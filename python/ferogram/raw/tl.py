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


from __future__ import annotations
import html as _html
import keyword as _keyword
import re
import struct
from typing import Any


class TLDecodeError(ValueError):
    pass


class TLEncodeError(ValueError):
    pass


def _u16(s: str) -> int:
    if s.isascii():
        return len(s)
    return len(s.encode("utf-16-le")) // 2


_S_u32 = struct.Struct("<I")
_pack_u32_raw = _S_u32.pack
_pack_int32 = struct.Struct("<i").pack
_pack_int64 = struct.Struct("<q").pack
_pack_double = struct.Struct("<d").pack
_TRUE_B = b"\xb5\x75\x72\x99"
_FALSE_B = b"\x37\x97\x79\xbc"
_PAD = (b"", b"\x00\x00\x00", b"\x00\x00", b"\x00")


def _pack_uint32(v: int) -> bytes:
    return _pack_u32_raw(v & 0xFFFFFFFF)


def _pack_bool(v: bool) -> bytes:
    return _TRUE_B if v else _FALSE_B


def _pack_string(s: str) -> bytes:
    return _pack_bytes(s.encode() if isinstance(s, str) else bytes(s))


def _pack_bytes(b: bytes) -> bytes:
    n = len(b)
    if n <= 253:
        return bytes((n,)) + b + _PAD[(n + 1) & 3]
    if n >= 1 << 24:
        raise TLEncodeError(f"bytes value of {n} bytes exceeds the 16 MiB TL limit")
    return bytes((254, n & 255, (n >> 8) & 255, n >> 16)) + b + _PAD[n & 3]


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


_VECTOR_HDR = b"\x15\xc4\xb5\x1c"
_BOOL_TRUE  = 0x997275b5
_BOOL_FALSE = 0xbc799737
_VECTOR_CID = 0x1cb5c415
_LONG_TYPES   = {"long", "int64"}
_INT128_TYPES = {"int128"}
_INT256_TYPES = {"int256"}
_TRUE_TYPES   = {"true", "True"}


# Schema field format: (name, ftype, flag)
# flag is None for unconditional fields, or (group, bit) for conditional ones.
# group is "flags", "flags2", etc. - any string matching the flag-word name in TL.
# bit is the 0-based bit index within that flag word.



def serialize(obj: Any, schema: dict) -> bytes:
    if type(obj) is dict:
        return serialize_object(obj, schema)
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


# Peer-family constructors that can stand in for each other, keyed by the declared
# field type. The wire format needs the constructor of the declared type: sending an
# `inputPeerChannel` where an `InputChannel` is expected puts the wrong id on the wire.
# Each pair has identical fields, so the swap only changes the constructor.
_PEER_COERCE: dict[str, dict[str, str]] = {
    "InputChannel": {
        "inputPeerChannel": "inputChannel",
        "inputPeerChannelFromMessage": "inputChannelFromMessage",
        "inputPeerEmpty": "inputChannelEmpty",
    },
    "InputUser": {
        "inputPeerUser": "inputUser",
        "inputPeerUserFromMessage": "inputUserFromMessage",
        "inputPeerSelf": "inputUserSelf",
        "inputPeerEmpty": "inputUserEmpty",
    },
    "InputPeer": {
        "inputChannel": "inputPeerChannel",
        "inputChannelFromMessage": "inputPeerChannelFromMessage",
        "inputChannelEmpty": "inputPeerEmpty",
        "inputUser": "inputPeerUser",
        "inputUserFromMessage": "inputPeerUserFromMessage",
        "inputUserSelf": "inputPeerSelf",
        "inputUserEmpty": "inputPeerEmpty",
    },
}


def _coerce_peer(val: Any, ftype: str) -> Any:
    if type(val) is not dict:
        if hasattr(val, "to_dict"):
            val = val.to_dict()
        if not isinstance(val, dict):
            return val
    target = _PEER_COERCE[ftype].get(val.get("_"))
    if target is not None:
        return {**val, "_": target}
    return val


def _ser(v: Any, schema: dict) -> bytes:
    if type(v) is dict:
        return serialize_object(v, schema)
    if getattr(v, "_CID", None) is not None:
        return v.to_bytes()
    return serialize(_resolve(v), schema)


def _ser_peer(v: Any, ftype: str, schema: dict) -> bytes:
    if type(v) is dict:
        target = _PEER_COERCE[ftype].get(v.get("_"))
        if target is not None:
            v = {**v, "_": target}
        return serialize_object(v, schema)
    return _ser(_coerce_peer(v, ftype), schema)


