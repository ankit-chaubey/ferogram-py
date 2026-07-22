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
# group is "flags", "flags2", etc. - any string matching the flag-word name in TL.
# bit is the 0-based bit index within that flag word.



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

    # Fast path: dispatch to the generated class's specialized to_bytes(),
    # which has the field layout inlined at codegen time instead of walking
    # the schema dict per field. Falls back to the generic walk below for
    # anything not in the dispatch table (shouldn't normally happen - it's
    # built from the same schema every to_bytes() constructor is generated
    # from) or if the dict's shape doesn't match the constructor's __init__
    # (extra/missing keys), so a mismatch degrades instead of breaking.
    cls = _ensure_serialize_dispatch().get(name)
    if cls is not None:
        try:
            return cls(**{k: v for k, v in obj.items() if k != "_"}).to_bytes()
        except TypeError:
            pass

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


# constructor name -> generated class; populated lazily on first serialize call.
# Covers both raw/generated/types (nested field values, e.g. inputPeerChannel)
# and raw/generated/functions (top-level RPC requests). Keyed by name (not CID,
# unlike _CID_TO_CLASS below) since that's what obj["_"] carries.
_NAME_TO_CLASS: dict[str, type] | None = None


def _ensure_serialize_dispatch() -> dict[str, type]:
    global _NAME_TO_CLASS
    if _NAME_TO_CLASS is None:
        import importlib
        import pkgutil
        from ferogram.raw.generated import functions as _functions_pkg
        from ferogram.raw.generated import types as _types_pkg
        from ferogram.raw.generated._tl_schema import _SCHEMA

        # First constructor name wins on a CID collision - shouldn't happen,
        # every CID in api.tl is unique by construction.
        name_by_cid: dict[int, str] = {}
        for cname, (cid, _fields) in _SCHEMA.items():
            name_by_cid.setdefault(cid, cname)

        mapping: dict[str, type] = {}
        for pkg in (_types_pkg, _functions_pkg):
            for _, modname, _ in pkgutil.walk_packages(
                path=pkg.__path__,
                prefix=pkg.__name__ + ".",
            ):
                mod = importlib.import_module(modname)
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if isinstance(obj, type) and hasattr(obj, "to_bytes"):
                        cid = getattr(obj, "_CID", None)
                        cname = name_by_cid.get(cid)
                        if cname is not None:
                            mapping[cname] = obj
        _NAME_TO_CLASS = mapping
    return _NAME_TO_CLASS


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


# CID -> generated class; populated lazily on first deserialize call.
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




def _html_unescape(s: str) -> str:
    """Unescape basic HTML entities."""
    return (s
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", "\u00a0")
    )


def _attr(tag_raw: str, name: str) -> str:
    """Extract an attribute value from a raw tag string."""
    import re
    m = re.search(rf'{re.escape(name)}=["\']([^"\']*)["\']', tag_raw)
    return m.group(1) if m else ""


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
    import re
    TAG_MAP: dict[str, str] = {
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
    entities: list = []
    plain_parts: list[str] = []
    stack: list[tuple[str, int, dict]] = []

    def cur_offset() -> int:
        return sum(len(p) for p in plain_parts)

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
                    plain_parts.append(char)
                    entities.append({
                        "_": "messageEntityCustomEmoji",
                        "offset": off,
                        "length": len(char),
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
            elif re.match(r'tg://user\?id=(\d+)', href):
                uid = int(re.match(r'tg://user\?id=(\d+)', href).group(1))
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

    plain = _html_unescape("".join(plain_parts))
    return plain, entities


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
    import re
    entities: list = []
    plain_parts: list[str] = []

    def cur_offset() -> int:
        return sum(len(p) for p in plain_parts)

    def push(fragment: str, etype: str, extra: dict | None = None) -> None:
        off = cur_offset()
        plain_parts.append(fragment)
        ent: dict = {"_": etype, "offset": off, "length": len(fragment)}
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
        if re.match(r'^\$\$(.+)\$\$$', s):
            formula = re.match(r'^\$\$(.+)\$\$$', s).group(1)
            processed.append("\x00MATH\x00" + formula)
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

    INLINE = re.compile(
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

    pos = 0
    for m in INLINE.finditer(src):
        plain_parts.append(src[pos:m.start()])
        pos = m.end()
        g = m.groups()

        if g[0] is not None:
            push(g[2] or "", "messageEntityPre", {"language": g[1] or ""})
        elif g[3] is not None:
            push(g[4] or "", "messageEntityCode")
        elif g[5] is not None:
            content = g[6] or ""
            off = cur_offset()
            plain_parts.append(content)
            if content:
                entities.append({"_": "messageEntityBlockquote", "offset": off, "length": len(content)})
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
                    plain_parts.append(label)
            else:
                if url.startswith("mailto:"):
                    push(label, "messageEntityEmail", {"url": url})
                elif url.startswith("tel:"):
                    push(label, "messageEntityPhone", {"url": url})
                elif re.match(r'tg://user\?id=(\d+)', url):
                    uid = int(re.match(r'tg://user\?id=(\d+)', url).group(1))
                    push(label, "messageEntityMentionName", {"user_id": uid})
                else:
                    push(label, "messageEntityTextUrl", {"url": url})

    plain_parts.append(src[pos:])
    plain = "".join(plain_parts)
    # strip any unmatched sentinels
    plain = re.sub(r'\x00[A-Z]+\x00[^\x00]*\x00?', '', plain)
    return plain, entities
