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


from __future__ import annotations
import struct
from typing import Any


def _pack_uint32(v: int) -> bytes: return struct.pack("<I", v & 0xFFFFFFFF)
def _pack_int32(v: int)  -> bytes: return struct.pack("<i", v)
def _pack_int64(v: int)  -> bytes: return struct.pack("<q", v)
def _pack_double(v: float) -> bytes: return struct.pack("<d", v)
def _pack_bool(v: bool)  -> bytes: return _pack_uint32(0x997275b5 if v else 0xbc799737)
def _pack_string(s: str) -> bytes: return _pack_bytes(s.encode())

def _pack_bytes(b: bytes) -> bytes:
    n = len(b)
    if n <= 253:
        header = bytes([n])
        pad = (4 - (n + 1) % 4) % 4
    else:
        header = bytes([254, n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF])
        pad = (4 - n % 4) % 4
    return header + b + b"\x00" * pad


def _resolve(v: Any) -> Any:
    """
    Accept typed TL object, raw dict, list of either, or primitive.
    Powers styles 1-3:
      dict style:     {"_": "inputPeerChannel", ...}  -> passthrough
      typed style:  InputPeerChannel(...)            -> .to_dict()
      callable style: await client(req)               -> same objects, __call__ handles it
    """
    if v is None:
        return None
    if hasattr(v, "to_dict"):
        return v.to_dict()
    if isinstance(v, list):
        return [_resolve(i) for i in v]
    return v


_BOOL_TRUE  = 0x997275b5
_BOOL_FALSE = 0xbc799737
_VECTOR_CID = 0x1cb5c415


# Schema field format: (name, ftype, flag)
# flag is None for unconditional fields, or (group, bit) for conditional ones.
# group is "flags", "flags2", etc. — any string matching the flag-word name in TL.
# bit is the 0-based bit index within that flag word.
#
# Old format (pre-Phase-2) stored flag_bit as a plain int for flags.X fields
# and ftype="flags2.N?inner" with flag=None for flags2 fields. The new format
# stores (group, bit) uniformly so tl.py never needs to inspect ftype strings
# for flag-group dispatch.


def serialize(obj: Any, schema: dict) -> bytes:
    if isinstance(obj, bool):
        return _pack_bool(obj)
    if isinstance(obj, int):
        if -(2**31) <= obj < 2**31:
            return _pack_int32(obj)
        return _pack_int64(obj)
    if isinstance(obj, float):
        return _pack_double(obj)
    if isinstance(obj, str):
        return _pack_string(obj)
    if isinstance(obj, bytes):
        return _pack_bytes(obj)
    if isinstance(obj, list):
        items = b"".join(serialize(i, schema) for i in obj)
        return _pack_uint32(0x1cb5c415) + _pack_uint32(len(obj)) + items
    if isinstance(obj, dict):
        return serialize_object(obj, schema)
    raise TypeError(f"cannot serialize {type(obj)}")


def serialize_object(obj: dict, schema: dict) -> bytes:
    name = obj["_"]
    if name not in schema:
        raise KeyError(f"unknown TL constructor: {name!r}")
    cid, fields = schema[name]
    out = _pack_uint32(cid)

    # Gather all flag groups present in this constructor and compute their words.
    # Iteration order: we need the flag words written in the order their first
    # conditional field appears in the field list, which matches the wire format.
    # We pre-compute all group words up front, then emit each word lazily on
    # first encounter (same lazy pattern as before, now generalised).
    flag_words: dict[str, int] = {}
    for fname, ftype, flag in fields:
        if flag is None:
            continue
        group, bit = flag
        if group not in flag_words:
            flag_words[group] = 0
        if obj.get(fname) is not None:
            flag_words[group] |= (1 << bit)

    # "flags" is always written first as a prefix word (TL convention).
    if "flags" in flag_words:
        out += _pack_uint32(flag_words["flags"])

    emitted: set[str] = {"flags"} if "flags" in flag_words else set()

    for fname, ftype, flag in fields:
        if flag is not None:
            group, bit = flag
            # Emit this group's flag word on its first appearance in field order.
            if group not in emitted:
                out += _pack_uint32(flag_words.get(group, 0))
                emitted.add(group)
            if not (flag_words.get(group, 0) & (1 << bit)):
                continue
        val = obj.get(fname)
        if val is None:
            continue
        out += _serialize_field(val, ftype, schema)

    return out