def _coerce_peer_fields(obj: dict, fields: list) -> dict:
    """Return `obj` with peer-typed fields rewritten to the constructor their type needs."""
    changed: dict | None = None
    for fname, ftype, _flag in fields:
        val = obj.get(fname)
        if val is None:
            continue
        if ftype in _PEER_COERCE:
            new = _coerce_peer(val, ftype)
            if new is val:
                continue
        elif ftype.startswith("Vector<") and ftype[7:-1] in _PEER_COERCE and isinstance(val, list):
            inner = ftype[7:-1]
            new = [_coerce_peer(v, inner) for v in val]
            if all(a is b for a, b in zip(new, val)):
                continue
        else:
            continue
        if changed is None:
            changed = dict(obj)
        changed[fname] = new
    return obj if changed is None else changed


class _CtorInfo:
    __slots__ = ("cid", "fields", "allowed", "required", "groups", "coerce", "renames", "cls")


_INFO: dict[str, _CtorInfo] = {}


def _ctor_info(name: str, schema: dict) -> _CtorInfo:
    info = _INFO.get(name)
    if info is not None:
        return info
    if name not in schema:
        raise KeyError(f"unknown TL constructor: {name!r}")
    cid, fields = schema[name]
    allowed, required, groups = _field_info(name, fields)
    info = _CtorInfo()
    info.cid = cid
    info.fields = fields
    info.allowed = allowed | {"_"}
    info.required = required
    info.groups = groups
    specs = []
    for fname, ftype, _flag in fields:
        if ftype in _PEER_COERCE:
            specs.append((fname, ftype, False))
        elif ftype.startswith("Vector<") and ftype[7:-1] in _PEER_COERCE:
            specs.append((fname, ftype[7:-1], True))
    info.coerce = tuple(specs)
    info.renames = any(f[0] in _PY_KEYWORDS for f in fields)
    info.cls = _load_class(name)
    if schema is _schema_ref():
        _INFO[name] = info
    return info


def _schema_ref() -> dict:
    from .generated._tl_schema import _SCHEMA
    return _SCHEMA


def _coerce_specs(obj: dict, specs: tuple) -> dict:
    changed: dict | None = None
    for fname, ftype, is_vector in specs:
        val = obj.get(fname)
        if val is None:
            continue
        if is_vector:
            if not isinstance(val, list):
                continue
            new = [_coerce_peer(v, ftype) for v in val]
            if all(a is b for a, b in zip(new, val)):
                continue
        else:
            new = _coerce_peer(val, ftype)
            if new is val:
                continue
        if changed is None:
            changed = dict(obj)
        changed[fname] = new
    return obj if changed is None else changed


def serialize_object(obj: dict, schema: dict) -> bytes:
    name = obj["_"]
    info = _INFO.get(name) or _ctor_info(name, schema)
    if info.coerce and info.cls is None:
        obj = _coerce_specs(obj, info.coerce)
    extra = obj.keys() - info.allowed
    if extra:
        raise TLEncodeError(f"{name}: unknown field(s) {sorted(extra)}")
    for f in info.required:
        if obj.get(f) is None:
            missing = [m for m in info.required if obj.get(m) is None]
            raise TLEncodeError(f"{name}: missing required field(s) {missing}")
    if info.groups:
        for members, valued, flags_only in info.groups:
            if any((obj.get(m) is True) if m in flags_only else (obj.get(m) is not None) for m in members):
                absent = [v for v in valued if obj.get(v) is None]
                if absent:
                    raise TLEncodeError(f"{name}: {list(members)} share one flag and must be provided together, missing {absent}")

    cls = info.cls
    if cls is not None:
        if info.renames:
            kw = {(k + "_" if k in _PY_KEYWORDS else k): v for k, v in obj.items() if k != "_"}
        else:
            kw = dict(obj)
            del kw["_"]
        try:
            inst = cls(**kw)
        except TypeError:
            inst = None
        if inst is not None:
            return inst.to_bytes()
        if info.coerce:
            obj = _coerce_specs(obj, info.coerce)

    return _serialize_generic(obj, info.cid, info.fields, schema)


