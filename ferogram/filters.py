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


# Filters for use with handler decorators.
# Each filter is a callable: filter(update) -> bool

from __future__ import annotations
import re
from typing import Callable, Any


Filter = Callable[[Any], bool]


def _make(fn: Callable) -> Filter:
    return fn


def _get_msg(m: Any) -> Any:
    """Unwrap NewMessage/EditedMessage wrapper to the inner Message object."""
    return getattr(m, "message", m)

def _get_text(m: Any) -> str:
    return getattr(_get_msg(m), "text", None) or ""

def _get_chat_id(m: Any) -> int | None:
    return getattr(_get_msg(m), "chat_id", None)

def _get_from_id(m: Any) -> int | None:
    return getattr(_get_msg(m), "sender_id", None)


all_updates = _make(lambda _: True)
private   = _make(lambda m: _get_chat_id(m) is not None and _get_chat_id(m) > 0)
group     = _make(lambda m: (_get_chat_id(m) or 0) < 0)
channel   = _make(lambda m: (_get_chat_id(m) or 0) < 0 and not _get_from_id(m))
text      = _make(lambda m: bool(_get_text(m)))
photo     = _make(lambda m: getattr(_get_msg(m), "has_photo", False))
document  = _make(lambda m: getattr(_get_msg(m), "has_document", False))
media     = _make(lambda m: bool(getattr(_get_msg(m), "media", None)))
outgoing  = _make(lambda m: getattr(_get_msg(m), "out", False))
incoming  = _make(lambda m: not getattr(_get_msg(m), "out", True))
mentioned = _make(lambda m: getattr(_get_msg(m), "mentioned", False))
album     = _make(lambda m: getattr(_get_msg(m), "grouped_id", None) is not None)
reply     = _make(lambda m: getattr(_get_msg(m), "reply_to_msg_id", None) is not None)
forwarded = _make(lambda m: getattr(_get_msg(m), "forward_from_id", None) is not None)
via_bot   = _make(lambda m: getattr(_get_msg(m), "via_bot_id", None) is not None)
pinned    = _make(lambda m: getattr(_get_msg(m), "pinned", False))


def command(*names: str, prefix: str = "/") -> Filter:
    lower = {n.lstrip(prefix).lower() for n in names}
    def check(m: Any) -> bool:
        t = _get_text(m)
        if not t.startswith(prefix):
            return False
        cmd = t[len(prefix):].split()[0].split("@")[0].lower()
        return cmd in lower
    return check


def regex(pattern: str | re.Pattern, flags: int = 0) -> Filter:
    compiled = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    def check(m: Any) -> bool:
        return bool(compiled.search(_get_text(m)))
    return check


def text_contains(substr: str, case_sensitive: bool = False) -> Filter:
    sub = substr if case_sensitive else substr.lower()
    def check(m: Any) -> bool:
        t = _get_text(m)
        return sub in (t if case_sensitive else t.lower())
    return check


def startswith(prefix: str) -> Filter:
    def check(m: Any) -> bool:
        return _get_text(m).startswith(prefix)
    return check


def endswith(suffix: str) -> Filter:
    def check(m: Any) -> bool:
        return _get_text(m).endswith(suffix)
    return check


def user(*user_ids: int) -> Filter:
    ids = set(user_ids)
    return _make(lambda m: _get_from_id(m) in ids)


def chat(*chat_ids: int) -> Filter:
    ids = set(chat_ids)
    return _make(lambda m: _get_chat_id(m) in ids)



def data(value: str) -> Filter:
    return _make(lambda q: getattr(q, "data", None) == value)


def data_regex(pattern: str | re.Pattern, flags: int = 0) -> Filter:
    compiled = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    return _make(lambda q: bool(compiled.search(getattr(q, "data", "") or "")))


def data_startswith(prefix: str) -> Filter:
    return _make(lambda q: (getattr(q, "data", "") or "").startswith(prefix))



def inline(pattern: str | re.Pattern | None = None, flags: int = 0) -> Filter:
    if pattern is None:
        return _make(lambda q: True)
    compiled = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    return _make(lambda q: bool(compiled.search(getattr(q, "query", "") or "")))



online  = _make(lambda s: getattr(s, "online", False))
offline = _make(lambda s: not getattr(s, "online", True))


def status(value: str) -> Filter:
    return _make(lambda s: getattr(s, "status", None) == value)



def action(name: str) -> Filter:
    return _make(lambda a: getattr(a, "action", None) == name)

typing = action("typing")



def reaction(*emojis: str) -> Filter:
    s = set(emojis)
    return _make(lambda r: bool(set(getattr(r, "new_reactions", [])) & s))



def participant_status(*statuses: str) -> Filter:
    s = set(statuses)
    def check(p: Any) -> bool:
        return getattr(p, "status", None) in s
    return check



def constructor(cid: int) -> Filter:
    return _make(lambda r: getattr(r, "constructor_id", None) == cid)


def update_type(name: str) -> Filter:
    return _make(lambda r: getattr(r, "type_name", None) == name)



def and_(*filters: Filter) -> Filter:
    return _make(lambda m: all(f(m) for f in filters))


def or_(*filters: Filter) -> Filter:
    return _make(lambda m: any(f(m) for f in filters))


def not_(f: Filter) -> Filter:
    return _make(lambda m: not f(m))


AND = and_
OR  = or_
NOT = not_



def min_length(n: int) -> Filter:
    def check(m: Any) -> bool:
        t = getattr(m, "text", None) or ""
        return len(t) >= n
    return check


def max_length(n: int) -> Filter:
    def check(m: Any) -> bool:
        t = getattr(m, "text", None) or ""
        return len(t) <= n
    return check



bot     = _make(lambda m: getattr(getattr(m, "sender", None), "bot", False))
no_bot  = _make(lambda m: not getattr(getattr(m, "sender", None), "bot", False))


scheduled = _make(lambda m: getattr(m, "date", 0) == 0)


def vote_position(index: int) -> Filter:
    return _make(lambda v: index in getattr(v, "positions", []))

