"""Test helpers.

`install()` makes the real `ferogram` package importable from the source tree.
If the compiled Rust extension (`ferogram._ferogram`) is not built, a stub is
registered so that pure-Python code (TL layer, keyboards, filters, rich text,
the `Client` class layout) can still be tested without a Rust toolchain.
Set FEROGRAM_TEST_STUB=1 to force the stub even when the extension exists.
"""

from __future__ import annotations

import os
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYTHON_DIR = ROOT / "python"
PACKAGE_DIR = PYTHON_DIR / "ferogram"


def _extension_built() -> bool:
    return any(PACKAGE_DIR.glob("_ferogram*.so")) or any(PACKAGE_DIR.glob("_ferogram*.pyd"))


def _make_stub() -> types.ModuleType:
    stub = types.ModuleType("ferogram._ferogram")
    stub.__doc__ = "Test stub for the compiled ferogram extension."

    def _getattr(name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        if name == "srp_calculate":
            return lambda *args, **kwargs: None
        return type(name, (), {"__init__": lambda self, *a, **k: None})

    stub.__getattr__ = _getattr  # type: ignore[attr-defined]
    return stub


def install() -> None:
    """Idempotent: put python/ on sys.path and stub the extension if needed."""
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    if "ferogram._ferogram" in sys.modules:
        return
    if os.environ.get("FEROGRAM_TEST_STUB") or not _extension_built():
        sys.modules["ferogram._ferogram"] = _make_stub()


def uses_stub() -> bool:
    return isinstance(sys.modules.get("ferogram._ferogram"), types.ModuleType) and (
        sys.modules["ferogram._ferogram"].__doc__ or ""
    ).startswith("Test stub")