def _serialize_generic(obj: dict, cid: int, fields: list, schema: dict) -> bytes:
    chunks: list[bytes] = [_pack_uint32(cid)]
    flag_words: dict[str, int] = {}
    for fname, ftype, flag in fields:
        if flag is None:
            continue
        group, bit = flag
        flag_words.setdefault(group, 0)
        val = obj.get(fname)
        if (val if ftype in ("true", "True") else val is not None):
            flag_words[group] |= (1 << bit)

    at: dict[int, list[str]] = {}
    for group, idx in _flag_markers(obj.get("_", "")).items():
        at.setdefault(idx, []).append(group)
    emitted: set[str] = set()

    for i, (fname, ftype, flag) in enumerate(fields):
        for group in at.get(i, ()):
            chunks.append(_pack_uint32(flag_words.get(group, 0)))
            emitted.add(group)
        if flag is not None:
            group, bit = flag
            if group not in emitted:
                chunks.append(_pack_uint32(flag_words.get(group, 0)))
                emitted.add(group)
            if not (flag_words.get(group, 0) & (1 << bit)):
                continue
        val = obj.get(fname)
        if val is None:
            continue
        chunks.append(_serialize_field(val, ftype, schema))
    for group in at.get(len(fields), ()):
        chunks.append(_pack_uint32(flag_words.get(group, 0)))

    return b"".join(chunks)


# constructor name -> generated class; populated lazily on first serialize call.
# Covers both raw/generated/types (nested field values, e.g. inputPeerChannel)
# and raw/generated/functions (top-level RPC requests). Keyed by name (not CID,
# unlike _CID_TO_CLASS below) since that's what obj["_"] carries.
_NAME_TO_CLASS: dict[str, type] | None = None

_FIELD_INFO: dict[str, tuple[frozenset, tuple, tuple]] = {}

_PY_KEYWORDS = frozenset(_keyword.kwlist) | {"True", "False", "None", "self"}

_MARKERS: dict | None = None
_NO_MARKERS: dict = {}


def _flag_markers(name: str) -> dict:
    global _MARKERS
    if _MARKERS is None:
        from .generated import _tl_schema
        _MARKERS = getattr(_tl_schema, "_FLAG_MARKERS", {})
    return _MARKERS.get(name, _NO_MARKERS)


def _field_info(name: str, fields: list) -> tuple[frozenset, tuple, tuple]:
    info = _FIELD_INFO.get(name)
    if info is None:
        members: dict[tuple, list[tuple[str, bool]]] = {}
        for fname, ftype, flag in fields:
            if flag is not None:
                members.setdefault(flag, []).append((fname, ftype in ("true", "True")))
        groups = tuple(
            (tuple(n for n, _ in m), tuple(n for n, t in m if not t), frozenset(n for n, t in m if t))
            for m in members.values()
            if len(m) > 1 and any(not t for _, t in m)
        )
        info = (
            frozenset(f[0] for f in fields),
            tuple(f[0] for f in fields if f[2] is None and f[1] not in ("true", "True")),
            groups,
        )
        _FIELD_INFO[name] = info
    return info


_CLASS_CACHE: dict[str, type | None] = {}


def _load_class(name: str) -> type | None:
    cls = _CLASS_CACHE.get(name)
    if cls is None and name not in _CLASS_CACHE:
        import importlib
        from .generated import _tl_schema
        entry = _tl_schema._CLASS_INDEX.get(name)
        if entry is not None:
            module = importlib.import_module(f"{__package__}.generated.{entry[0]}.{entry[1]}")
            cls = getattr(module, entry[2])
        _CLASS_CACHE[name] = cls
    return cls


def _ensure_serialize_dispatch() -> dict[str, type]:
    global _NAME_TO_CLASS
    if _NAME_TO_CLASS is None:
        from .generated import _tl_schema
        _NAME_TO_CLASS = {n: _load_class(n) for n in _tl_schema._CLASS_INDEX}
    return _NAME_TO_CLASS


