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


"""Shared constants and helpers used by `Client` and its method groups."""

from __future__ import annotations

import base64
import logging
import struct
from typing import Any, Callable

from ._ferogram import srp_calculate


_log = logging.getLogger("ferogram")


class _ClientLoggerAdapter(logging.LoggerAdapter):
    """Prefixes every record with a short tag identifying which `Client`
    instance logged it, so output from two clients running in the same
    process (e.g. a userbot + a bot account) doesn't collapse into one
    indistinguishable stream. The tag starts as the session name/type and
    gains a "dcN" suffix once start() knows which DC it landed on.
    """

    def process(self, msg, kwargs):
        return f"[{self.extra['client']}] {msg}", kwargs


def _session_tag(session: Any, session_string: str | None) -> str:
    """Short, stable identifier for a session, used to tag log lines.

    Doesn't try to be unique - just distinguishable enough to tell two
    Client instances' log lines apart at a glance.
    """
    if session_string:
        return "session_string"
    if isinstance(session, str):
        return session
    return type(session).__name__


class SignInCodeInvalid(RuntimeError):
    """Raised by sign_in() when Telegram rejects the login code.

    `expired` is True for PHONE_CODE_EXPIRED (the code timed out - call
    resend_code() before trying again) and False for PHONE_CODE_INVALID /
    PHONE_CODE_EMPTY (the code itself was wrong - just re-prompt and retry
    with the same sent_code). Mirrors ferogram's Rust `SignInError::InvalidCode`.
    """
    def __init__(self, message: str, expired: bool = False) -> None:
        super().__init__(message)
        self.expired = expired


_Handler = tuple[Callable, list[Callable]]


_DEVICE_MODEL    = "Python"


_SYSTEM_VERSION  = "1.0"


_APP_VERSION     = "1.0"


_LANG_CODE       = "en"


_SYSTEM_LANG     = "en"


_LANG_PACK       = ""


# invokeWithLayer / initConnection / help.getConfig constructor IDs (not in api.tl schema)
_CID_INVOKE_WITH_LAYER     = 0xda9b0d0d


_CID_INIT_CONNECTION       = 0xc1cd5ea9


_CID_HELP_GET_CONFIG       = 0xc4f9186b


_CID_IMPORT_AUTHORIZATION  = 0xa57a7dad


def _pack_u32(v: int) -> bytes: return struct.pack("<I", v & 0xFFFFFFFF)


def _pack_i32(v: int) -> bytes: return struct.pack("<i", v)


def _pack_i64(v: int) -> bytes: return struct.pack("<q", v)


def _pack_str(s: str)  -> bytes:
    b = s.encode()
    n = len(b)
    if n <= 253:
        header = bytes([n])
        pad = (4 - (n + 1) % 4) % 4
    else:
        header = bytes([254, n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF])
        pad = (4 - n % 4) % 4
    return header + b + b"\x00" * pad


def _pack_bytes(b: bytes) -> bytes:
    # TL "bytes" uses the same length-prefixed/padded wire format as "string".
    n = len(b)
    if n <= 253:
        header = bytes([n])
        pad = (4 - (n + 1) % 4) % 4
    else:
        header = bytes([254, n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF])
        pad = (4 - n % 4) % 4
    return header + b + b"\x00" * pad


def _build_init_connection(api_id: int, device: str, sys_ver: str, app_ver: str,
                            sys_lang: str, lang_pack: str, lang_code: str,
                            inner_bytes: bytes) -> bytes:
    # initConnection#c1cd5ea9 flags:# api_id:int device_model:string system_version:string
    #   app_version:string system_lang_code:string lang_pack:string lang_code:string
    #   proxy:flags.0?... params:flags.1?... query:!X
    flags = 0  # no proxy, no params
    return (
        _pack_u32(_CID_INIT_CONNECTION)
        + _pack_u32(flags)
        + _pack_i32(api_id)
        + _pack_str(device)
        + _pack_str(sys_ver)
        + _pack_str(app_ver)
        + _pack_str(sys_lang)
        + _pack_str(lang_pack)
        + _pack_str(lang_code)
        + inner_bytes
    )


def _build_invoke_with_layer(layer: int, inner_bytes: bytes) -> bytes:
    return _pack_u32(_CID_INVOKE_WITH_LAYER) + _pack_i32(layer) + inner_bytes


def _build_help_get_config() -> bytes:
    return _pack_u32(_CID_HELP_GET_CONFIG)


def _build_import_authorization(id_: int, bytes_: bytes) -> bytes:
    # auth.importAuthorization#a57a7dad id:long bytes:bytes = auth.Authorization
    return _pack_u32(_CID_IMPORT_AUTHORIZATION) + _pack_i64(id_) + _pack_bytes(bytes_)


