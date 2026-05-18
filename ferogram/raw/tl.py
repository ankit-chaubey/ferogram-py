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


def _parse_flags2_ftype(ftype: str) -> tuple[int, str]:
    """Parse "flags2.N?inner" -> (bit, inner_type)."""
    sep = ftype.index("?")
    return int(ftype[7:sep]), ftype[sep + 1:]


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

    # Compute flags (flags.X fields have fbit != None).
    flag_fields = [(fn, ft, fb) for fn, ft, fb in fields if fb is not None]
    flags = 0
    for fname, ftype, fbit in flag_fields:
        if obj.get(fname) is not None:
            flags |= (1 << fbit)
    if flag_fields:
        out += _pack_uint32(flags)

    # Compute flags2 (fields whose ftype starts with "flags2.").
    flags2_fields = [
        (fn, ft) for fn, ft, _ in fields
        if isinstance(ft, str) and ft.startswith("flags2.")
    ]
    flags2 = 0
    for fname, ftype in flags2_fields:
        bit, _ = _parse_flags2_ftype(ftype)
        if obj.get(fname) is not None:
            flags2 |= (1 << bit)

    flags2_written = False

    for fname, ftype, fbit in fields:
        # flags2.X?inner field: write the flags2 word on first encounter, then
        # write the inner value only when the corresponding bit is set.
        if isinstance(ftype, str) and ftype.startswith("flags2."):
            if not flags2_written:
                out += _pack_uint32(flags2)
                flags2_written = True
            bit, inner = _parse_flags2_ftype(ftype)
            if not (flags2 & (1 << bit)):
                continue
            val = obj.get(fname)
            if val is not None:
                out += _serialize_field(val, inner, schema)
            continue

        if fbit is not None:
            if obj.get(fname) is None:
                continue
        val = obj.get(fname)
        if val is None:
            continue
        out += _serialize_field(val, ftype, schema)

    return out


def _serialize_field(val: Any, ftype: str, schema: dict) -> bytes:
    LONG_TYPES  = {"long", "int64"}
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
    result, _ = _read_value(data, 0, schema_by_cid)
    return result


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

    BOOL_TRUE  = 0x997275b5
    BOOL_FALSE = 0xbc799737
    VECTOR_CID = 0x1cb5c415

    if cid == BOOL_TRUE:  return True,  pos
    if cid == BOOL_FALSE: return False, pos

    if cid == VECTOR_CID:
        count, pos = _read_uint32(data, pos)
        items = []
        for _ in range(count):
            item, pos = _read_value(data, pos, schema)
            items.append(item)
        return items, pos

    if cid not in schema:
        return {"_cid": hex(cid)}, pos

    name, fields = schema[cid]
    obj: dict[str, Any] = {"_": name}

    # Read flags word if any field is gated on flags.X.
    flags = 0
    if any(fb is not None for _, _, fb in fields):
        flags, pos = _read_uint32(data, pos)

    # flags2 is a second flags word that appears inline in the field sequence,
    # just before the first flags2.X?... field. The generated schema omits the
    # flags2:# marker (FIELD_RE doesn't match "#") and encodes the conditionality
    # as ftype="flags2.N?inner" with fbit=None. We read the flags2 word lazily
    # on the first flags2.X field encountered, which matches the wire position.
    flags2 = 0
    flags2_read = False

    for fname, ftype, fbit in fields:
        # flags2.X?inner conditional field.
        if isinstance(ftype, str) and ftype.startswith("flags2."):
            if not flags2_read:
                flags2, pos = _read_uint32(data, pos)
                flags2_read = True
            bit, inner = _parse_flags2_ftype(ftype)
            if not (flags2 & (1 << bit)):
                continue
            if inner in ("true", "True"):
                obj[fname] = True
            else:
                val, pos = _read_typed(data, pos, inner, schema)
                obj[fname] = val
            continue

        # Normal flags.X conditional or unconditional field.
        if fbit is not None and not (flags & (1 << fbit)):
            continue
        if ftype in ("true", "True"):
            obj[fname] = True
            continue
        val, pos = _read_typed(data, pos, ftype, schema)
        obj[fname] = val

    return obj, pos


def _read_typed(data: bytes, pos: int, ftype: str, schema: dict) -> tuple[Any, int]:
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
        return cid == 0x997275b5, pos
    if ftype.startswith("Vector<") or ftype.startswith("vector<"):
        inner = ftype[7:-1]
        cid, pos = _read_uint32(data, pos)  # 0x1cb5c415
        count, pos = _read_uint32(data, pos)
        items = []
        for _ in range(count):
            item, pos = _read_typed(data, pos, inner, schema)
            items.append(item)
        return items, pos
    return _read_value(data, pos, schema)