def _serialize_field(val: Any, ftype: str, schema: dict) -> bytes:
    if ftype in _LONG_TYPES:
        return _pack_int64(val)
    if ftype == "int":
        return _pack_int32(val)
    if ftype == "double":
        return _pack_double(float(val))
    if ftype == "Bool":
        return _pack_bool(val)
    if ftype == "string":
        return _pack_string(val)
    if ftype == "bytes":
        return _pack_bytes(val.encode() if isinstance(val, str) else bytes(val))
    if ftype in _INT128_TYPES:
        return val.to_bytes(16, "little", signed=False)
    if ftype in _INT256_TYPES:
        return val.to_bytes(32, "little", signed=False)
    if ftype in _TRUE_TYPES:
        return b""
    if ftype.startswith(("Vector<", "vector<")):
        inner = ftype[7:-1]
        n = len(val)
        if inner in _LONG_TYPES:
            body = struct.pack(f"<{n}q", *val)
        elif inner == "int":
            body = struct.pack(f"<{n}i", *val)
        elif inner in _PEER_COERCE:
            body = b"".join(_ser_peer(v, inner, schema) for v in val)
        else:
            body = b"".join(_serialize_field(v, inner, schema) for v in val)
        return _VECTOR_HDR + _pack_u32_raw(n) + body
    if ftype in _PEER_COERCE:
        return _ser_peer(val, ftype, schema)
    return _ser(val, schema)


def deserialize(data: bytes, schema_by_cid: dict) -> Any:
    rd = _CID_READERS.get(_u32(data, 0)[0]) if len(data) >= 4 else None
    if rd is not None:
        try:
            return rd(data, 4)[0]
        except TLDecodeError:
            raise
        except (struct.error, IndexError) as e:
            raise TLDecodeError(f"truncated or malformed TL data: {e}") from e
    if len(data) >= 4:
        cid = struct.unpack_from("<I", data, 0)[0]
        if cid not in (_BOOL_TRUE, _BOOL_FALSE, _VECTOR_CID) and cid not in schema_by_cid:
            return {"_cid": hex(cid), "_raw": bytes(data[4:])}
    try:
        return _read_object(data, 0, schema_by_cid)[0]
    except TLDecodeError:
        raise
    except (struct.error, IndexError) as e:
        raise TLDecodeError(f"truncated or malformed TL data: {e}") from e


def _check_count(count: int, data: bytes, pos: int) -> None:
    if count * 4 > len(data) - pos:
        raise TLDecodeError(f"vector of {count} items overruns buffer at offset {pos}")


# CID -> generated class; populated lazily on first deserialize call.
_CID_TO_CLASS: dict[int, type] | None = None


def _ensure_cid_map() -> dict[int, type]:
    global _CID_TO_CLASS
    if _CID_TO_CLASS is None:
        from .generated._tl_schema import _SCHEMA_BY_CID
        mapping: dict[int, type] = {}
        for cid, (name, _fields) in _SCHEMA_BY_CID.items():
            cls = _load_class(name)
            if cls is not None:
                mapping[cid] = cls
                if cid not in (_BOOL_TRUE, _BOOL_FALSE, _VECTOR_CID):
                    _CID_READERS[cid] = cls.from_bytes
        _CID_TO_CLASS = mapping
    return _CID_TO_CLASS


_u32 = struct.Struct("<I").unpack_from
_i32 = struct.Struct("<i").unpack_from
_i64 = struct.Struct("<q").unpack_from
_f64 = struct.Struct("<d").unpack_from
_CID_READERS: dict[int, Any] = {}


def _read_object(data: bytes, pos: int, schema_by_cid: dict) -> tuple[Any, int]:
    cid = _u32(data, pos)[0]
    new_pos = pos + 4

    rd = _CID_READERS.get(cid)
    if rd is not None:
        return rd(data, new_pos)

    if cid == _BOOL_TRUE:
        return True, new_pos
    if cid == _BOOL_FALSE:
        return False, new_pos

    if cid == _VECTOR_CID:
        count = _u32(data, new_pos)[0]
        item_pos = new_pos + 4
        _check_count(count, data, item_pos)
        items = []
        for _ in range(count):
            item, item_pos = _read_object(data, item_pos, schema_by_cid)
            items.append(item)
        return items, item_pos

    entry = schema_by_cid.get(cid)
    if entry is not None:
        cls = _load_class(entry[0])
        if cls is not None:
            rd = _CID_READERS[cid] = cls.from_bytes
            return rd(data, new_pos)

    return _read_value(data, pos, schema_by_cid)


def _read_uint32(data: bytes, pos: int) -> tuple[int, int]:
    return _u32(data, pos)[0], pos + 4


def _read_int32(data: bytes, pos: int) -> tuple[int, int]:
    return _i32(data, pos)[0], pos + 4


def _read_int64(data: bytes, pos: int) -> tuple[int, int]:
    return _i64(data, pos)[0], pos + 8


def _read_double(data: bytes, pos: int) -> tuple[float, int]:
    return _f64(data, pos)[0], pos + 8


def _read_bool(data: bytes, pos: int) -> tuple[bool, int]:
    return _u32(data, pos)[0] == _BOOL_TRUE, pos + 4


