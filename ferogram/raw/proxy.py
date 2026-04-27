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

"""
ferogram Style 4 - the cleanest raw API:

    await client.raw.messages.GetHistory(peer="@durov", limit=10)

Three things happen automatically:
  1. Peer is resolved  → "@durov" becomes InputPeerUsername dict
  2. Boring ints fill  → offset_id, hash, etc. become 0
  3. random_id gen     → SendMessage gets a random_id if you skip it

Proxy chain:
  client.raw                        → RawProxy
  client.raw.messages               → NamespaceProxy("messages")
  client.raw.messages.GetHistory    → MethodCaller("messages", "GetHistory")
  client.raw.messages.GetHistory(…) → resolve + fill + invoke
"""
from __future__ import annotations

import random
import re
from typing import Any

# ── field auto-default rules ──────────────────────────────────────────────────
_INT_TYPES   = {"int", "long", "int32", "int64", "int128", "int256", "Int", "Long"}
_FLOAT_TYPES = {"double"}
_STR_TYPES   = {"string"}
_BYTES_TYPES = {"bytes"}
_BOOL_TYPES  = {"Bool"}
_VECTOR_RE   = re.compile(r"[Vv]ector<(.+)>")

_MISSING = object()


def _auto_default(ftype: str) -> Any:
    """Return a zero-value for a required primitive field, or _MISSING for TL objects."""
    if ftype in _INT_TYPES:     return 0
    if ftype in _FLOAT_TYPES:   return 0.0
    if ftype in _STR_TYPES:     return ""
    if ftype in _BYTES_TYPES:   return b""
    if ftype in _BOOL_TYPES:    return False
    if _VECTOR_RE.match(ftype): return []
    return _MISSING  # TL object - user must provide


# ── peer-like field names ─────────────────────────────────────────────────────
_PEER_FIELDS = {"peer", "channel", "participant", "user_id", "from_id", "send_as"}


# ── TL name derivation ────────────────────────────────────────────────────────
def _tl_name(namespace: str, class_name: str) -> str:
    """("messages", "GetHistory") → "messages.getHistory"
       ("_base",    "InputPeer")  → "inputPeer"
    """
    snake = class_name[0].lower() + class_name[1:]
    if namespace == "_base":
        return snake
    return f"{namespace}.{snake}"


# ── proxy chain ───────────────────────────────────────────────────────────────

