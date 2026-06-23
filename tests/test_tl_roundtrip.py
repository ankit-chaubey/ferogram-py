# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# Round-trip sweep for ferogram/raw/generated/. Runs without pytest so it
# works the same locally and in CI: python3 tests/test_tl_roundtrip.py
#
# Per constructor:
#   1. to_bytes() == serialize_object(to_dict()) (specialized vs generic path)
#   2. for types only: tl.deserialize(wire) == to_dict() (live dispatcher path)
#   3. from_bytes(), called past the CID, agrees with both and consumes all bytes
#
# Field values are synthetic placeholders, not valid Telegram data, chosen
# from the schema's declared ftype (not __init__'s annotations, which are
# plain strings at runtime since generated files use
# `from __future__ import annotations`).

from __future__ import annotations

import sys
import pathlib
import importlib
import inspect
import types as _pytypes

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Bool's own constructors are doubly exceptional:
#   - deserialize() returns bare True/False (not a dict), because _read_object
#     intercepts their CIDs before any schema dispatch.
#   - from_bytes() is called *past* the CID, so it returns the dict form
#     {"_": "boolTrue"}, so the from_bytes check is skipped for these.
_BOOL_NAMES = {"boolTrue": True, "boolFalse": False}


def _load_without_rust_extension():
    """
    Import ferogram.raw.tl and ferogram.raw.generated without pulling in
    ferogram/__init__.py, which needs the compiled Rust extension. Tests
    for the pure-Python codegen output shouldn't require a built wheel.
    """
    pkg = _pytypes.ModuleType("ferogram")
    pkg.__path__ = [str(ROOT / "ferogram")]
    sys.modules["ferogram"] = pkg

    raw_pkg = _pytypes.ModuleType("ferogram.raw")
    raw_pkg.__path__ = [str(ROOT / "ferogram" / "raw")]
    sys.modules["ferogram.raw"] = raw_pkg

    tl = importlib.import_module("ferogram.raw.tl")
    schema_mod = importlib.import_module("ferogram.raw.generated._tl_schema")
    types_pkg = importlib.import_module("ferogram.raw.generated.types")
    functions_pkg = importlib.import_module("ferogram.raw.generated.functions")
    return tl, schema_mod, types_pkg, functions_pkg


def _placeholder_for(ftype: str):
    """A wire-valid stand-in value for one field, by its real schema ftype."""
    if ftype in ("int", "long", "int128", "int256"):
        return 0
    if ftype == "double":
        return 0.0
    if ftype == "string":
        return ""
    if ftype == "bytes":
        return b""
    if ftype in ("Bool", "true", "True"):
        return True
    if ftype.startswith(("Vector<", "vector<")):
        return []
    # Abstract/object-typed field. inputPeerEmpty is a zero-field TL
    # constructor that deserializes back to {"_": "inputPeerEmpty"}, and
    # round-trips cleanly through both the generic and specialized paths,
    # unlike boolTrue whose CID causes _read_object to return bare True.
    return {"_": "inputPeerEmpty"}


def _ordered_fields(fields: list[tuple]) -> list[tuple]:
    """Required fields first, then optional, matches render_class's __init__ param order."""
    required = [f for f in fields if f[2] is None]
    optional = [f for f in fields if f[2] is not None]
    return required + optional


def _instantiate(cls: type, fields: list[tuple], *, include_optional: bool):
    sig_params = [
        p for p in inspect.signature(cls.__init__).parameters.values()
        if p.name != "self"
    ]
    ordered = _ordered_fields(fields)
    if len(sig_params) != len(ordered):
        raise AssertionError(
            f"{cls.__qualname__}: __init__ has {len(sig_params)} params "
            f"but schema has {len(ordered)} fields"
        )

    kwargs = {}
    for param, (fname, ftype, flag) in zip(sig_params, ordered):
        if flag is not None and not include_optional:
            continue
        kwargs[param.name] = _placeholder_for(ftype)
    return cls(**kwargs)


def _iter_classes(pkg):
    import pkgutil
    for _, modname, _ in pkgutil.walk_packages(
        path=pkg.__path__, prefix=pkg.__name__ + "."
    ):
        mod = importlib.import_module(modname)
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, type) and hasattr(obj, "to_bytes") and obj.__module__ == mod.__name__:
                yield obj


def run() -> int:
    tl, schema_mod, types_pkg, functions_pkg = _load_without_rust_extension()
    schema = schema_mod._SCHEMA
    schema_by_cid = schema_mod._SCHEMA_BY_CID

    # CID -> (name, fields) for everything, types and functions alike.
    # _SCHEMA_BY_CID deliberately excludes functions (never deserialized
    # from the wire), but this sweep also needs their field lists.
    cid_index = {cid: (name, fields) for name, (cid, fields) in schema.items()}

    failures: list[str] = []
    checked = 0

    for is_type, pkg in ((True, types_pkg), (False, functions_pkg)):
        for cls in _iter_classes(pkg):
            name, fields = cid_index[cls._CID]
            for include_optional in (True, False):
                checked += 1
                label = f"{name} (optional={include_optional})"
                try:
                    obj = _instantiate(cls, fields, include_optional=include_optional)
                    specialized = obj.to_bytes()
                    generic = tl.serialize_object(obj.to_dict(), schema)
                    if specialized != generic:
                        failures.append(f"{label}: to_bytes() != serialize_object()")
                        continue

                    if not is_type:
                        continue  # functions are never deserialized from the wire

                    if name in _BOOL_NAMES:
                        expected = _BOOL_NAMES[name]
                    else:
                        expected = {k: v for k, v in obj.to_dict().items() if v is not None}

                    live = tl.deserialize(specialized, schema_by_cid)
                    if live != expected:
                        failures.append(
                            f"{label}: deserialize() mismatch\n"
                            f"    expected: {expected}\n"
                            f"    got:      {live}"
                        )
                        continue

                    if name in _BOOL_NAMES:
                        continue  # from_bytes() returns dict form; bare bool only comes from _read_object CID dispatch
                    spec_dict, consumed = cls.from_bytes(specialized, 4)
                    if spec_dict != expected:
                        failures.append(f"{label}: from_bytes() mismatch")
                    elif consumed != len(specialized):
                        failures.append(
                            f"{label}: from_bytes() consumed {consumed} of {len(specialized)} bytes"
                        )
                except Exception as e:  # noqa: BLE001 - want every failure, not just the first
                    failures.append(f"{label}: raised {type(e).__name__}: {e}")

    print(f"checked {checked} (constructor x optional-state) combinations")
    if failures:
        print(f"\n{len(failures)} FAILURES:\n")
        for f in failures[:50]:
            print(f"  - {f}")
        if len(failures) > 50:
            print(f"  ... and {len(failures) - 50} more")
        return 1

    print("all combinations round-tripped correctly")
    return 0


if __name__ == "__main__":
    sys.exit(run())
