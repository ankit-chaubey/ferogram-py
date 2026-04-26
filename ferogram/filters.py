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


# ---- message filters ----

# passes for any update
all       = _make(lambda _: True)
# only private chats
private   = _make(lambda m: getattr(m, "is_private", None) or (m.from_id is not None and m.chat_id == m.from_id))
# only group/channel chats (chat_id < 0)
group     = _make(lambda m: getattr(m, "is_group", None) or m.chat_id < 0)
channel   = _make(lambda m: m.chat_id < 0 and not getattr(m, "from_id", None))
# message has text
text      = _make(lambda m: bool(getattr(m, "text", None)))
# message has a photo
photo     = _make(lambda m: getattr(m, "has_photo", False))
document  = _make(lambda m: getattr(m, "has_document", False))
# message has any media
media     = _make(lambda m: getattr(m, "has_media", False))
# outgoing message
outgoing  = _make(lambda m: getattr(m, "outgoing", False))
# incoming message
incoming  = _make(lambda m: not getattr(m, "outgoing", True))
mentioned = _make(lambda m: getattr(m, "mentioned", False))
album     = _make(lambda m: getattr(m, "grouped_id", None) is not None)
reply     = _make(lambda m: getattr(m, "reply_to_message_id", None) is not None)
forwarded = _make(lambda m: getattr(m, "is_forwarded", False))
via_bot   = _make(lambda m: getattr(m, "via_bot_id", None) is not None)
pinned    = _make(lambda m: getattr(m, "pinned", False))


def command(*names: str, prefix: str = "/") -> Filter:
    lower = {n.lstrip(prefix).lower() for n in names}
    def check(m: Any) -> bool:
        t = getattr(m, "text", None) or ""
        if not t.startswith(prefix):
            return False
        cmd = t[len(prefix):].split()[0].split("@")[0].lower()
        return cmd in lower
    return check


def regex(pattern: str | re.Pattern, flags: int = 0) -> Filter:
    compiled = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    def check(m: Any) -> bool:
        t = getattr(m, "text", None) or ""
        return bool(compiled.search(t))
    return check


def text_contains(substr: str, case_sensitive: bool = False) -> Filter:
    sub = substr if case_sensitive else substr.lower()
    def check(m: Any) -> bool:
        t = getattr(m, "text", None) or ""
        return sub in (t if case_sensitive else t.lower())
    return check


def startswith(prefix: str) -> Filter:
    def check(m: Any) -> bool:
        t = getattr(m, "text", None) or ""
        return t.startswith(prefix)
    return check


def endswith(suffix: str) -> Filter:
    def check(m: Any) -> bool:
        t = getattr(m, "text", None) or ""
        return t.endswith(suffix)
    return check


def user(*user_ids: int) -> Filter:
    ids = set(user_ids)
    return _make(lambda m: getattr(m, "from_id", None) in ids)


def chat(*chat_ids: int) -> Filter:
    """Only pass updates from specific chat ids."""
    ids = set(chat_ids)
    return _make(lambda m: getattr(m, "chat_id", None) in ids)


# ---- callback query filters ----

def data(value: str) -> Filter:
    """Match callback_query data exactly."""
    return _make(lambda q: getattr(q, "data", None) == value)


def data_regex(pattern: str | re.Pattern, flags: int = 0) -> Filter:
    compiled = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    return _make(lambda q: bool(compiled.search(getattr(q, "data", "") or "")))


def data_startswith(prefix: str) -> Filter:
    return _make(lambda q: (getattr(q, "data", "") or "").startswith(prefix))


# ---- inline query filters ----

def inline(pattern: str | re.Pattern | None = None, flags: int = 0) -> Filter:
    if pattern is None:
        return _make(lambda q: True)
    compiled = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    return _make(lambda q: bool(compiled.search(getattr(q, "query", "") or "")))


# ---- user status filters ----

online  = _make(lambda s: getattr(s, "online", False))
offline = _make(lambda s: not getattr(s, "online", True))


def status(value: str) -> Filter:
    return _make(lambda s: getattr(s, "status", None) == value)


# ---- chat action filters ----

def action(name: str) -> Filter:
    """Match a specific chat action string, e.g. 'typing', 'upload_photo'."""
    return _make(lambda a: getattr(a, "action", None) == name)

typing = action("typing")


# ---- reaction filters ----

def reaction(*emojis: str) -> Filter:
    s = set(emojis)
    return _make(lambda r: bool(set(getattr(r, "new_reactions", [])) & s))


# participant update filters

def participant_status(*statuses: str) -> Filter:
    s = set(statuses)
    def check(p: Any) -> bool:
        return getattr(p, "status", None) in s
    return check


# ---- raw update filters ----

def constructor(cid: int) -> Filter:
    return _make(lambda r: getattr(r, "constructor_id", None) == cid)


def update_type(name: str) -> Filter:
    return _make(lambda r: getattr(r, "type_name", None) == name)


# ---- logic combinators ----

def and_(*filters: Filter) -> Filter:
    return _make(lambda m: all(f(m) for f in filters))


def or_(*filters: Filter) -> Filter:
    return _make(lambda m: any(f(m) for f in filters))


def not_(f: Filter) -> Filter:
    return _make(lambda m: not f(m))


AND = and_
OR  = or_
NOT = not_


# message length filters

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


# bot filters

# aliases
bot     = _make(lambda m: getattr(getattr(m, "sender", None), "bot", False))
no_bot  = _make(lambda m: not getattr(getattr(m, "sender", None), "bot", False))

# scheduled message filter

scheduled = _make(lambda m: getattr(m, "date", 0) == 0)

# poll vote filter (by position index)

def vote_position(index: int) -> Filter:
    return _make(lambda v: index in getattr(v, "positions", []))

