# Public surface and internal layout of the Python package.

from __future__ import annotations

import importlib
import inspect
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()

ferogram = importlib.import_module("ferogram")
client_mod = importlib.import_module("ferogram.client")
methods = importlib.import_module("ferogram.methods")

_SKIP = {"__module__", "__qualname__", "__doc__", "__dict__", "__weakref__",
         "__annotations__", "__firstlineno__", "__static_attributes__", "__slots__"}


def _defined(cls) -> set[str]:
    return {n for n in vars(cls) if n not in _SKIP}


def test_all_exported_names_resolve():
    for pkg in (ferogram, client_mod, methods):
        for name in getattr(pkg, "__all__", []):
            assert hasattr(pkg, name), f"{pkg.__name__}.__all__ lists missing {name!r}"


def test_package_exposes_client():
    assert ferogram.Client is client_mod.Client


def test_client_is_composed_of_the_method_groups():
    mro = client_mod.Client.__mro__
    for name in methods.__all__:
        assert getattr(methods, name) in mro, name


def test_method_groups_do_not_overlap():
    seen: dict[str, str] = {}
    groups = [getattr(methods, n) for n in methods.__all__] + [client_mod.Client]
    rich = importlib.import_module("ferogram.rich")._RichMixin
    for cls in groups + [rich]:
        for attr in _defined(cls):
            assert attr not in seen, f"{attr!r} defined in both {seen[attr]} and {cls.__name__}"
            seen[attr] = cls.__name__


def test_method_groups_are_documented():
    for name in methods.__all__:
        assert inspect.getdoc(getattr(methods, name)), name


def test_client_keeps_its_public_methods():
    expected = {
        "start", "stop", "run", "invoke", "send_message", "edit_message", "delete_messages",
        "forward_messages", "get_dialogs", "get_chat", "get_participants", "download_media",
        "upload_file", "send_photo", "answer_callback_query", "sign_in", "bot_sign_in",
        "on_message", "on_callback_query", "add_handler",
    }
    missing = sorted(n for n in expected if not hasattr(client_mod.Client, n))
    assert not missing, missing


def test_backward_compatible_names_stay_importable_from_client():
    # These used to be defined in client.py before it was split into modules.
    for name in ("StopPropagation", "ContinuePropagation", "TransferHandle",
                 "TransferLimits", "TransferCancelled", "SignInCodeInvalid",
                 "available_qualities", "_markup_to_dict", "_log"):
        assert hasattr(client_mod, name), name


def test_public_async_methods_are_coroutines_or_async_generators():
    for name, member in inspect.getmembers(client_mod.Client):
        if name.startswith("_") or not callable(member):
            continue
        if name.startswith("on_") or name in {"add_handler", "remove_handler", "run",
                                              "signal_network_restored"}:
            continue
        # iter_* helpers are async generators; everything else that does I/O is async
        if inspect.isasyncgenfunction(member) or inspect.iscoroutinefunction(member):
            continue
        assert not name.startswith(("send_", "get_", "iter_")), f"{name} should be async"


def _package_parts(path: pathlib.Path) -> list[str]:
    rel = path.relative_to(support.PYTHON_DIR).with_suffix("")
    return list(rel.parts[:-1])           # a/b/c.py and a/b/__init__.py both live in package a.b


def test_every_relative_import_resolves():
    """Checks imports inside function bodies too, which lint and plain imports never exercise.

    Moving a method to another package depth silently breaks `from .x import y` written
    inside it, and nothing fails until that method is called.
    """
    import ast

    problems = []
    for path in sorted(support.PACKAGE_DIR.rglob("*.py")):
        if "generated" in path.parts:
            continue
        package = _package_parts(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
            if not (isinstance(node, ast.ImportFrom) and node.level):
                continue
            base = package[: len(package) - (node.level - 1)]
            target = ".".join(base + ([node.module] if node.module else []))
            where = f"{path.relative_to(support.PYTHON_DIR)}:{node.lineno}"
            try:
                module = importlib.import_module(target)
            except ImportError:
                problems.append(f"{where}: no module {target!r}")
                continue
            for alias in node.names:
                if alias.name == "*" or hasattr(module, alias.name):
                    continue
                try:
                    importlib.import_module(f"{target}.{alias.name}")
                except ImportError:
                    problems.append(f"{where}: {target!r} has no {alias.name!r}")
    assert not problems, "\n".join(problems)
