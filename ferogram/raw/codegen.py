# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# ferogram is a high-performance Telegram MTProto framework written in Rust.
# ferogram-py provides Python bindings built on top of the Rust core for
# building Telegram clients, bots, and applications with a simple API.
#
# Rust core: https://github.com/ankit-chaubey/ferogram
# Python bindings: https://github.com/ankit-chaubey/ferogram-py
#
# If you use or modify this code, keep this notice at the top of the file
# and include the LICENSE-MIT or LICENSE-APACHE file from this repository.

#
# Run: python -m ferogram.raw.codegen <api.tl> <out_dir>

from __future__ import annotations
import re, sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

TL_LINE = re.compile(
    r'^(\w[\w.]*)'
    r'#([0-9a-fA-F]+)'
    r'((?:\s+[\w.]+:[^\s=]+)*)'
    r'\s*=\s*([\w.<>]+);'
)
FIELD_RE  = re.compile(r'([\w.]+):([\w?.<>]+)')
FLAG_FIELD = re.compile(r'flags\.(\d+)\?(.+)')

PRIMITIVES = {"int", "long", "double", "string", "bytes", "Bool",
              "int128", "int256", "true", "True", "Int", "Long"}

# TL field names that clash with Python keywords → rename with trailing _
# We keep to_dict using the original TL name so serialization is unaffected
import keyword as _kw
_PY_KEYWORDS = set(_kw.kwlist) | {"True", "False", "None", "self"}

def _safe_param(name: str) -> str:
    return name + "_" if name in _PY_KEYWORDS else name


class Field(NamedTuple):
    name: str
    ftype: str
    flag_bit: int | None


class Constructor(NamedTuple):
    name: str
    cid: int
    fields: list[Field]
    ret: str
    is_function: bool


def parse_fields(raw: str) -> list[Field]:
    fields = []
    for fname, ftype in FIELD_RE.findall(raw):
        if fname == "flags" and ftype == "#":
            continue
        m = FLAG_FIELD.match(ftype)
        if m:
            fields.append(Field(fname, m.group(2), int(m.group(1))))
        else:
            fields.append(Field(fname, ftype, None))
    return fields


def parse_tl(path: Path) -> tuple[list[Constructor], list[Constructor]]:
    types: list[Constructor] = []
    funcs: list[Constructor] = []
    in_functions = False
    for line in path.read_text().splitlines():
        line = line.strip()
        if line == "---functions---":
            in_functions = True
            continue
        if line.startswith("//") or not line:
            continue
        m = TL_LINE.match(line)
        if not m:
            continue
        name, cid_hex, fields_raw, ret = m.groups()
        cid = int(cid_hex, 16)
        fields = parse_fields(fields_raw)
        c = Constructor(name, cid, fields, ret, in_functions)
        (funcs if in_functions else types).append(c)
    return types, funcs


import keyword as _keyword

def py_class(tl_name: str) -> str:
    base = tl_name.split(".")[-1]
    result = base[0].upper() + base[1:]
    # avoid Python keywords and builtins that look like TL names (True, False, None)
    if _keyword.iskeyword(result) or result in ("True", "False", "None"):
        result = "Tl" + result
    return result


def ns_of(tl_name: str) -> str:
    parts = tl_name.split(".")
    return parts[0] if len(parts) > 1 else "_base"


def ftype_py(ftype: str) -> str:
    mapping = {
        "int": "int", "long": "int", "int32": "int",
        "int64": "int", "int128": "int", "int256": "int",
        "double": "float", "string": "str", "bytes": "bytes",
        "Bool": "bool", "true": "bool", "True": "bool",
    }
    if ftype in mapping:
        return mapping[ftype]
    if ftype.startswith(("Vector<", "vector<")):
        inner = ftype[7:-1]
        return f"list[{ftype_py(inner)}]"
    return "Any"  # TL object - accepts dict or typed instance


def render_class(c: Constructor) -> str:
    cls = py_class(c.name)
    lines = [f"class {cls}:"]

    # __init__: required fields first, optional (flag) fields after
    # This is required by Python: non-default args can't follow default args
    required = [f for f in c.fields if f.flag_bit is None]
    optional = [f for f in c.fields if f.flag_bit is not None]
    if required or optional:
        lines.append("    def __init__(")
        lines.append("        self,")
        for f in required:
            p = _safe_param(f.name)
            lines.append(f"        {p}: {ftype_py(f.ftype)},")
        for f in optional:
            p = _safe_param(f.name)
            lines.append(f"        {p}: {ftype_py(f.ftype)} | None = None,")
        lines.append("    ) -> None:")
        for f in c.fields:
            p = _safe_param(f.name)
            lines.append(f"        self.{p} = {p}")
    else:
        lines.append("    def __init__(self) -> None:")
        lines.append("        pass")

    # to_dict: _tl._resolve() lets callers pass dicts or typed objects
    lines.append("")
    lines.append("    def to_dict(self) -> dict:")
    lines.append(f'        return {{"_": "{c.name}", **{{')
    for f in c.fields:
        lines.append(f'            "{f.name}": _tl._resolve(self.{_safe_param(f.name)}),')
    lines.append("        }}")

    # to_bytes
    lines.append("")
    lines.append("    def to_bytes(self) -> bytes:")
    lines.append("        return _tl.serialize_object(self.to_dict(), _SCHEMA)")

    # __repr__
    lines.append("")
    preview = ", ".join(
        f"{f.name}={{self.{_safe_param(f.name)}!r}}"
        for f in c.fields[:4]
    )
    lines.append("    def __repr__(self) -> str:")
    lines.append(f'        return f"{cls}({preview})"')
    lines.append("")

    return "\n".join(lines)


