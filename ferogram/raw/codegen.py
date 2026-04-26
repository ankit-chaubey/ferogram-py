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

#!/usr/bin/env python3
# Parses api.tl and generates raw/functions.py and raw/types.py
# Run: python -m ferogram.raw.codegen <api.tl> <out_dir>

from __future__ import annotations
import re, sys, struct
from pathlib import Path
from typing import NamedTuple

TL_LINE = re.compile(
    r'^(\w[\w.]*)'         # name (may have namespace like messages.getHistory)
    r'#([0-9a-fA-F]+)'    # #cid
    r'((?:\s+[\w.]+:[^\s=]+)*)'  # fields
    r'\s*=\s*([\w.<>]+);' # = ReturnType
)

FIELD_RE = re.compile(r'([\w.]+):([\w?.<>]+)')

PRIMITIVES = {"int", "long", "double", "string", "bytes", "Bool",
              "int128", "int256", "true", "True", "Int", "Long"}

FLAG_FIELD = re.compile(r'flags\.(\d+)\?(.+)')


class Field(NamedTuple):
    name: str
    ftype: str
    flag_bit: int | None  # None = required


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
            continue  # skip flags placeholder, we handle it
        m = FLAG_FIELD.match(ftype)
        if m:
            bit, inner = int(m.group(1)), m.group(2)
            fields.append(Field(fname, inner, bit))
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


def py_name(tl_name: str) -> str:
    # messages.getHistory -> GetHistory (class name)
    base = tl_name.split(".")[-1]
    return base[0].upper() + base[1:]


def namespace(tl_name: str) -> str:
    parts = tl_name.split(".")
    return parts[0] if len(parts) > 1 else "base"


def ftype_py(ftype: str) -> str:
    mapping = {
        "int": "int", "long": "int", "int32": "int",
        "int64": "int", "int128": "int", "int256": "int",
        "double": "float", "string": "str", "bytes": "bytes",
        "Bool": "bool", "true": "bool", "True": "bool",
    }
    if ftype in mapping:
        return mapping[ftype]
    if ftype.startswith("Vector<") or ftype.startswith("vector<"):
        inner = ftype[7:-1]
        return f"list[{ftype_py(inner)}]"
    return "dict"  # nested TL object


def render_class(c: Constructor, schema_name: str) -> str:
    lines = [f"class {py_name(c.name)}:"]
    # __init__
    params = []
    for f in c.fields:
        ann = ftype_py(f.ftype)
        if f.flag_bit is not None:
            params.append(f"        {f.name}: {ann} | None = None,")
        else:
            params.append(f"        {f.name}: {ann},")
    if params:
        lines.append("    def __init__(")
        lines.append("        self,")
        lines.extend(params)
        lines.append("    ) -> None:")
        for f in c.fields:
            lines.append(f"        self.{f.name} = {f.name}")
    else:
        lines.append("    def __init__(self) -> None:")
        lines.append("        pass")

    # to_dict
    lines.append("")
    lines.append("    def to_dict(self) -> dict:")
    lines.append(f'        return {{"_": "{c.name}", **{{')
    for f in c.fields:
        lines.append(f'            "{f.name}": self.{f.name},')
    lines.append("        }}")

    # to_bytes
    lines.append("")
    lines.append("    def to_bytes(self) -> bytes:")
    lines.append(f"        return _tl.serialize_object(self.to_dict(), _SCHEMA)")

    # __repr__
    lines.append("")
    lines.append("    def __repr__(self) -> str:")
    field_repr = ", ".join(f"{f.name}={{self.{f.name}!r}}" for f in c.fields[:4])
    lines.append(f'        return f"{py_name(c.name)}({field_repr})"')
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


HEADER = """\
# auto-generated by ferogram raw codegen - do not edit
from __future__ import annotations
from .. import _tl as _tl

"""


def generate(tl_path: Path, out_dir: Path) -> None:
    types, funcs = parse_tl(tl_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    schema_str = build_schema(types + funcs)
    schema_by_cid_str = build_schema_by_cid(types)

    # write _tl_schema.py used by both modules
    schema_file = out_dir / "_tl_schema.py"
    schema_file.write_text(
        "# auto-generated schema - do not edit\n"
        + schema_str + "\n\n"
        + schema_by_cid_str + "\n"
    )

    # types.py
    type_lines = [HEADER, schema_str, "", schema_by_cid_str, "", ""]
    for c in types:
        type_lines.append(render_class(c, "_SCHEMA"))
    (out_dir / "types.py").write_text("\n".join(type_lines))

    # functions.py
    func_lines = [HEADER, schema_str, "", ""]
    for c in funcs:
        func_lines.append(render_class(c, "_SCHEMA"))
    (out_dir / "functions.py").write_text("\n".join(func_lines))

    # __init__.py for the raw subpackage
    init = (out_dir / "__init__.py")
    if not init.exists():
        init.write_text("from .functions import *  # noqa\nfrom .types import *  # noqa\n")

    print(f"generated {len(types)} types, {len(funcs)} functions -> {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python codegen.py <api.tl> <out_dir>")
        sys.exit(1)
    generate(Path(sys.argv[1]), Path(sys.argv[2]))
