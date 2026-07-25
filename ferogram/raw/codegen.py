# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# ferogram is a high-performance Telegram MTProto framework written in Rust.
# ferogram-py is a Python MTProto library powered by ferogram, delivering
# native Rust performance through a clean and Pythonic API for building
# Telegram clients, bots, and applications.
#
# Rust: https://github.com/ankit-chaubey/ferogram
# Python: https://github.com/ankit-chaubey/ferogram-py
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
FIELD_RE   = re.compile(r'([\w.]+):([\w?.<>#]+)')
FLAG_FIELD = re.compile(r'^(flags\d*)\.(\d+)\?(.+)$')

PRIMITIVES = {"int", "long", "double", "string", "bytes", "Bool",
              "int128", "int256", "true", "True", "Int", "Long"}

import keyword as _kw
_PY_KEYWORDS = set(_kw.kwlist) | {"True", "False", "None", "self"}

def _safe_param(name: str) -> str:
    return name + "_" if name in _PY_KEYWORDS else name


class Flag(NamedTuple):
    group: str
    bit:   int


class Field(NamedTuple):
    name:  str
    ftype: str
    flag:  Flag | None


class Constructor(NamedTuple):
    name:        str
    cid:         int
    fields:      list[Field]
    ret:         str
    is_function: bool
    flag_markers: dict[str, int] = {}


def parse_fields(raw: str) -> tuple[list[Field], dict[str, int]]:
    """Parse fields, and also record where each ``group:#`` marker sits.

    ``flag_markers[group]`` is the number of *data* fields already seen
    when that marker token was encountered in the schema text - i.e. the
    index in the returned field list that the group's flags word must be
    read/written immediately before. Wire order is whatever the schema
    text says; it is NOT always "flags first" (e.g. ``poll#966e2dbf
    id:long flags:# closed:flags.0?true ...`` reads ``id`` before the
    flags word).
    """
    fields: list[Field] = []
    flag_markers: dict[str, int] = {}
    for fname, ftype in FIELD_RE.findall(raw):
        if ftype == "#":
            flag_markers[fname] = len(fields)
            continue
        m = FLAG_FIELD.match(ftype)
        if m:
            group, bit_str, inner = m.groups()
            fields.append(Field(fname, inner, Flag(group, int(bit_str))))
        else:
            fields.append(Field(fname, ftype, None))
    return fields, flag_markers


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
        fields, flag_markers = parse_fields(fields_raw)
        c = Constructor(name, cid, fields, ret, in_functions, flag_markers)
        (funcs if in_functions else types).append(c)
    return types, funcs


def parse_layer(path: Path) -> int:
    for line in path.read_text().splitlines():
        m = re.match(r"^//\s*LAYER\s+(\d+)", line.strip())
        if m:
            return int(m.group(1))
    return 0


import keyword as _keyword

def py_class(tl_name: str) -> str:
    base = tl_name.split(".")[-1]
    result = base[0].upper() + base[1:]
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
    return "Any"



# Deserialization codegen (Phase 4)

# Fixed-width field: (struct format char, byte width)
_FIXED_READ: dict[str, tuple[str, int]] = {
    "int":    ("i", 4),
    "long":   ("q", 8),
    "double": ("d", 8),
}


def _collect_fixed_read_run(fields: list[Field], start: int) -> list[Field]:
    run = []
    for f in fields[start:]:
        if f.flag is None and f.ftype in _FIXED_READ:
            run.append(f)
        else:
            break
    return run


