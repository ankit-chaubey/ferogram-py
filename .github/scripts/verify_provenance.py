#!/usr/bin/env python3
"""Check a published PyPI release against the distributions that were uploaded.

Polls the PyPI simple API (PEP 691) until every file of the release is listed
and has a provenance URL. Then it checks, for every file:

  - the sha256 on PyPI equals the sha256 of the local file
  - the provenance object (PEP 740) names the expected GitHub publisher

The signatures themselves are verified separately with pypi-attestations.
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

SIMPLE_ACCEPT = "application/vnd.pypi.simple.v1+json"
INTEGRITY_ACCEPT = "application/vnd.pypi.integrity.v1+json"


def get_json(url: str, accept: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": accept})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("version")
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--repository", required=True, help="owner/repo")
    parser.add_argument("--workflow", required=True, help="e.g. publish.yml")
    parser.add_argument("--environment", default="")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--files-out", help="write the checked file names here")
    args = parser.parse_args()

    local = {p.name: sha256(p) for p in Path(args.dist_dir).iterdir() if p.is_file()}
    if not local:
        print(f"::error::no files in {args.dist_dir}")
        return 1

    url = f"https://pypi.org/simple/{args.project}/"
    deadline = time.monotonic() + args.timeout
    while True:
        listing = get_json(url, SIMPLE_ACCEPT)
        remote = {f["filename"]: f for f in listing["files"] if f["filename"] in local}
        waiting = sorted(
            (set(local) - set(remote))
            | {n for n, f in remote.items() if not f.get("provenance")}
        )
        if not waiting:
            break
        if time.monotonic() > deadline:
            print("::error::timed out waiting for PyPI. Not listed or without provenance:")
            for name in waiting:
                print(f"  {name}")
            return 1
        print(f"{len(waiting)} of {len(local)} files not ready yet, retrying in {args.interval}s")
        time.sleep(args.interval)

    problems = []
    for name in sorted(local):
        entry = remote[name]
        found = []
        if entry["hashes"].get("sha256") != local[name]:
            found.append(f"{name}: sha256 on PyPI differs from the uploaded file")

        provenance = get_json(entry["provenance"], INTEGRITY_ACCEPT)
        publishers = [
            bundle.get("publisher") or {}
            for bundle in provenance.get("attestation_bundles", [])
            if bundle.get("attestations")
        ]
        matched = any(
            pub.get("kind") == "GitHub"
            and pub.get("repository") == args.repository
            and pub.get("workflow") == args.workflow
            and (not args.environment or pub.get("environment") == args.environment)
            for pub in publishers
        )
        if not matched:
            found.append(f"{name}: unexpected publisher {publishers}")

        if not found:
            print(f"ok   {name}")
        problems.extend(found)

    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        return 1

    if args.files_out:
        Path(args.files_out).write_text("\n".join(sorted(local)) + "\n", encoding="utf-8")
    print(f"{len(local)} files on PyPI with provenance from {args.repository} ({args.workflow})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
