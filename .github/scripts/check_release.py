#!/usr/bin/env python3
"""Release checks used by .github/workflows/publish.yml.

  check_release.py version [--check-pypi]
      pyproject.toml version must match the pushed tag (v<version>). With
      --check-pypi the version must also not exist on PyPI yet.

  check_release.py dists DIR VERSION
      DIR must hold exactly the distributions a full release consists of.
"""

import argparse
import fnmatch
import os
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = "ferogram"

# One pattern per distribution in a release. Each pattern must match exactly
# one file and every file must match exactly one pattern.
EXPECTED_DISTS = [
    "{p}-{v}.tar.gz",
    "{p}-{v}-cp39-abi3-manylinux*x86_64*.whl",
    "{p}-{v}-cp39-abi3-manylinux*aarch64*.whl",
    "{p}-{v}-cp39-abi3-macosx_*_x86_64.whl",
    "{p}-{v}-cp39-abi3-macosx_*_arm64.whl",
    "{p}-{v}-cp39-abi3-win_amd64.whl",
    "{p}-{v}-cp39-abi3-android_*_arm64_v8a.whl",
    "{p}-{v}-cp39-abi3-android_*_armeabi_v7a.whl",
    "{p}-{v}-cp39-abi3-android_*_x86_64.whl",
    "{p}-{v}-cp39-abi3-android_*_x86.whl",
]


def error(msg: str) -> None:
    print(f"::error::{msg}")


def warning(msg: str) -> None:
    print(f"::warning::{msg}")


def read_versions(root: Path) -> tuple[str, str]:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    cargo = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["version"], cargo["package"]["version"]


def on_pypi(project: str, version: str) -> bool:
    url = f"https://pypi.org/pypi/{project}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30):
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def cmd_version(args: argparse.Namespace) -> int:
    version, cargo_version = read_versions(Path(args.root))
    problems = []

    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ["GITHUB_REF_NAME"]
        if tag != f"v{version}":
            problems.append(
                f"tag {tag} does not match the pyproject.toml version {version} "
                f"(expected tag v{version})"
            )
    else:
        print("Not a tag run, skipping the tag comparison.")

    if cargo_version != version:
        warning(
            f"Cargo.toml version {cargo_version} differs from pyproject.toml "
            f"version {version}. The wheels use the pyproject.toml version."
        )

    if args.check_pypi and on_pypi(PROJECT, version):
        problems.append(f"{PROJECT} {version} already exists on PyPI")

    for problem in problems:
        error(problem)
    if problems:
        return 1

    print(f"{PROJECT} {version}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"version={version}\n")
    return 0


def cmd_dists(args: argparse.Namespace) -> int:
    files = sorted(p.name for p in Path(args.dir).iterdir() if p.is_file())
    patterns = [p.format(p=PROJECT, v=args.version) for p in EXPECTED_DISTS]
    problems = []

    for pattern in patterns:
        matches = [f for f in files if fnmatch.fnmatch(f, pattern)]
        if len(matches) != 1:
            problems.append(f"{len(matches)} files match {pattern}, expected 1")

    for name in files:
        hits = [p for p in patterns if fnmatch.fnmatch(name, p)]
        if len(hits) != 1:
            problems.append(f"unexpected file in {args.dir}: {name}")

    for name in files:
        print(name)
    for problem in problems:
        error(problem)
    if problems:
        return 1

    print(f"{len(files)} distributions, all expected platforms present")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_version = sub.add_parser("version")
    p_version.add_argument("--root", default=".")
    p_version.add_argument("--check-pypi", action="store_true")
    p_version.set_defaults(func=cmd_version)

    p_dists = sub.add_parser("dists")
    p_dists.add_argument("dir")
    p_dists.add_argument("version")
    p_dists.set_defaults(func=cmd_dists)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