def _read_expr(ftype: str, access_data: str, access_pos: str) -> tuple[str, str] | None:
    """
    Return (value_expr, new_pos_expr) for reading one primitive field inline,
    or None if the type needs the generic _tl._read_typed() fallback.

    access_data / access_pos are the names of the data/pos variables in scope.
    """
    if ftype == "int":
        return (
            f"_struct.unpack_from('<i', {access_data}, {access_pos})[0]",
            f"{access_pos} + 4",
        )
    if ftype == "long":
        return (
            f"_struct.unpack_from('<q', {access_data}, {access_pos})[0]",
            f"{access_pos} + 8",
        )
    if ftype == "double":
        return (
            f"_struct.unpack_from('<d', {access_data}, {access_pos})[0]",
            f"{access_pos} + 8",
        )
    if ftype == "bytes":
        return None   # _pack_bytes logic is non-trivial; use generic
    if ftype == "string":
        return None   # same -- needs decode attempt
    if ftype == "Bool":
        return None   # needs CID dispatch
    return None       # TL object or Vector -- generic fallback


def _emit_read_body(c: Constructor) -> list[str]:
    """
    Return lines (8-space indent) of from_bytes(cls, data, pos).

    Returns (dict, new_pos). The dict always has "_" set to the TL name.
    Fields are written as obj["fname"] = value.

    Batching: runs of 2+ consecutive unconditional int/long/double fields
    are collapsed into a single struct.unpack_from call with a combined
    format string, unpacking directly into the dict in one shot.
    """
    I = "        "

    lines: list[str] = []
    lines.append(f'{I}obj = {{"_": "{c.name}"}}')

    # Determine flag groups present. A group counts as present if it was
    # *declared* (a "flags:#" / "flags2:#" marker in the schema text) even
    # if zero fields end up gated on it - the word is still 4 bytes on the
    # wire either way and must be consumed/emitted, or every field after
    # it silently misaligns. Order by the marker's schema position.
    flag_groups: list[str] = sorted(c.flag_markers, key=lambda g: c.flag_markers[g])

    if not flag_groups:
        # Fast path - no flags
        lines.extend(_emit_read_fields(c.fields, indent=I))
        lines.append(f"{I}return obj, pos")
        return lines

    # Emit each flag group's word read at its true schema position (the
    # marker's index into c.fields), not always hoisted to the front.
    # Groups whose marker sits at index 0 (the overwhelmingly common case)
    # read first; a marker declared after N data fields (e.g. poll#966e2dbf
    # id:long flags:# ...) reads those N fields first, matching real wire order.
    markers = c.flag_markers

    def _emit_group_read(grp: str) -> None:
        lines.append(f"{I}_{grp}_word, = _struct.unpack_from('<I', data, pos)")
        lines.append(f"{I}pos += 4")

    emitted_reads: set[str] = set()

    # Any group whose marker position is 0 reads before the first field.
    for grp in flag_groups:
        if markers.get(grp, 0) == 0 and grp not in emitted_reads:
            _emit_group_read(grp)
            emitted_reads.add(grp)

    i = 0
    fields = c.fields
    while i < len(fields):
        f = fields[i]

        # Emit any group whose marker sits exactly at this field index.
        for grp in flag_groups:
            if grp not in emitted_reads and markers.get(grp, 0) == i:
                _emit_group_read(grp)
                emitted_reads.add(grp)

        # Fall back: lazily read on first flagged-field encounter, in case
        # a group has no recorded marker (shouldn't happen, but safe).
        if f.flag and f.flag.group not in emitted_reads:
            grp = f.flag.group
            _emit_group_read(grp)
            emitted_reads.add(grp)

        # Try batch of consecutive unconditional fixed-width fields  but
        # never cross a not-yet-emitted flags marker's position, or a
        # mid-sequence group (e.g. poll/wallPaper's "flags" after "id")
        # would get read too late.
        if f.flag is None and f.ftype in _FIXED_READ:
            next_marker = min(
                (pos for grp, pos in markers.items()
                 if grp not in emitted_reads and pos > i),
                default=len(fields),
            )
            run = _collect_fixed_read_run(fields[:next_marker], i)
            if len(run) >= 2:
                fmt = "<" + "".join(_FIXED_READ[rf.ftype][0] for rf in run)
                size = sum(_FIXED_READ[rf.ftype][1] for rf in run)
                names = ", ".join(f'obj["{rf.name}"]' for rf in run)
                lines.append(f"{I}{names}, = _struct.unpack_from('{fmt}', data, pos)")
                lines.append(f"{I}pos += {size}")
                i += len(run)
                continue

        lines.extend(_emit_read_single_field(f, indent=I))
        i += 1

    lines.append(f"{I}return obj, pos")
    return lines