def _read_string(data: bytes, pos: int) -> tuple[str, int]:
    b, pos = _read_bytes(data, pos)
    return b.decode("utf-8", "replace"), pos


def _read_int128(data: bytes, pos: int) -> tuple[int, int]:
    return int.from_bytes(data[pos:pos + 16], "little"), pos + 16


def _read_int256(data: bytes, pos: int) -> tuple[int, int]:
    return int.from_bytes(data[pos:pos + 32], "little"), pos + 32


def _read_bytes(data: bytes, pos: int) -> tuple[bytes, int]:
    if pos >= len(data):
        raise TLDecodeError(f"bytes field starts past end of buffer at offset {pos}")
    first = data[pos]
    if first <= 253:
        n = first
        start = pos + 1
        pad = (4 - (n + 1) % 4) % 4
    else:
        if pos + 4 > len(data):
            raise TLDecodeError(f"bytes header overruns buffer at offset {pos}")
        n = data[pos+1] | (data[pos+2] << 8) | (data[pos+3] << 16)
        start = pos + 4
        pad = (4 - n % 4) % 4
    end = start + n
    if end > len(data):
        raise TLDecodeError(f"bytes field of {n} bytes overruns buffer at offset {pos}")
    return data[start:end], end + pad


def _read_value(data: bytes, pos: int, schema: dict) -> tuple[Any, int]:
    cid, pos = _read_uint32(data, pos)

    if cid == _BOOL_TRUE:  return True,  pos
    if cid == _BOOL_FALSE: return False, pos

    if cid == _VECTOR_CID:
        count, pos = _read_uint32(data, pos)
        _check_count(count, data, pos)
        items = []
        for _ in range(count):
            item, pos = _read_object(data, pos, schema)
            items.append(item)
        return items, pos

    if cid not in schema:
        raise TLDecodeError(f"unknown constructor {hex(cid)} at offset {pos - 4}")

    name, fields = schema[cid]
    obj: dict[str, Any] = {"_": name}

    # Every flag group's word (including "flags" itself) is read lazily,
    # on first encounter of a field that's actually gated on it. Do NOT
    # special-case "flags" as always-first: some constructors declare a
    # field before the "flags:#" marker in the schema text (e.g.
    # poll#966e2dbf and wallPaper#a437c3ed both read "id" before flags),
    # and hoisting the word early would misread that field's bytes as
    # the flags word.
    flag_words: dict[str, int] = {}
    at: dict[int, list[str]] = {}
    for group, idx in _flag_markers(name).items():
        at.setdefault(idx, []).append(group)

    for i, (fname, ftype, flag) in enumerate(fields):
        for group in at.get(i, ()):
            flag_words[group], pos = _read_uint32(data, pos)
        if flag is not None:
            group, bit = flag
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
    for group in at.get(len(fields), ()):
        flag_words[group], pos = _read_uint32(data, pos)

    return obj, pos


_TYPED_READERS = {
    "int": _read_int32,
    "long": _read_int64,
    "double": _read_double,
    "string": _read_string,
    "bytes": _read_bytes,
    "Bool": _read_bool,
    "int128": _read_int128,
    "int256": _read_int256,
}


def _read_vector(data: bytes, pos: int, inner: str, schema: dict) -> tuple[list, int]:
    count = _u32(data, pos + 4)[0]
    pos += 8
    _check_count(count, data, pos)
    if inner == "int":
        return list(struct.unpack_from(f"<{count}i", data, pos)), pos + 4 * count
    if inner == "long":
        return list(struct.unpack_from(f"<{count}q", data, pos)), pos + 8 * count
    items = []
    rd = _TYPED_READERS.get(inner)
    if rd is not None:
        for _ in range(count):
            item, pos = rd(data, pos)
            items.append(item)
    elif inner.startswith(("Vector<", "vector<")):
        sub = inner[7:-1]
        for _ in range(count):
            item, pos = _read_vector(data, pos, sub, schema)
            items.append(item)
    else:
        for _ in range(count):
            item, pos = _read_object(data, pos, schema)
            items.append(item)
    return items, pos


def _read_typed(data: bytes, pos: int, ftype: str, schema: dict) -> tuple[Any, int]:
    rd = _TYPED_READERS.get(ftype)
    if rd is not None:
        return rd(data, pos)
    if ftype.startswith(("Vector<", "vector<")):
        return _read_vector(data, pos, ftype[7:-1], schema)
    return _read_object(data, pos, schema)