def build_schema(constructors: list[Constructor]) -> str:
    lines = ["_SCHEMA = {"]
    for c in constructors:
        fields_repr = ", ".join(
            f'("{f.name}", "{f.ftype}", {f.flag_bit!r})'
            for f in c.fields
        )
        lines.append(f'    "{c.name}": ({c.cid:#010x}, [{fields_repr}]),')
    lines.append("}")
    return "\n".join(lines)


def build_schema_by_cid(constructors: list[Constructor]) -> str:
    lines = ["_SCHEMA_BY_CID = {"]
    for c in constructors:
        fields_repr = ", ".join(
            f'("{f.name}", "{f.ftype}", {f.flag_bit!r})'
            for f in c.fields
        )
        lines.append(f'    {c.cid:#010x}: ("{c.name}", [{fields_repr}]),')
    lines.append("}")
    return "\n".join(lines)


LICENSE = """\
# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""

NS_HEADER = """\
# auto-generated by ferogram raw codegen - do not edit
from __future__ import annotations
from typing import Any
from ... import tl as _tl
from .._tl_schema import _SCHEMA

"""


def write_namespace_pkg(
    out_pkg: Path,
    grouped: dict[str, list[Constructor]],
    schema_str: str,
) -> None:
    out_pkg.mkdir(parents=True, exist_ok=True)

    all_classes: list[str] = []

    for ns, constructors in sorted(grouped.items()):
        mod_file = out_pkg / f"{ns}.py"
        body = [NS_HEADER]
        for c in constructors:
            body.append(render_class(c))
            all_classes.append(py_class(c.name))
        mod_file.write_text("\n".join(body))

    # flat imports - re-exports every class from every namespace module
    init_lines = [
        LICENSE,
        "# auto-generated - do not edit",
        "# Flat imports so both styles work:",
        "#   raw.functions.messages.GetHistory(...)   ← namespace style",
        "#   raw.functions.GetHistory(...)            ← flat style (convenience)",
        "",
    ]
    for ns in sorted(grouped):
        init_lines.append(f"from .{ns} import *  # noqa: F401,F403")
    init_lines.append("")

    # expose namespace modules as attributes too
    init_lines.append("# namespace sub-modules")
    for ns in sorted(grouped):
        init_lines.append(f"from . import {ns}  # noqa: F401")
    init_lines.append("")

    (out_pkg / "__init__.py").write_text("\n".join(init_lines))


def generate(tl_path: Path, out_dir: Path) -> None:
    types, funcs = parse_tl(tl_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_constructors = types + funcs
    schema_str     = build_schema(all_constructors)
    schema_by_cid  = build_schema_by_cid(types)

    # _tl_schema.py - unchanged format, used by serializer
    (out_dir / "_tl_schema.py").write_text(
        "# auto-generated schema - do not edit\n"
        + schema_str + "\n\n"
        + schema_by_cid + "\n"
    )

    # group by namespace
    type_ns: dict[str, list[Constructor]] = defaultdict(list)
    func_ns: dict[str, list[Constructor]] = defaultdict(list)
    for c in types:
        type_ns[ns_of(c.name)].append(c)
    for c in funcs:
        func_ns[ns_of(c.name)].append(c)

    # write types/ and functions/ namespace packages
    write_namespace_pkg(out_dir / "types",     type_ns, schema_str)
    write_namespace_pkg(out_dir / "functions", func_ns, schema_str)

    # generated/__init__.py
    (out_dir / "__init__.py").write_text(
        LICENSE + "\n"
        "from . import functions, types\n\n"
        "__all__ = ['functions', 'types']\n"
    )

    print(f"generated {len(types)} types, {len(funcs)} functions")
    print(f"  types namespaces:     {sorted(type_ns)}")
    print(f"  functions namespaces: {sorted(func_ns)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python codegen.py <api.tl> <out_dir>")
        sys.exit(1)
    generate(Path(sys.argv[1]), Path(sys.argv[2]))