def _emit_read_fields(fields: list[Field], indent: str) -> list[str]:
    """Emit all fields with batching (no-flags fast path)."""
    lines = []
    i = 0
    while i < len(fields):
        f = fields[i]
        if f.flag is None and f.ftype in _FIXED_READ:
            run = _collect_fixed_read_run(fields, i)
            if len(run) >= 2:
                fmt = "<" + "".join(_FIXED_READ[rf.ftype][0] for rf in run)
                size = sum(_FIXED_READ[rf.ftype][1] for rf in run)
                names = ", ".join(f'obj["{rf.name}"]' for rf in run)
                lines.append(f"{indent}{names}, = _struct.unpack_from('{fmt}', data, pos)")
                lines.append(f"{indent}pos += {size}")
                i += len(run)
                continue
        lines.extend(_emit_read_single_field(f, indent=indent))
        i += 1
    return lines


def _emit_read_single_field(f: Field, indent: str) -> list[str]:
    I = indent
    fname = f.name

    if f.flag is not None:
        grp, bit = f.flag.group, f.flag.bit
        guard = f"{I}if _{grp}_word & (1 << {bit}):"
        II = I + "    "
        if f.ftype in ("true", "True"):
            return [guard, f'{II}obj["{fname}"] = True']
        inner = _read_expr(f.ftype, "data", "pos")
        if inner:
            val_expr, pos_expr = inner
            return [
                guard,
                f'{II}obj["{fname}"] = {val_expr}',
                f"{II}pos = {pos_expr}",
            ]
        return [
            guard,
            f'{II}obj["{fname}"], pos = _tl._read_typed(data, pos, "{f.ftype}", _SCHEMA_BY_CID)',
        ]

    # Unconditional field
    if f.ftype in ("true", "True"):
        return [f'{I}obj["{fname}"] = True']
    inner = _read_expr(f.ftype, "data", "pos")
    if inner:
        val_expr, pos_expr = inner
        return [
            f'{I}obj["{fname}"] = {val_expr}',
            f"{I}pos = {pos_expr}",
        ]
    return [f'{I}obj["{fname}"], pos = _tl._read_typed(data, pos, "{f.ftype}", _SCHEMA_BY_CID)']

# Serialization codegen helpers

# Struct format chars for unconditional fixed-width scalars.
# These can be batched into a single struct.pack call when contiguous.
_FIXED_FMT: dict[str, str] = {
    "int":    "i",
    "long":   "q",
    "double": "d",
}

# int128 / int256 are rare (only 2 total in the schema) and handled via
# .to_bytes() - not worth special-casing in the batch logic.