def _serialize_field(val: Any, ftype: str, schema: dict) -> bytes:
    LONG_TYPES   = {"long", "int64"}
    INT128_TYPES = {"int128"}
    INT256_TYPES = {"int256"}
    if ftype in LONG_TYPES:
        return _pack_int64(val)
    if ftype in INT128_TYPES:
        return val.to_bytes(16, "little", signed=False)
    if ftype in INT256_TYPES:
        return val.to_bytes(32, "little", signed=False)
    if ftype in ("true", "True"):
        return b""
    return serialize(val, schema)



def deserialize(data: bytes, schema_by_cid: dict) -> Any:
    return _read_object(data, 0, schema_by_cid)[0]


# Populated lazily on first deserialize call. Maps CID -> generated class
# with a from_bytes() classmethod, so _read_object() can dispatch straight
# to the specialized reader instead of walking the schema dict for every
# field of every nested object.
_CID_TO_CLASS: dict[int, type] | None = None


def _ensure_cid_map() -> dict[int, type]:
    global _CID_TO_CLASS
    if _CID_TO_CLASS is None:
        import importlib
        import pkgutil
        from ferogram.raw.generated import types as _types_pkg

        mapping: dict[int, type] = {}
        for _, modname, _ in pkgutil.walk_packages(
            path=_types_pkg.__path__,
            prefix=_types_pkg.__name__ + ".",
        ):
            mod = importlib.import_module(modname)
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and hasattr(obj, "from_bytes"):
                    cid = getattr(obj, "_CID", None)
                    if cid is not None:
                        mapping[cid] = obj
        _CID_TO_CLASS = mapping
    return _CID_TO_CLASS


def _read_object(data: bytes, pos: int, schema_by_cid: dict) -> tuple[Any, int]:
    """
    Read a CID-prefixed TL object from data[pos:].

    Dispatches to the generated class's specialized from_bytes() via
    _CID_TO_CLASS when the CID is known. Falls back to the generic
    schema-dict walk (_read_value) for anything not in the dispatch
    table — unknown/forward-compat CIDs, and MTProto-internal
    constructors that aren't part of api.tl.
    """
    cid, new_pos = _read_uint32(data, pos)

    if cid == _BOOL_TRUE:
        return True, new_pos
    if cid == _BOOL_FALSE:
        return False, new_pos

    if cid == _VECTOR_CID:
        count, item_pos = _read_uint32(data, new_pos)
        items = []
        for _ in range(count):
            item, item_pos = _read_object(data, item_pos, schema_by_cid)
            items.append(item)
        return items, item_pos

    cls = _ensure_cid_map().get(cid)
    if cls is not None:
        return cls.from_bytes(data, new_pos)

    return _read_value(data, pos, schema_by_cid)