def _html_unescape(s: str) -> str:
        return _html.unescape(s)


def _attr(tag_raw: str, name: str) -> str:
    """Extract an attribute value from a raw tag string."""
    m = re.search(rf'{re.escape(name)}=["\']([^"\']*)["\']', tag_raw)
    return m.group(1) if m else ""


_HTML_TAG_MAP: dict[str, str] = {
    "b": "messageEntityBold", "strong": "messageEntityBold",
    "i": "messageEntityItalic", "em": "messageEntityItalic",
    "u": "messageEntityUnderline", "ins": "messageEntityUnderline",
    "s": "messageEntityStrike", "strike": "messageEntityStrike", "del": "messageEntityStrike",
    "code": "messageEntityCode",
    "pre": "messageEntityPre",
    "mark": "messageEntitySpoiler",
    "tg-spoiler": "messageEntitySpoiler",
    "blockquote": "messageEntityBlockquote",
}


def parse_html(text: str) -> tuple[str, list]:
    """Parse HTML-formatted text into (plain_text, MessageEntity list).

    Supported tags:
      <b> <strong>                       bold
      <i> <em>                           italic
      <u> <ins>                          underline
      <s> <strike> <del>                 strikethrough
      <code>                             code (inline)
      <pre language="...">               pre block
      <mark>                             spoiler
      <tg-spoiler>                       spoiler
      <blockquote>                       blockquote
      <tg-emoji emoji-id="...">          custom emoji
      <img src="tg://emoji?id=..."/>     custom emoji (self-close form)
      <a href="...">                     text URL / mailto / tel / tg://user
      <tg-time unix="..." format="...">  formatted date
    """
    TAG_MAP = _HTML_TAG_MAP
    entities: list = []
    plain_parts: list[str] = []
    stack: list[tuple[str, int, dict]] = []

    # offset tracks the length of everything emitted to plain_parts so far,
    # updated in O(1) by _emit(). All appends to plain_parts must go through
    # _emit() so offset stays correct.
    offset = 0

    def cur_offset() -> int:
        return offset

    def _emit(s: str) -> None:
        nonlocal offset
        if s:
            plain_parts.append(s)
            offset += _u16(s)

    i = 0
    src = text
    while i < len(src):
        if src[i] != "<":
            # Batch the whole run of plain text up to the next "<" (or end
            # of string) into a single append.
            next_lt = src.find("<", i)
            run_end = next_lt if next_lt != -1 else len(src)
            _emit(_html_unescape(src[i:run_end]))
            i = run_end
            continue
        end = src.find(">", i)
        if end == -1:
            _emit(src[i])
            i += 1
            continue
        tag_full = src[i + 1:end]
        i = end + 1

        self_close = tag_full.endswith("/")
        if self_close:
            tag_full = tag_full[:-1].rstrip()

        closing = tag_full.startswith("/")
        if closing:
            tag_name = tag_full[1:].split()[0].lower()
            attrs_raw = ""
        else:
            parts_split = tag_full.split(None, 1)
            tag_name = parts_split[0].lower()
            attrs_raw = parts_split[1] if len(parts_split) > 1 else ""

        if self_close:
            if not closing and tag_name == "img":
                src_val = _attr(attrs_raw, "src")
                m_eid = re.search(r'tg://emoji\?id=(\d+)', src_val)
                if m_eid:
                    off = cur_offset()
                    alt = _attr(attrs_raw, "alt")
                    char = alt or "\U0001f44d"
                    _emit(char)
                    entities.append({
                        "_": "messageEntityCustomEmoji",
                        "offset": off,
                        "length": _u16(char),
                        "document_id": int(m_eid.group(1)),
                    })
            continue

        if closing:
            for j in range(len(stack) - 1, -1, -1):
                etype, pstart, extra = stack[j]
                if extra.get("_tag") == tag_name:
                    length = cur_offset() - pstart
                    if length > 0 and etype != "__skip__":
                        ent: dict = {"_": etype, "offset": pstart, "length": length}
                        ent.update({k: v for k, v in extra.items() if k != "_tag"})
                        entities.append(ent)
                    stack.pop(j)
                    break
            continue

        # opening tags
        if tag_name == "a":
            href = _attr(attrs_raw, "href")
            if href.startswith("mailto:"):
                etype = "messageEntityEmail"
                extra_d: dict = {"_tag": "a", "url": href}
            elif href.startswith("tel:"):
                etype = "messageEntityPhone"
                extra_d = {"_tag": "a", "url": href}
            elif (m_uid := re.match(r'tg://user\?id=(\d+)', href)):
                uid = int(m_uid.group(1))
                etype = "messageEntityMentionName"
                extra_d = {"_tag": "a", "user_id": uid}
            elif href.startswith("#"):
                stack.append(("__skip__", cur_offset(), {"_tag": "a"}))
                continue
            else:
                etype = "messageEntityTextUrl"
                extra_d = {"_tag": "a", "url": href}
            stack.append((etype, cur_offset(), extra_d))

        elif tag_name == "tg-emoji":
            emoji_id_str = _attr(attrs_raw, "emoji-id")
            if emoji_id_str:
                stack.append(("messageEntityCustomEmoji", cur_offset(), {
                    "_tag": "tg-emoji",
                    "document_id": int(emoji_id_str),
                }))

        elif tag_name == "tg-time":
            unix_str = _attr(attrs_raw, "unix")
            fmt = _attr(attrs_raw, "format")
            if unix_str:
                stack.append(("messageEntityFormattedDate", cur_offset(), {
                    "_tag": "tg-time",
                    "date": int(unix_str),
                    "relative": "r" in fmt,
                    "short_time": "t" in fmt,
                    "long_time": "T" in fmt,
                    "short_date": "d" in fmt,
                    "long_date": "D" in fmt,
                    "day_of_week": "w" in fmt,
                }))

        elif tag_name == "tg-math":
            stack.append(("messageEntityCode", cur_offset(), {"_tag": "tg-math"}))

        elif tag_name == "pre":
            lang = _attr(attrs_raw, "language") or _attr(attrs_raw, "lang") or ""
            stack.append(("messageEntityPre", cur_offset(), {"_tag": "pre", "language": lang}))

        elif tag_name in TAG_MAP:
            etype = TAG_MAP[tag_name]
            stack.append((etype, cur_offset(), {"_tag": tag_name}))
        # ignore unknown/block tags (h1-h6, p, div, br, aside, details, tg-collage, etc.)

    # flush unclosed frames
    for etype, pstart, extra in stack:
        length = cur_offset() - pstart
        if length > 0 and etype not in ("__skip__",):
            ent = {"_": etype, "offset": pstart, "length": length}
            ent.update({k: v for k, v in extra.items() if k != "_tag"})
            entities.append(ent)

    return "".join(plain_parts), entities