def _emit_serialize_body(c: Constructor) -> list[str]:
    """
    Return the lines (indented 8 spaces) of to_bytes(), using inlined
    struct.pack calls instead of calling the generic serialize_object()
    interpreter.

    Strategy:
      1. Emit CID as a fixed 4-byte little-endian uint32.
      2. For each flag group present, compute and emit the flags word.
         "flags" is always emitted before its fields; other groups
         (flags2, ...) are emitted lazily on first field encounter,
         matching TL wire order.
      3. For each field, emit the tightest possible pack call:
         - Runs of 2+ consecutive unconditional int/long/double fields
           (with no conditional fields or non-scalar fields interrupting)
           are collapsed into one struct.pack with a combined format string.
         - Single unconditional int / long / double: one struct.pack.
         - Unconditional string / bytes: _pack_bytes / _pack_string.
         - Unconditional true/True: nothing (zero-wire-size).
         - Unconditional Bool: _pack_bool.
         - Unconditional int128 / int256: .to_bytes() call.
         - Unconditional TL object or Vector: _tl.serialize(val, _SCHEMA).
         - Conditional (flagged) field: guard with bit-check, then same
           per-type dispatch.
    """
    I = "        "   # 8-space indent inside to_bytes

    lines: list[str] = []

    # CID
    cid_bytes = c.cid.to_bytes(4, "little")
    lines.append(f"{I}out = {cid_bytes!r}")

    # Determine which flag groups are present. Same rule as the
    # deserializer: a declared marker counts even with zero gated fields.
    flag_groups: list[str] = sorted(c.flag_markers, key=lambda g: c.flag_markers[g])

    if not flag_groups:
        # Fast path: no flags at all - just emit fields sequentially.
        lines.extend(_emit_fields_sequence(c.fields, conditional=False, indent=I))
        lines.append(f"{I}return out")
        return lines

    # Precompute each flag group's word from field presence.
    for grp in flag_groups:
        grp_fields = [f for f in c.fields if f.flag and f.flag.group == grp]
        parts = []
        for f in grp_fields:
            p = _safe_param(f.name)
            parts.append(f"(0 if self.{p} is None else (1 << {f.flag.bit}))")
        word_expr = " | ".join(parts) if parts else "0"
        lines.append(f"{I}_{grp}_word = {word_expr}")

    # Emit each flag word at its true schema position: a marker at index 0
    # writes first, but a mid-sequence marker, e.g. poll/wallPaper's "flags"
    # after "id", writes after the fields that precede it in the schema text.
    # Matches how the reader positions each flag word (see _emit_read_fields).
    markers = c.flag_markers

    def _emit_group_write(grp: str) -> None:
        lines.append(f"{I}out += _struct.pack('<I', _{grp}_word)")

    emitted_groups: set[str] = set()
    for grp in flag_groups:
        if markers.get(grp, 0) == 0 and grp not in emitted_groups:
            _emit_group_write(grp)
            emitted_groups.add(grp)

    # Walk fields, batching fixed-width unconditional runs
    i = 0
    fields = c.fields
    while i < len(fields):
        f = fields[i]

        # Emit any group whose marker sits exactly at this field index.
        for grp in flag_groups:
            if grp not in emitted_groups and markers.get(grp, 0) == i:
                _emit_group_write(grp)
                emitted_groups.add(grp)

        # Fall back: emit on first flagged-field encounter if no marker
        # position was recorded for its group (shouldn't happen, but safe).
        if f.flag and f.flag.group not in emitted_groups:
            grp = f.flag.group
            _emit_group_write(grp)
            emitted_groups.add(grp)

        # Try to batch consecutive unconditional fixed-width scalars  but
        # never cross a not-yet-emitted flags marker's position.
        if f.flag is None and f.ftype in _FIXED_FMT:
            next_marker = min(
                (pos for grp, pos in markers.items()
                 if grp not in emitted_groups and pos > i),
                default=len(fields),
            )
            run = _collect_fixed_run(fields[:next_marker], i)
            if len(run) >= 2:
                fmt = "<" + "".join(_FIXED_FMT[rf.ftype] for rf in run)
                args = ", ".join(f"self.{_safe_param(rf.name)}" for rf in run)
                lines.append(f"{I}out += _struct.pack('{fmt}', {args})")
                i += len(run)
                continue

        # Single field
        lines.extend(_emit_single_field(f, indent=I))
        i += 1

    lines.append(f"{I}return out")
    return lines


def _collect_fixed_run(fields: list[Field], start: int) -> list[Field]:
    """Return the longest run of unconditional fixed-width fields starting at start."""
    run = []
    for f in fields[start:]:
        if f.flag is None and f.ftype in _FIXED_FMT:
            run.append(f)
        else:
            break
    return run


