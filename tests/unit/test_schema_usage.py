# Every raw TL dict literal in the hand-written library code must match the
# current schema (known constructor, known fields, all required fields set).
#
# This catches the breakage a layer bump causes in code that builds requests
# by hand, long before a user hits "unknown TL constructor" at runtime.
#
# KNOWN_ISSUES is a ratchet for problems that already exist: new problems fail
# the test, and so does fixing a listed one without removing it, so the list can
# only shrink. It is empty now.

from __future__ import annotations

import ast
import importlib
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()

SCHEMA = importlib.import_module("ferogram.raw.generated._tl_schema")._SCHEMA
PACKAGE = support.PACKAGE_DIR

# Dicts with an "_" key that are internal and not TL objects.
INTERNAL = {"rpc_error"}

# (file, constructor, problem) -> how many times it occurs
KNOWN_ISSUES: Counter = Counter()


def _scan() -> Counter:
    found: Counter = Counter()
    for path in sorted(PACKAGE.rglob("*.py")):
        if "generated" in path.parts:
            continue
        rel = path.relative_to(PACKAGE).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value if isinstance(k, ast.Constant) else None for k in node.keys]
            if "_" not in keys or None in keys:      # no "_", or a **spread: can't check
                continue
            name_node = node.values[keys.index("_")]
            if not (isinstance(name_node, ast.Constant) and isinstance(name_node.value, str)):
                continue
            name = name_node.value
            if name in INTERNAL:
                continue
            given = [k for k in keys if k != "_"]
            if name not in SCHEMA:
                found[(rel, name, "unknown constructor")] += 1
                continue
            fields = SCHEMA[name][1]
            known = {f[0] for f in fields}
            for key in given:
                if key not in known:
                    found[(rel, name, f"unknown field {key}")] += 1
            for fname, ftype, flag in fields:
                if flag is None and ftype != "#" and fname not in given:
                    found[(rel, name, f"missing required {fname}")] += 1
    return found


def test_no_new_schema_mismatches():
    new = _scan() - KNOWN_ISSUES
    assert not new, "TL dicts that do not match the schema:\n" + "\n".join(
        f"  {f}: {c}: {p}" for (f, c, p) in sorted(new)
    )


def test_known_issues_list_has_no_stale_entries():
    fixed = KNOWN_ISSUES - _scan()
    assert not fixed, "fixed, remove from KNOWN_ISSUES:\n" + "\n".join(
        f"  {f}: {c}: {p}" for (f, c, p) in sorted(fixed)
    )