def _parse_proxy_link(url: str) -> dict:
    """Parse a `https://t.me/proxy?...` or `tg://proxy?...` MTProxy link into
    `{"dc_addr": ..., "transport": ..., "proxy_secret": ..., "domain": ...}`,
    mirroring ferogram's Rust `parse_proxy_link`. `domain` is only
    meaningful (non-None) for "faketls" links - the SNI hostname presented
    in the fake TLS ClientHello, taken from the secret's trailing bytes if
    present, else falling back to the link's own `server` host.
    """
    for prefix in ("https://t.me/proxy?", "tg://proxy?"):
        if url.startswith(prefix):
            rest = url[len(prefix):]
            break
    else:
        raise ValueError(f"not an MTProxy link: {url!r}")

    params = dict(kv.split("=", 1) for kv in rest.split("&") if "=" in kv)
    try:
        host = params["server"]
        port = int(params["port"])
        secret_param = params["secret"]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid MTProxy link {url!r}: missing/bad server, port, or secret") from exc

    if len(secret_param) >= 32 and all(c in "0123456789abcdefABCDEF" for c in secret_param):
        secret_bytes = bytes.fromhex(secret_param)
    else:
        padded = secret_param.replace("-", "+").replace("_", "/")
        pad_len = (-len(padded)) % 4
        secret_bytes = base64.b64decode(padded + "=" * pad_len)

    if not secret_bytes:
        raise ValueError(f"invalid MTProxy link {url!r}: empty secret")

    prefix_byte = secret_bytes[0]
    domain = None
    if prefix_byte == 0xDD:
        key = secret_bytes[1:17]
        transport = "padded_intermediate"
    elif prefix_byte == 0xEE:
        key = secret_bytes[1:17]
        domain = secret_bytes[17:].decode("utf-8", errors="replace") if len(secret_bytes) > 17 else host
        transport = "faketls"
    else:
        key = secret_bytes[:16]
        transport = "obfuscated"

    return {
        "dc_addr": f"{host}:{port}",
        "transport": transport,
        "proxy_secret": key.hex(),
        "domain": domain,
    }


class StopPropagation(Exception):
    """Raise inside a handler to stop processing all further handlers for this update."""


class ContinuePropagation(Exception):
    """Raise inside a handler to skip to the next matching handler in the same group."""


_ALL_EVENTS = (
    "message",
    "edited_message",
    "message_deleted",
    "callback_query",
    "inline_query",
    "inline_send",
    "user_status",
    "chat_action",
    "participant_update",
    "join_request",
    "message_reaction",
    "poll_vote",
    "bot_stopped",
    "raw_update",
    "shipping_query",
    "pre_checkout_query",
    "chat_boost",
)


def _markup_to_dict(markup: Any) -> dict:
    if isinstance(markup, dict):
        return markup
    if hasattr(markup, "to_dict"):
        return markup.to_dict()
    return {}


def _extract_invite_hash(link: str) -> str:
    if "+" in link:
        return link.split("+")[-1]
    if "/" in link:
        return link.rstrip("/").split("/")[-1]
    return link


def _web_document(url: str, mime_type: str, attributes: list | None = None) -> dict:
    return {"_": "inputWebDocument", "url": url, "size": 0, "mime_type": mime_type,
            "attributes": attributes or []}


def _inline_tuple_to_tl(r: tuple) -> dict:
    """Turn an inline result tuple into an inputBotInlineResult.

    Two layouts are accepted: the short ("article", id, title, description, text) and the
    12-field tuple that `InlineArticle`, `InlinePhoto` and `InlineDocument` produce:
    (kind, id, title, text, description, url, thumb_url, photo_url, width, height, mime, markup).

    Photo and document results are URL based: the media goes in `content` and is sent with
    `inputBotInlineMessageMediaAuto` (`text` becomes the caption). Articles send plain text.
    """
    kind = r[0] if r else "article"
    if kind not in ("article", "photo", "document"):
        raise ValueError(f"unknown inline result kind {kind!r}, expected article, photo or document")
    if len(r) == 5 and kind == "article":
        _, id_, title, desc, text = r
        url = thumb_url = photo_url = mime = reply_markup = None
        width = height = 0
    elif len(r) == 12:
        _, id_, title, text, desc, url, thumb_url, photo_url, width, height, mime, reply_markup = r
    else:
        raise ValueError(f"inline result tuple must have 5 or 12 items, got {len(r)}")

    if kind == "article":
        send_message: dict = {"_": "inputBotInlineMessageText", "message": text}
    else:
        send_message = {"_": "inputBotInlineMessageMediaAuto", "message": text}
    if reply_markup is not None:
        send_message["reply_markup"] = _markup_to_dict(reply_markup)

    result: dict = {
        "_": "inputBotInlineResult",
        "id": str(id_),
        "type": {"article": "article", "photo": "photo", "document": "file"}[kind],
        "title": title,
        "send_message": send_message,
    }
    if desc is not None:
        result["description"] = desc

    if kind == "article":
        if url is not None:
            result["url"] = url
    elif kind == "photo":
        sizes = ([{"_": "documentAttributeImageSize", "w": width, "h": height}]
                 if width and height else [])
        result["content"] = _web_document(photo_url, mime or "image/jpeg", sizes)
        thumb_url = thumb_url or photo_url
    else:
        result["content"] = _web_document(url, mime or "application/octet-stream")
    if thumb_url is not None:
        result["thumb"] = _web_document(thumb_url, "image/jpeg")
    return result