def _emit_single_field(f: Field, indent: str) -> list[str]:
    """Emit the pack statement(s) for one field (conditional or not)."""
    I = indent
    p = _safe_param(f.name)

    if f.flag is not None:
        grp, bit = f.flag.group, f.flag.bit
        inner = _pack_expr(f.ftype, f"self.{p}")
        if inner is None:
            # true/True: zero wire size - the bit in the flags word is enough,
            # nothing to write. Skip emitting an if block entirely.
            return []
        lines = [f"{I}if _{grp}_word & (1 << {bit}):"]
        lines.append(f"{I}    out += {inner}")
        return lines

    expr = _pack_expr(f.ftype, f"self.{p}")
    if expr is None:
        return []   # true/True - zero wire size, unconditional
    return [f"{I}out += {expr}"]


def _pack_expr(ftype: str, access: str) -> str | None:
    """
    Return a Python expression that evaluates to bytes for one field value,
    or None for zero-wire-size types (true/True).
    """
    if ftype in ("true", "True"):
        return None
    if ftype == "int":
        return f"_struct.pack('<i', {access})"
    if ftype == "long":
        return f"_struct.pack('<q', {access})"
    if ftype == "double":
        return f"_struct.pack('<d', {access})"
    if ftype == "Bool":
        return f"_tl._pack_bool({access})"
    if ftype == "string":
        return f"_tl._pack_string({access})"
    if ftype == "bytes":
        return f"_tl._pack_bytes({access})"
    if ftype == "int128":
        return f"{access}.to_bytes(16, 'little', signed=False)"
    if ftype == "int256":
        return f"{access}.to_bytes(32, 'little', signed=False)"
    # Vector or TL object - fall back to generic serialize
    return f"_tl.serialize(_tl._resolve({access}), _SCHEMA)"


def _emit_fields_sequence(fields: list[Field], conditional: bool, indent: str) -> list[str]:
    """Emit all fields with batching (used for the no-flags fast path)."""
    lines = []
    i = 0
    while i < len(fields):
        f = fields[i]
        if f.flag is None and f.ftype in _FIXED_FMT:
            run = _collect_fixed_run(fields, i)
            if len(run) >= 2:
                fmt = "<" + "".join(_FIXED_FMT[rf.ftype] for rf in run)
                args = ", ".join(f"self.{_safe_param(rf.name)}" for rf in run)
                lines.append(f"{indent}out += _struct.pack('{fmt}', {args})")
                i += len(run)
                continue
        lines.extend(_emit_single_field(f, indent=indent))
        i += 1
    return lines


# Class renderer

def render_class(c: Constructor) -> str:
    cls = py_class(c.name)
    lines = [f"class {cls}:"]
    lines.append(f"    _CID = {c.cid:#010x}")
    lines.append("")

    required = [f for f in c.fields if f.flag is None]
    optional = [f for f in c.fields if f.flag is not None]

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

    # to_dict - keep for dict-style callers and _tl._resolve compatibility
    lines.append("")
    lines.append("    def to_dict(self) -> dict:")
    lines.append(f'        return {{"_": "{c.name}", **{{')
    for f in c.fields:
        lines.append(f'            "{f.name}": _tl._resolve(self.{_safe_param(f.name)}),')
    lines.append("        }}")

    # to_bytes - specialized, inlined struct.pack calls
    lines.append("")
    lines.append("    def to_bytes(self) -> bytes:")
    lines.extend(_emit_serialize_body(c))

    # from_bytes - specialized, inlined struct.unpack calls
    lines.append("")
    lines.append("    @classmethod")
    lines.append("    def from_bytes(cls, data: bytes, pos: int = 0) -> tuple[dict, int]:")
    lines.extend(_emit_read_body(c))

    lines.append("")
    preview = ", ".join(
        f"{f.name}={{self.{_safe_param(f.name)}!r}}"
        for f in c.fields[:4]
    )
    lines.append("    def __repr__(self) -> str:")
    lines.append(f'        return f"{cls}({preview})"')
    lines.append("")

    return "\n".join(lines)


# Schema builders (unchanged from Phase 2)