def _read_uint32(data: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from("<I", data, pos)[0], pos + 4


def _read_int32(data: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from("<i", data, pos)[0], pos + 4


def _read_int64(data: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from("<q", data, pos)[0], pos + 8


def _read_double(data: bytes, pos: int) -> tuple[float, int]:
    return struct.unpack_from("<d", data, pos)[0], pos + 8


def _read_bytes(data: bytes, pos: int) -> tuple[bytes, int]:
    first = data[pos]
    if first <= 253:
        n = first
        start = pos + 1
        pad = (4 - (n + 1) % 4) % 4
    else:
        n = data[pos+1] | (data[pos+2] << 8) | (data[pos+3] << 16)
        start = pos + 4
        pad = (4 - n % 4) % 4
    return data[start:start+n], start + n + pad


def _read_value(data: bytes, pos: int, schema: dict) -> tuple[Any, int]:
    cid, pos = _read_uint32(data, pos)

    if cid == _BOOL_TRUE:  return True,  pos
    if cid == _BOOL_FALSE: return False, pos

    if cid == _VECTOR_CID:
        count, pos = _read_uint32(data, pos)
        items = []
        for _ in range(count):
            item, pos = _read_object(data, pos, schema)
            items.append(item)
        return items, pos

    if cid not in schema:
        return {"_cid": hex(cid)}, pos

    name, fields = schema[cid]
    obj: dict[str, Any] = {"_": name}

    # Read "flags" word first if any field is gated on it.
    flag_words: dict[str, int] = {}
    if any(f[2] is not None and f[2][0] == "flags" for f in fields):
        flag_words["flags"], pos = _read_uint32(data, pos)

    for fname, ftype, flag in fields:
        if flag is not None:
            group, bit = flag
            # Lazily read each new flag group word on first encounter.
            if group not in flag_words:
                flag_words[group], pos = _read_uint32(data, pos)
            if not (flag_words[group] & (1 << bit)):
                continue
            if ftype in ("true", "True"):
                obj[fname] = True
                continue
            val, pos = _read_typed(data, pos, ftype, schema)
            obj[fname] = val
            continue

        if ftype in ("true", "True"):
            obj[fname] = True
            continue
        val, pos = _read_typed(data, pos, ftype, schema)
        obj[fname] = val

    return obj, pos


def _read_typed(data: bytes, pos: int, ftype: str, schema: dict) -> tuple[Any, int]:  # noqa: E302 (called by generated from_bytes)
    if ftype == "int":    return _read_int32(data, pos)
    if ftype == "long":   return _read_int64(data, pos)
    if ftype == "double": return _read_double(data, pos)
    if ftype in ("string",):
        b, pos = _read_bytes(data, pos)
        try:
            return b.decode(), pos
        except UnicodeDecodeError:
            return b, pos
    if ftype == "bytes":  return _read_bytes(data, pos)
    if ftype == "Bool":
        cid, pos = _read_uint32(data, pos)
        return cid == _BOOL_TRUE, pos
    if ftype.startswith("Vector<") or ftype.startswith("vector<"):
        inner = ftype[7:-1]
        cid, pos = _read_uint32(data, pos)  # _VECTOR_CID
        count, pos = _read_uint32(data, pos)
        items = []
        for _ in range(count):
            item, pos = _read_typed(data, pos, inner, schema)
            items.append(item)
        return items, pos
    return _read_object(data, pos, schema)


def parse_markdown(text: str) -> tuple[str, list]:
    """Strip basic markdown (* _ ` ~) and return (plain_text, entities)."""
    import re
    entities = []
    pos = 0
    plain = []
    pattern = re.compile(r'(\*\*(.+?)\*\*|\*(.+?)\*|__(.+?)__|_(.+?)_|`(.+?)`|~~(.+?)~~)', re.DOTALL)
    last = 0
    for m in pattern.finditer(text):
        plain.append(text[last:m.start()])
        inner = next(g for g in m.groups()[1:] if g is not None)
        start = sum(len(s) for s in plain)
        plain.append(inner)
        length = len(inner)
        raw = m.group(0)
        if raw.startswith("**"):
            entities.append({"_": "messageEntityBold", "offset": start, "length": length})
        elif raw.startswith("*") or raw.startswith("_"):
            entities.append({"_": "messageEntityItalic", "offset": start, "length": length})
        elif raw.startswith("`"):
            entities.append({"_": "messageEntityCode", "offset": start, "length": length})
        elif raw.startswith("~~"):
            entities.append({"_": "messageEntityStrike", "offset": start, "length": length})
        last = m.end()
    plain.append(text[last:])
    return "".join(plain), entities


def parse_html(text: str) -> tuple[str, list]:
    """Strip basic HTML tags (<b> <i> <code> <s> <u> <a>) and return (plain_text, entities)."""
    import re
    tag_map = {
        "b": "messageEntityBold", "strong": "messageEntityBold",
        "i": "messageEntityItalic", "em": "messageEntityItalic",
        "code": "messageEntityCode", "pre": "messageEntityPre",
        "s": "messageEntityStrike", "strike": "messageEntityStrike", "del": "messageEntityStrike",
        "u": "messageEntityUnderline",
    }
    entities: list = []
    plain_parts: list = []
    pos = 0
    stack: list = []  # (entity_type, plain_start, url)
    i = 0
    src = text
    while i < len(src):
        if src[i] != "<":
            plain_parts.append(src[i])
            i += 1
            continue
        end = src.find(">", i)
        if end == -1:
            plain_parts.append(src[i])
            i += 1
            continue
        tag_raw = src[i+1:end]
        i = end + 1
        closing = tag_raw.startswith("/")
        tag_body = tag_raw.lstrip("/").split()[0].lower()
        if closing:
            for j in range(len(stack) - 1, -1, -1):
                etype, pstart, url = stack[j]
                if tag_map.get(tag_body) == etype or tag_body == "a":
                    cur_pos = sum(len(p) for p in plain_parts)
                    length = cur_pos - pstart
                    if length > 0:
                        ent: dict = {"_": etype, "offset": pstart, "length": length}
                        if url:
                            ent["url"] = url
                        entities.append(ent)
                    stack.pop(j)
                    break
        else:
            etype = tag_map.get(tag_body)
            url = ""
            if tag_body == "a":
                etype = "messageEntityTextUrl"
                m = re.search(r'href=["\'"]([^"\']+)["\']', tag_raw)
                url = m.group(1) if m else ""
            if etype:
                pstart = sum(len(p) for p in plain_parts)
                stack.append((etype, pstart, url))
    return "".join(plain_parts), entities