_MARKDOWN_INLINE = re.compile(
    r'(?s)'
    r'(\x00PRE\x00([^\x00]*)\x00(.*?)(?=\n\x00|\Z))'
    r'|(\x00MATH\x00([^\n]*))'
    r'|(\x00QUOTE\x00([^\n]*))'
    r'|(\|\|(.+?)\|\|)'
    r'|(==(.+?)==)'
    r'|(\$\$(.+?)\$\$)'
    r'|(\$([^$\s][^$\n]*?)\$)'
    r'|(\*\*(.+?)\*\*)'
    r'|(__(.+?)__)'
    r'|(\*([^*\n]+?)\*)'
    r'|(_([^_\n]+?)_)'
    r'|(~~(.+?)~~)'
    r'|(```([a-zA-Z0-9]*)\n(.*?)```)'
    r'|(`([^`\n]+?)`)'
    r'|(\[(\^[^\]]+)\](?!\())'
    r'|(!?\[([^\]]*)\]\(([^)]+)\))'
)


def parse_markdown(text: str) -> tuple[str, list]:
    """Parse Telegram-style rich Markdown into (plain_text, MessageEntity list).

    Supported:
      **bold** / __bold__
      *italic* / _italic_
      ~~strikethrough~~
      `inline code`
      ||spoiler|| / ==spoiler==
      ```lang code block```
      [text](url)  links / mailto / tel / tg://user mention
      ![alt](tg://emoji?id=...)  custom emoji
      $math$  inline formula (code entity)
      > blockquote lines
      # Heading lines (kept as plain text)
      [^id] footnote refs (stripped)
    """
    entities: list = []
    plain_parts: list[str] = []

    # offset tracks the length of everything emitted to plain_parts so far,
    # updated in O(1) by _emit(). All appends to plain_parts must go through
    # _emit() so offset stays correct.
    offset = 0

    def cur_offset() -> int:
        return offset

    def _emit(s: str) -> None:
        nonlocal offset
        if s:
            plain_parts.append(s)
            offset += _u16(s)

    def push(fragment: str, etype: str, extra: dict | None = None) -> None:
        off = cur_offset()
        _emit(fragment)
        ent: dict = {"_": etype, "offset": off, "length": _u16(fragment)}
        if extra:
            ent.update(extra)
        entities.append(ent)

    # Pre-process block-level constructs line by line.
    lines = text.split("\n")
    processed: list[str] = []
    in_code = False
    code_lang = ""
    code_buf: list[str] = []

    for line in lines:
        if in_code:
            if line.strip().startswith("```"):
                processed.append("\x00PRE\x00" + code_lang + "\x00" + "\n".join(code_buf))
                in_code = False
                code_lang = ""
                code_buf = []
            else:
                code_buf.append(line)
            continue

        s = line.rstrip()
        if s.startswith("```"):
            in_code = True
            code_lang = s[3:].strip()
            code_buf = []
            continue

        # block math $$...$$ on its own line
        if (m_math := re.match(r'^\$\$(.+)\$\$$', s)):
            processed.append("\x00MATH\x00" + m_math.group(1))
            continue

        # blockquote
        if s.startswith(">"):
            processed.append("\x00QUOTE\x00" + s[1:].lstrip())
            continue

        # heading: strip markers, keep content
        m_h = re.match(r'^#{1,6}\s+(.*)', s)
        if m_h:
            processed.append(m_h.group(1))
            continue

        # horizontal rule
        if re.match(r'^[-*_]{3,}\s*$', s):
            continue

        # footnote definitions
        if re.match(r'^\[\^[^\]]+\]:', s):
            continue

        processed.append(line)

    if in_code and code_buf:
        processed.append("\x00PRE\x00" + code_lang + "\x00" + "\n".join(code_buf))

    src = "\n".join(processed)

    pos = 0
    for m in _MARKDOWN_INLINE.finditer(src):
        _emit(src[pos:m.start()])
        pos = m.end()
        g = m.groups()

        if g[0] is not None:
            push(g[2] or "", "messageEntityPre", {"language": g[1] or ""})
        elif g[3] is not None:
            push(g[4] or "", "messageEntityCode")
        elif g[5] is not None:
            content = g[6] or ""
            off = cur_offset()
            _emit(content)
            if content:
                entities.append({"_": "messageEntityBlockquote", "offset": off, "length": _u16(content)})
        elif g[7] is not None:
            push(g[8], "messageEntitySpoiler")
        elif g[9] is not None:
            push(g[10], "messageEntitySpoiler")
        elif g[11] is not None:
            push(g[12], "messageEntityCode")
        elif g[13] is not None:
            push(g[14], "messageEntityCode")
        elif g[15] is not None:
            push(g[16], "messageEntityBold")
        elif g[17] is not None:
            push(g[18], "messageEntityBold")
        elif g[19] is not None:
            push(g[20], "messageEntityItalic")
        elif g[21] is not None:
            push(g[22], "messageEntityItalic")
        elif g[23] is not None:
            push(g[24], "messageEntityStrike")
        elif g[25] is not None:
            push(g[27] or "", "messageEntityPre", {"language": g[26] or ""})
        elif g[28] is not None:
            push(g[29], "messageEntityCode")
        elif g[30] is not None:
            pass  # footnote ref stripped
        elif g[32] is not None:
            full_m = m.group(0)
            is_img = full_m.startswith("!")
            label = g[33] or ""
            url = (g[34] or "").strip()
            if is_img:
                me = re.match(r'tg://emoji\?id=(\d+)', url)
                if me:
                    push(label or "\U0001f44d", "messageEntityCustomEmoji",
                         {"document_id": int(me.group(1))})
                elif label:
                    _emit(label)
            else:
                if url.startswith("mailto:"):
                    push(label, "messageEntityEmail", {"url": url})
                elif url.startswith("tel:"):
                    push(label, "messageEntityPhone", {"url": url})
                elif (m_uid := re.match(r'tg://user\?id=(\d+)', url)):
                    uid = int(m_uid.group(1))
                    push(label, "messageEntityMentionName", {"user_id": uid})
                else:
                    push(label, "messageEntityTextUrl", {"url": url})

    _emit(src[pos:])
    plain = "".join(plain_parts)
    # strip any unmatched sentinels
    plain = re.sub(r'\x00[A-Z]+\x00[^\x00]*\x00?', '', plain)
    return plain, entities