def build_schema(constructors: list[Constructor]) -> str:
    lines = ["_SCHEMA = {"]
    for c in constructors:
        fields_repr = ", ".join(
            f'("{f.name}", "{f.ftype}", {(f.flag.group, f.flag.bit) if f.flag else None!r})'
            for f in c.fields
        )
        lines.append(f'    "{c.name}": ({c.cid:#010x}, [{fields_repr}]),')
    lines.append("}")
    return "\n".join(lines)


def build_schema_by_cid(constructors: list[Constructor]) -> str:
    lines = ["_SCHEMA_BY_CID = {"]
    for c in constructors:
        fields_repr = ", ".join(
            f'("{f.name}", "{f.ftype}", {(f.flag.group, f.flag.bit) if f.flag else None!r})'
            for f in c.fields
        )
        lines.append(f'    {c.cid:#010x}: ("{c.name}", [{fields_repr}]),')
    lines.append("}")
    return "\n".join(lines)


# File writers

LICENSE = """\
# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# ferogram is a high-performance Telegram MTProto framework written in Rust.
# ferogram-py is a Python MTProto library powered by ferogram, delivering
# native Rust performance through a clean and Pythonic API for building
# Telegram clients, bots, and applications.
#
# Rust: https://github.com/ankit-chaubey/ferogram
# Python: https://github.com/ankit-chaubey/ferogram-py
#
# If you use or modify this code, keep this notice at the top of the file
# and include the LICENSE-MIT or LICENSE-APACHE file from this repository.
"""

NS_HEADER = """\
# auto-generated by ferogram raw codegen - do not edit

""" + LICENSE + """
from __future__ import annotations
import struct as _struct
from typing import Any
from ... import tl as _tl
from .._tl_schema import _SCHEMA, _SCHEMA_BY_CID

"""


def write_namespace_pkg(
    out_pkg: Path,
    grouped: dict[str, list[Constructor]],
    schema_str: str,
) -> None:
    out_pkg.mkdir(parents=True, exist_ok=True)

    for ns, constructors in sorted(grouped.items()):
        mod_file = out_pkg / f"{ns}.py"
        body = [NS_HEADER]
        for c in constructors:
            body.append(render_class(c))
        mod_file.write_text("\n".join(body))

    init_lines = [
        "# auto-generated - do not edit\n",
        "",
        LICENSE,
        "# Flat imports so both styles work:",
        "#   raw.functions.messages.GetHistory(...)   <- namespace style",
        "#   raw.functions.GetHistory(...)            <- flat style (convenience)",
        "",
    ]
    for ns in sorted(grouped):
        init_lines.append(f"from .{ns} import *  # noqa: F401,F403")
    init_lines.append("")
    init_lines.append("# namespace sub-modules")
    for ns in sorted(grouped):
        init_lines.append(f"from . import {ns}  # noqa: F401")
    init_lines.append("")

    (out_pkg / "__init__.py").write_text("\n".join(init_lines))


def generate(tl_path: Path, out_dir: Path) -> None:
    types, funcs = parse_tl(tl_path)
    layer = parse_layer(tl_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_constructors = types + funcs
    schema_str    = build_schema(all_constructors)
    schema_by_cid = build_schema_by_cid(types)

    (out_dir / "_tl_schema.py").write_text(
        "# auto-generated schema - do not edit\n\n"
        + LICENSE + "\n"
        + (f"LAYER = {layer}\n\n" if layer else "")
        + schema_str + "\n\n"
        + schema_by_cid + "\n"
    )

    type_ns: dict[str, list[Constructor]] = defaultdict(list)
    func_ns: dict[str, list[Constructor]] = defaultdict(list)
    for c in types:
        type_ns[ns_of(c.name)].append(c)
    for c in funcs:
        func_ns[ns_of(c.name)].append(c)

    write_namespace_pkg(out_dir / "types",     type_ns, schema_str)
    write_namespace_pkg(out_dir / "functions", func_ns, schema_str)

    (out_dir / "__init__.py").write_text(
        "# auto-generated - do not edit\n\n"
        + LICENSE + "\n"
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


