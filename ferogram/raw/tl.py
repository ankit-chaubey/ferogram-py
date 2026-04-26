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

# TL serializer and deserializer for Telegram API types.
# Handles all primitive TL types: int32, int64, int128, int256,
# double, bool, string, bytes, vector, and nested objects.

from __future__ import annotations
import struct
from typing import Any


# primitives

def _pack_int32(v: int) -> bytes:
    return struct.pack("<i", v)

def _pack_uint32(v: int) -> bytes:
    return struct.pack("<I", v)

def _pack_int64(v: int) -> bytes:
    return struct.pack("<q", v)

def _pack_double(v: float) -> bytes:
    return struct.pack("<d", v)

def _pack_bool(v: bool) -> bytes:
    return _pack_uint32(0x997275b5 if v else 0xbc799737)

def _pack_bytes(data: bytes) -> bytes:
    n = len(data)
    if n <= 253:
        header = bytes([n])
        pad = (-(n + 1)) % 4
    else:
        header = bytes([254]) + struct.pack("<I", n)[:3]
        pad = (-n) % 4
    return header + data + b"\x00" * pad

def _pack_string(s: str) -> bytes:
    return _pack_bytes(s.encode())

def _pack_int128(v: int) -> bytes:
    return v.to_bytes(16, "little", signed=False)

def _pack_int256(v: int) -> bytes:
    return v.to_bytes(32, "little", signed=False)


# serializer

def serialize(obj: Any, schema: dict) -> bytes:
    """Serialize a Python dict or primitive using TL schema."""
    if isinstance(obj, bool):
        return _pack_bool(obj)
    if isinstance(obj, int):
        return _pack_int32(obj)
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
    """Serialize a TL object dict with a '_' constructor key."""
    name = obj["_"]
    if name not in schema:
        raise KeyError(f"unknown TL constructor: {name!r}")
    cid, fields = schema[name]
    out = _pack_uint32(cid)
    # flags field: compute bitmask from optional fields present
    flags = 0
    flag_fields = [(fname, ftype, fbit) for fname, ftype, fbit in fields if fbit is not None]
    for fname, ftype, fbit in flag_fields:
        if obj.get(fname) is not None:
            flags |= (1 << fbit)
    if any(True for _, _, fbit in fields if fbit is not None):
        out += _pack_uint32(flags)
    for fname, ftype, fbit in fields:
        if fbit is not None:
            if obj.get(fname) is None:
                continue
            if ftype == "true":
                continue  # flag-only, no value serialized
        val = obj.get(fname)
        if val is None:
            raise ValueError(f"missing required field {fname!r} on {name!r}")
        out += _serialize_typed(val, ftype, schema)
    return out


def _serialize_typed(val: Any, ftype: str, schema: dict) -> bytes:
    if ftype in ("int", "int32"):
        return _pack_int32(val)
    if ftype in ("long", "int64"):
        return _pack_int64(val)
    if ftype == "int128":
        return _pack_int128(val)
    if ftype == "int256":
        return _pack_int256(val)
    if ftype == "double":
        return _pack_double(val)
    if ftype == "Bool":
        return _pack_bool(val)
    if ftype == "string":
        return _pack_string(val)
    if ftype == "bytes":
        return _pack_bytes(val)
    if ftype.startswith("Vector<") or ftype.startswith("vector<"):
        inner = ftype[7:-1]
        items = b"".join(_serialize_typed(i, inner, schema) for i in val)
        return _pack_uint32(0x1cb5c415) + _pack_uint32(len(val)) + items
    # nested TL object
    return serialize_object(val, schema)


# deserializer

class Reader:
    def __init__(self, data: bytes) -> None:
        self._d = data
        self._pos = 0

    def remaining(self) -> int:
        return len(self._d) - self._pos

    def read(self, n: int) -> bytes:
        chunk = self._d[self._pos:self._pos + n]
        if len(chunk) < n:
            raise EOFError("unexpected end of TL buffer")
        self._pos += n
        return chunk

    def read_uint32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def read_int32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def read_int64(self) -> int:
        return struct.unpack("<q", self.read(8))[0]

    def read_double(self) -> float:
        return struct.unpack("<d", self.read(8))[0]

    def read_int128(self) -> int:
        return int.from_bytes(self.read(16), "little")

    def read_int256(self) -> int:
        return int.from_bytes(self.read(32), "little")

    def read_bytes(self) -> bytes:
        first = self.read(1)[0]
        if first <= 253:
            n = first
            data = self.read(n)
            padding = (-(n + 1)) % 4
        else:
            b1, b2, b3 = self.read(3)
            n = b1 | (b2 << 8) | (b3 << 16)
            data = self.read(n)
            padding = (-n) % 4
        if padding:
            self.read(padding)
        return data

    def read_string(self) -> str:
        return self.read_bytes().decode()


BOOL_TRUE  = 0x997275b5
BOOL_FALSE = 0xbc799737
VECTOR_CID = 0x1cb5c415


def deserialize(data: bytes, schema_by_cid: dict) -> Any:
    r = Reader(data)
    return _read_value(r, schema_by_cid)


def _read_value(r: Reader, schema_by_cid: dict) -> Any:
    cid = r.read_uint32()
    if cid == BOOL_TRUE:
        return True
    if cid == BOOL_FALSE:
        return False
    if cid == VECTOR_CID:
        count = r.read_uint32()
        return [_read_value(r, schema_by_cid) for _ in range(count)]
    if cid not in schema_by_cid:
        raise ValueError(f"unknown constructor id: {cid:#010x}")
    name, fields = schema_by_cid[cid]
    obj: dict = {"_": name}
    flags = 0
    has_flags = any(fbit is not None for _, _, fbit in fields)
    if has_flags:
        flags = r.read_uint32()
    for fname, ftype, fbit in fields:
        if fbit is not None:
            if not (flags & (1 << fbit)):
                obj[fname] = None
                continue
            if ftype == "true":
                obj[fname] = True
                continue
        obj[fname] = _read_typed(r, ftype, schema_by_cid)
    return obj


def _read_typed(r: Reader, ftype: str, schema_by_cid: dict) -> Any:
    if ftype in ("int", "int32"):
        return r.read_int32()
    if ftype in ("long", "int64"):
        return r.read_int64()
    if ftype == "int128":
        return r.read_int128()
    if ftype == "int256":
        return r.read_int256()
    if ftype == "double":
        return r.read_double()
    if ftype == "Bool":
        cid = r.read_uint32()
        return cid == BOOL_TRUE
    if ftype == "string":
        return r.read_string()
    if ftype == "bytes":
        return r.read_bytes()
    if ftype.startswith("Vector<") or ftype.startswith("vector<"):
        inner = ftype[7:-1]
        cid = r.read_uint32()
        assert cid == VECTOR_CID, f"expected vector cid, got {cid:#010x}"
        count = r.read_uint32()
        return [_read_typed(r, inner, schema_by_cid) for _ in range(count)]
    return _read_value(r, schema_by_cid)