class RawProxy:
    """client.raw - exposes every TL namespace as an attribute."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def __getattr__(self, namespace: str) -> "NamespaceProxy":
        if namespace.startswith("_"):
            raise AttributeError(namespace)
        return NamespaceProxy(self._client, namespace)


class NamespaceProxy:
    """client.raw.messages - exposes every function in that namespace."""

    def __init__(self, client: Any, namespace: str) -> None:
        self._client    = client
        self._namespace = namespace

    def __getattr__(self, method_name: str) -> "MethodCaller":
        if method_name.startswith("_"):
            raise AttributeError(method_name)
        return MethodCaller(self._client, self._namespace, method_name)

    def __repr__(self) -> str:
        return f"NamespaceProxy({self._namespace!r})"


class MethodCaller:
    """
    client.raw.messages.GetHistory(peer="@durov", limit=10)

    Steps before invoking:
      1. Resolve peer-like fields (str/int → typed dict)
      2. Auto-fill required primitive fields with zero defaults
      3. Auto-generate random_id for send functions
      4. Build typed object and call client.invoke()
    """

    def __init__(self, client: Any, namespace: str, method: str) -> None:
        self._client    = client
        self._namespace = namespace
        self._method    = method

    async def __call__(self, **kwargs: Any) -> Any:
        from .generated._tl_schema import _SCHEMA
        from .generated import functions as _functions

        tl_key = _tl_name(self._namespace, self._method)

        ns_mod = getattr(_functions, self._namespace, None)
        if ns_mod is None:
            raise AttributeError(
                f"ferogram.raw has no namespace {self._namespace!r}. "
                f"Available: {[x for x in dir(_functions) if not x.startswith('_')]}"
            )

        cls = getattr(ns_mod, self._method, None)
        if cls is None:
            raise AttributeError(
                f"ferogram.raw.{self._namespace} has no method {self._method!r}"
            )

        if tl_key not in _SCHEMA:
            raise KeyError(f"TL schema has no entry for {tl_key!r}")

        _cid, schema_fields = _SCHEMA[tl_key]

        # step 1: resolve peer-like fields
        for fname, ftype, flag_bit in schema_fields:
            if fname not in kwargs:
                continue
            if (fname in _PEER_FIELDS
                    and not isinstance(kwargs[fname], dict)
                    and not hasattr(kwargs[fname], "to_dict")):
                kwargs[fname] = await self._client._resolve_peer(kwargs[fname])

        # step 2: auto-fill required primitive fields
        for fname, ftype, flag_bit in schema_fields:
            if flag_bit is not None:
                continue           # optional - skip
            if fname in kwargs:
                continue           # user provided - skip
            default = _auto_default(ftype)
            if default is not _MISSING:
                kwargs[fname] = default

        # step 3: auto random_id
        if "random_id" in {f[0] for f in schema_fields} and "random_id" not in kwargs:
            kwargs["random_id"] = random.randint(-(2**63), 2**63 - 1)

        # step 4: build + invoke
        try:
            fn = cls(**kwargs)
        except TypeError as e:
            raise TypeError(
                f"client.raw.{self._namespace}.{self._method}() - {e}\n"
                f"Required fields: {[f[0] for f in schema_fields if f[2] is None]}"
            ) from e

        return await self._client.invoke(fn)

    def __repr__(self) -> str:
        return f"MethodCaller({self._namespace!r}, {self._method!r})"


# ── PeerCache ─────────────────────────────────────────────────────────────────

class PeerCache:
    """
    Lightweight access_hash cache.
    Wire into client update processing:
        client._peer_cache.store_user(id, access_hash)
        client._peer_cache.store_channel(id, access_hash)
    """

    def __init__(self) -> None:
        self._users:    dict[int, int] = {}    # user_id    → access_hash
        self._channels: dict[int, int] = {}    # channel_id → access_hash
        self._chats:    set[int]       = set() # basic group ids (no hash)

    def store_user(self, user_id: int, access_hash: int) -> None:
        self._users[user_id] = access_hash

    def store_channel(self, channel_id: int, access_hash: int) -> None:
        self._channels[channel_id] = access_hash

    def store_chat(self, chat_id: int) -> None:
        self._chats.add(chat_id)

    def get_user(self, user_id: int) -> int | None:
        return self._users.get(user_id)

    def get_channel(self, channel_id: int) -> int | None:
        return self._channels.get(channel_id)

    def has_chat(self, chat_id: int) -> bool:
        return chat_id in self._chats


# ── peer resolver ─────────────────────────────────────────────────────────────

async def resolve_peer(client: Any, peer: Any) -> dict:
    """
    Convert any peer representation to a TL InputPeer dict.

      "me" / "self"        → inputPeerSelf
      "@username"          → inputPeerUsername
      "username"           → inputPeerUsername
      123456789  (user)    → inputPeerUser    (cache → live lookup)
      -123456789 (chat)    → inputPeerChat
      -100xxx    (channel) → inputPeerChannel (cache → live lookup)
      typed TL object      → .to_dict()
      dict                 → passthrough
    """
    if isinstance(peer, dict):
        return peer
    if hasattr(peer, "to_dict"):
        return peer.to_dict()
    if isinstance(peer, str) and peer.lower() in ("me", "self"):
        return {"_": "inputPeerSelf"}
    if isinstance(peer, str):
        return {"_": "inputPeerUsername", "username": peer.lstrip("@")}
    if isinstance(peer, int):
        return await _resolve_int_peer(client, peer)
    raise ValueError(
        f"Cannot resolve peer {peer!r}. "
        "Pass a username '@name', 'me', an integer ID, or a typed TL object."
    )


async def _resolve_int_peer(client: Any, peer_id: int) -> dict:
    cache: PeerCache = client._peer_cache

    # positive → user
    if peer_id > 0:
        ah = cache.get_user(peer_id)
        if ah is not None:
            return {"_": "inputPeerUser", "user_id": peer_id, "access_hash": ah}
        result = await client.invoke(_make_get_users([peer_id]))
        users  = result.get("users") or (result if isinstance(result, list) else [result])
        for u in users:
            if u.get("id") == peer_id:
                ah = u.get("access_hash", 0)
                cache.store_user(peer_id, ah)
                return {"_": "inputPeerUser", "user_id": peer_id, "access_hash": ah}
        raise ValueError(f"User {peer_id} not found")

    abs_id = abs(peer_id)

    # -100xxxxxxxxxx → channel / megagroup
    if abs_id > 1_000_000_000:
        channel_id = abs_id - 1_000_000_000
        ah = cache.get_channel(channel_id)
        if ah is not None:
            return {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": ah}
        result = await client.invoke(_make_get_channels([peer_id]))
        chats  = result.get("chats") or []
        for ch in chats:
            if ch.get("id") == channel_id:
                ah = ch.get("access_hash", 0)
                cache.store_channel(channel_id, ah)
                return {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": ah}
        raise ValueError(f"Channel {peer_id} not found")

    # small negative → basic group
    return {"_": "inputPeerChat", "chat_id": abs_id}


def _make_get_users(user_ids: list[int]) -> dict:
    return {
        "_": "users.getUsers",
        "id": [{"_": "inputUser", "user_id": uid, "access_hash": 0} for uid in user_ids],
    }


def _make_get_channels(channel_ids: list[int]) -> dict:
    return {
        "_": "messages.getChats",
        "id": [abs(cid) - 1_000_000_000 for cid in channel_ids],
    }