def _srp_answer(pw_info: dict, password: str) -> dict:
    if not pw_info.get("has_password"):
        return {"_": "inputCheckPasswordEmpty"}

    algo = pw_info.get("current_algo") or {}
    if algo.get("_") != "passwordKdfAlgoSHA256SHA256PBKDF2HMACSHA512iter100000SHA256ModPow":
        raise RuntimeError(f"unsupported password KDF algo: {algo.get('_')}")

    salt1 = algo.get("salt1", b"")
    salt2 = algo.get("salt2", b"")
    g     = algo.get("g", 0)
    p     = algo.get("p", b"")
    srp_b = pw_info.get("srp_B", b"")
    srp_id = pw_info.get("srp_id", 0)

    g_a, m1 = srp_calculate(salt1, salt2, p, g, srp_b, password)

    return {
        "_": "inputCheckPasswordSRP",
        "srp_id": srp_id,
        "A": bytes(g_a),
        "M1": bytes(m1),
    }


def _parse_migrate(err: str) -> int | None:
    import re
    m = re.search(r'MIGRATE[^(]*\((?:value: )?(\d+)\)', err)
    if m:
        return int(m.group(1))
    return None


def _is_bot_token(s: str) -> bool:
    """Bot tokens look like '123456789:AAAbcdEf...'; phone numbers don't contain ':'."""
    import re
    return bool(re.match(r'^\d+:[A-Za-z0-9_-]+$', s))


def _as_input_channel(input_peer: dict, what: str) -> dict:
    """Turn a resolved `inputPeerChannel` into the `inputChannel` that channels.* and stats.*
    requests expect. Serializing the peer constructor in an InputChannel field would put the
    wrong constructor id on the wire."""
    if input_peer.get("_") != "inputPeerChannel":
        raise ValueError(f"{what}: peer must be a channel or supergroup")
    return {
        "_": "inputChannel",
        "channel_id": input_peer["channel_id"],
        "access_hash": input_peer.get("access_hash", 0),
    }


def _inline_message_id_to_tl(msg_id: Any) -> dict:
    """Build an InputBotInlineMessageID from whatever the caller has.

    Accepts the TL dict that inline updates deliver (used as is), an `InlineMessageId`,
    or a `(dc_id, id_bytes)` tuple. `id_bytes` is the decoded inline message id without
    its leading dc_id: 16 bytes (id:long, access_hash:long) for the old layout, or
    20 bytes (owner_id:long, id:int, access_hash:long) for the 64-bit layout.
    """
    if isinstance(msg_id, dict):
        if str(msg_id.get("_", "")).startswith("inputBotInlineMessageID"):
            return msg_id
        raise ValueError(f"not an inline message id: {msg_id.get('_')!r}")
    if hasattr(msg_id, "dc_id") and hasattr(msg_id, "id_bytes"):
        dc_id, raw = msg_id.dc_id, msg_id.id_bytes
    else:
        dc_id, raw = msg_id
    raw = bytes(raw)
    if len(raw) == 16:
        id_, access_hash = struct.unpack("<qq", raw)
        return {"_": "inputBotInlineMessageID", "dc_id": dc_id, "id": id_, "access_hash": access_hash}
    if len(raw) == 20:
        owner_id, id_, access_hash = struct.unpack("<qiq", raw)
        return {"_": "inputBotInlineMessageID64", "dc_id": dc_id, "owner_id": owner_id,
                "id": id_, "access_hash": access_hash}
    raise ValueError(f"inline message id bytes must be 16 or 20 long, got {len(raw)}")
