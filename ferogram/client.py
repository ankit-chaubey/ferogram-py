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

import asyncio
import hashlib
import inspect
import logging
import os
import random
import struct
from typing import Any, Callable

from ._ferogram import DcConnection, srp_calculate
from ._ferogram import (
    FileSession, MemorySession, StringSession,
    SqliteSession, LibSqlSession, CustomSession,
)
from .raw import tl as _tl
from .raw.generated._tl_schema import _SCHEMA, _SCHEMA_BY_CID, LAYER
from .raw.proxy import RawProxy, PeerCache, resolve_peer as _resolve_peer_fn
from .types import (
    ChatAction, PrivacyKey, PrivacyRule,
    InlineMessageId, InlineArticle, InlinePhoto, InlineDocument,
    _inline_result_to_tuple,
)
from .updates import wrap_update
from .keyboards import InlineKeyboard, ReplyKeyboard, RemoveKeyboard, ForceReply

__all__ = ["Client", "StopPropagation", "ContinuePropagation"]

_log = logging.getLogger("ferogram")

_Handler = tuple[Callable, list[Callable]]

_DEVICE_MODEL    = "Python"
_SYSTEM_VERSION  = "1.0"
_APP_VERSION     = "1.0"
_LANG_CODE       = "en"
_SYSTEM_LANG     = "en"
_LANG_PACK       = ""

# invokeWithLayer / initConnection / help.getConfig constructor IDs (not in api.tl schema)
_CID_INVOKE_WITH_LAYER = 0xda9b0d0d
_CID_INIT_CONNECTION   = 0xc1cd5ea9
_CID_HELP_GET_CONFIG   = 0xc4f9186b


def _pack_u32(v: int) -> bytes: return struct.pack("<I", v & 0xFFFFFFFF)
def _pack_i32(v: int) -> bytes: return struct.pack("<i", v)
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

_AUDIO_MIME   = "audio/mpeg"
_VIDEO_MIME   = "video/mp4"
_VOICE_MIME   = "audio/ogg"
_STICKER_MIME = "image/webp"


class Client:
    def __init__(
        self,
        session: "str | FileSession | MemorySession | StringSession | SqliteSession | LibSqlSession | CustomSession" = "ferogram",
        *,
        api_id: int | None = None,
        api_hash: str | None = None,
        bot_token: str | None = None,
        phone: str | None = None,
        password: str | None = None,
        proxy: str | None = None,
        allow_ipv6: bool = False,
        dc_addr: str | None = None,
        probe_transport: bool = False,
        resilient_connect: bool = False,
        catch_up: bool = False,
        pfs: bool = False,
        device: str | None = None,
        system_version: str | None = None,
        app_version: str | None = None,
        lang_code: str | None = None,
        system_lang_code: str | None = None,
        lang_pack: str | None = None,
        session_string: str | None = None,
        in_memory: bool = False,
        update_queue_capacity: int | None = None,
        update_overflow: str | None = None,
        low_memory_mode: bool = False,
        allow_missing_channel_hash: bool = False,
        auto_resolve_peers: bool = False,
        parse_mode: str | None = None,
        workers: int = 4,
        flood_sleep_threshold: int = 60,
    ) -> None:
        self.session                  = session
        self.api_id                   = api_id or int(os.environ.get("API_ID", 0)) or None
        self.api_hash                 = api_hash or os.environ.get("API_HASH")
        self.bot_token                = bot_token or os.environ.get("BOT_TOKEN")
        self._phone                   = phone
        self._password                = password
        self.proxy                    = proxy
        self.allow_ipv6               = allow_ipv6
        self.dc_addr                  = dc_addr
        self.probe_transport          = probe_transport
        self.resilient_connect        = resilient_connect
        self.catch_up                 = catch_up
        self.pfs                      = pfs
        self.device                   = device or _DEVICE_MODEL
        self.system_version           = system_version or _SYSTEM_VERSION
        self.app_version              = app_version or _APP_VERSION
        self.lang_code                = lang_code or _LANG_CODE
        self.system_lang_code         = system_lang_code or _SYSTEM_LANG
        self.lang_pack                = lang_pack or _LANG_PACK
        self.session_string           = session_string
        self.in_memory                = in_memory
        self.update_queue_capacity    = update_queue_capacity
        self.update_overflow          = update_overflow
        self.low_memory_mode          = low_memory_mode
        self.allow_missing_channel_hash = allow_missing_channel_hash
        self.auto_resolve_peers       = auto_resolve_peers
        self.parse_mode               = parse_mode
        self._workers                 = workers
        self._flood_sleep_threshold   = flood_sleep_threshold
        self._conn: DcConnection | None = None
        self._handlers: dict[str, dict[int, list[_Handler]]] = {
            e: {} for e in _ALL_EVENTS
        }
        self._update_queue: asyncio.Queue | None = None
        self._peer_cache = PeerCache()
        self._pts: int = 0
        self._qts: int = 0
        self._date: int = 0
        self._seq: int = 0
        self.raw = RawProxy(self)

    def _resolve_pm(self, local: str | None) -> str | None:
        return local if local is not None else self.parse_mode

    def _require_creds(self) -> tuple[int, str]:
        if not self.api_id or not self.api_hash:
            raise ValueError("api_id and api_hash required.")
        return self.api_id, self.api_hash

    @property
    def _client(self) -> "Client":
        # self._client kept for compat; returns self
        return self

    def _require_conn(self) -> DcConnection:
        if self._conn is None:
            raise RuntimeError("Call await app.start() first.")
        return self._conn


    def _add_handler(self, event_type: str, func: Callable, filters: list, group: int) -> None:
        if group not in self._handlers[event_type]:
            self._handlers[event_type][group] = []
        self._handlers[event_type][group].append((func, filters))

    def on_message(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("message", func, list(filters), group)
            return func
        return decorator

    def on_edited_message(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("edited_message", func, list(filters), group)
            return func
        return decorator

    def on_message_deleted(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("message_deleted", func, list(filters), group)
            return func
        return decorator

    def on_callback_query(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("callback_query", func, list(filters), group)
            return func
        return decorator

    def on_inline_query(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("inline_query", func, list(filters), group)
            return func
        return decorator

    def on_inline_send(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("inline_send", func, list(filters), group)
            return func
        return decorator

    def on_user_status(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("user_status", func, list(filters), group)
            return func
        return decorator

    def on_chat_action(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("chat_action", func, list(filters), group)
            return func
        return decorator

    def on_participant_update(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("participant_update", func, list(filters), group)
            return func
        return decorator

    def on_join_request(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("join_request", func, list(filters), group)
            return func
        return decorator

    def on_message_reaction(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("message_reaction", func, list(filters), group)
            return func
        return decorator

    def on_poll_vote(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("poll_vote", func, list(filters), group)
            return func
        return decorator

    def on_bot_stopped(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("bot_stopped", func, list(filters), group)
            return func
        return decorator

    def on_shipping_query(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._add_handler("shipping_query", fn, list(filters), group)
            return fn
        return decorator

    def on_pre_checkout_query(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._add_handler("pre_checkout_query", fn, list(filters), group)
            return fn
        return decorator

    def on_chat_boost(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._add_handler("chat_boost", fn, list(filters), group)
            return fn
        return decorator

    def on_raw_update(self, *filters: Callable, group: int = 0) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._add_handler("raw_update", func, list(filters), group)
            return func
        return decorator

    def add_handler(self, event_type: str, func: Callable, *filters: Callable, group: int = 0) -> None:
        if event_type not in self._handlers:
            raise ValueError(f"Unknown event type: {event_type!r}")
        self._add_handler(event_type, func, list(filters), group)

    def remove_handler(self, event_type: str, func: Callable, group: int = 0) -> bool:
        bucket = self._handlers.get(event_type, {}).get(group, [])
        for i, (f, _) in enumerate(bucket):
            if f is func:
                bucket.pop(i)
                return True
        return False


    async def _dispatch(self, event_type: str, update: Any) -> None:
        groups = sorted(self._handlers.get(event_type, {}).keys())
        for g in groups:
            for func, fltrs in self._handlers[event_type][g]:
                if not all(f(update) for f in fltrs):
                    continue
                try:
                    result = func(self, update)
                    if inspect.isawaitable(result):
                        await result
                except StopPropagation:
                    return
                except ContinuePropagation:
                    continue
                except Exception as exc:
                    _log.error("handler error in %s: %s", event_type, exc, exc_info=True)
                break

    async def _worker(self) -> None:
        while True:
            item = await self._update_queue.get()
            try:
                if item is None:
                    return
                event_type, update = item
                await self._dispatch(event_type, update)
            except Exception as exc:
                _log.error("worker error: %s", exc, exc_info=True)
            finally:
                self._update_queue.task_done()


    def _route_update(self, upd: dict) -> tuple[str, Any] | None:
        t = upd.get("_", "")
        if t in ("updateNewMessage", "updateNewChannelMessage",
                  "updateNewScheduledMessage", "updateShortMessage"):
            msg = upd.get("message") or upd
            return ("message", msg)
        if t in ("updateEditMessage", "updateEditChannelMessage"):
            return ("edited_message", upd.get("message") or upd)
        if t == "updateDeleteMessages":
            return ("message_deleted", upd)
        if t in ("updateBotCallbackQuery", "updateInlineBotCallbackQuery"):
            return ("callback_query", upd)
        if t == "updateBotInlineQuery":
            return ("inline_query", upd)
        if t == "updateBotInlineSend":
            return ("inline_send", upd)
        if t == "updateUserStatus":
            return ("user_status", upd)
        if t in ("updateUserTyping", "updateChatUserTyping", "updateChannelUserTyping"):
            return ("chat_action", upd)
        if t == "updateChannelParticipant":
            return ("participant_update", upd)
        if t == "updateBotJoinRequest":
            return ("join_request", upd)
        if t == "updateMessageReactions":
            return ("message_reaction", upd)
        if t == "updateMessagePoll":
            return ("poll_vote", upd)
        if t == "updateBotStopped":
            return ("bot_stopped", upd)
        if t == "updateBotShippingQuery":
            return ("shipping_query", upd)
        if t == "updateBotPrecheckoutQuery":
            return ("pre_checkout_query", upd)
        if t == "updateBotChatBoost":
            return ("chat_boost", upd)
        # everything else goes to raw_update
        return ("raw_update", upd)

    def _collect_updates(self, resp: dict) -> list[dict]:
        t = resp.get("_", "")
        if t in ("updates", "updatesCombined"):
            self._populate_cache(resp)
            return resp.get("updates") or []
        if t == "updateShort":
            return [resp.get("update", resp)]
        if t == "updateShortMessage":
            return [resp]
        if t == "updates.difference":
            self._populate_cache(resp)
            msgs = [{"_": "updateNewMessage", "message": m, "pts": 0, "pts_count": 0}
                    for m in (resp.get("new_messages") or [])]
            return msgs + (resp.get("other_updates") or [])
        return []

    async def _run_updates(self) -> None:
        _log.debug("update loop started")
        self._update_queue = asyncio.Queue(maxsize=self._workers * 4)
        worker_tasks = [
            asyncio.create_task(self._worker())
            for _ in range(self._workers)
        ]
        try:
            # get initial state
            try:
                state = await self._rpc({"_": "updates.getState"})
                self._pts  = state.get("pts", 0)
                self._qts  = state.get("qts", 0)
                self._date = state.get("date", 0)
                self._seq  = state.get("seq", 0)
            except Exception as e:
                _log.warning("getState failed: %s", e)

            while True:
                await asyncio.sleep(0.3)
                try:
                    diff = await self._rpc({
                        "_": "updates.getDifference",
                        "pts": self._pts,
                        "date": self._date,
                        "qts": self._qts,
                    })
                except Exception as e:
                    _log.debug("getDifference error: %s", e)
                    await asyncio.sleep(2)
                    continue

                dt = diff.get("_", "")
                if dt == "updates.differenceEmpty":
                    new_date = diff.get("date")
                    if new_date:
                        self._date = new_date
                    continue

                updates_list = self._collect_updates(diff)

                # update state
                new_state = diff.get("state") or diff.get("intermediate_state")
                if new_state:
                    self._pts  = new_state.get("pts", self._pts)
                    self._qts  = new_state.get("qts", self._qts)
                    self._date = new_state.get("date", self._date)
                    self._seq  = new_state.get("seq", self._seq)
                else:
                    for u in updates_list:
                        pts = u.get("pts")
                        if pts:
                            self._pts = max(self._pts, pts)
                        date = u.get("date")
                        if date:
                            self._date = max(self._date, date)

                for upd in updates_list:
                    routed = self._route_update(upd)
                    if routed is None:
                        continue
                    event_type, event = routed
                    _log.debug("dispatching %s", event_type)
                    wrapped = wrap_update(event_type, event)
                    await self._update_queue.put((event_type, wrapped))

        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            for _ in worker_tasks:
                await self._update_queue.put(None)
            await asyncio.gather(*worker_tasks)


    async def _rpc(self, obj: dict, _retried_restart: bool = False) -> dict:
        conn = self._require_conn()
        req_bytes = _tl.serialize(obj, _SCHEMA)
        try:
            resp_bytes = await conn.rpc_call(req_bytes)
        except RuntimeError as e:
            msg = str(e)
            dc = _parse_migrate(msg)
            if dc is not None:
                await self._migrate(dc)
                return await self._rpc(obj)
            if "SESSION_PASSWORD_NEEDED" in msg:
                return {"_": "rpc_error", "error_code": 401,
                        "error_message": "SESSION_PASSWORD_NEEDED"}
            if "AUTH_RESTART" in msg and not _retried_restart:
                # AUTH_RESTART is transient right after a fresh auth key is
                # created on a new DC (e.g. after migrating for auth.sendCode).
                # Telegram expects the same request to simply be resent.
                _log.debug("AUTH_RESTART received, retrying request once")
                return await self._rpc(obj, _retried_restart=True)
            raise
        result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
        self._populate_cache(result)
        return result

    async def _migrate(self, dc_id: int) -> None:
        api_id, api_hash = self._require_creds()
        _log.info("migrating to DC%d", dc_id)
        session = self.session
        if isinstance(session, str):
            path = session if session.endswith(".session") else session + ".session"
            from ._ferogram import FileSession
            session = FileSession(path)
        self._conn = await DcConnection.connect(session, api_id, api_hash, dc_id)
        self._dc_id = dc_id
        await self._init_connection()
        _log.info("migrated to DC%d", dc_id)

    async def _init_connection(self) -> None:
        api_id, api_hash = self._require_creds()
        inner = _build_help_get_config()
        init  = _build_init_connection(
            api_id, self.device, self.system_version, self.app_version,
            self.system_lang_code, self.lang_pack, self.lang_code, inner,
        )
        wrapped = _build_invoke_with_layer(LAYER, init)
        conn = self._require_conn()
        resp_bytes = await conn.rpc_call(wrapped)
        _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)  # Config - parsed for DC info

    async def _resolve_peer(self, peer: Any) -> dict:
        return await _resolve_peer_fn(self, peer)

    def _populate_cache(self, obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        for u in obj.get("users") or []:
            if not isinstance(u, dict) or u.get("min"):
                continue
            uid = u.get("id")
            ah  = u.get("access_hash")
            if uid is not None and ah is not None:
                self._peer_cache.store_user(uid, ah)
        for ch in obj.get("chats") or []:
            if not isinstance(ch, dict) or ch.get("min"):
                continue
            cid = ch.get("id")
            if cid is None:
                continue
            ah = ch.get("access_hash")
            if ah is not None:
                self._peer_cache.store_channel(cid, ah)
            else:
                self._peer_cache.store_chat(cid)


    async def start(
        self,
        *,
        phone: str | None = None,
        bot_token: str | None = None,
        password: str | None = None,
        session_string: str | None = None,
    ) -> "Client":
        if self._conn is not None:
            return self

        # Per-call overrides take precedence over constructor-time values.
        if phone is not None:
            self._phone = phone
        if bot_token is not None:
            self.bot_token = bot_token
        if password is not None:
            self._password = password
        if session_string is not None:
            self.session_string = session_string

        api_id, api_hash = self._require_creds()

        session = self.session
        if self.session_string:
            session = StringSession(self.session_string)
        elif isinstance(session, str):
            path = session if session.endswith(".session") else session + ".session"
            session = FileSession(path)

        _log.info("connecting (session=%r)", repr(session))
        self._conn = await DcConnection.connect(session, api_id, api_hash)
        await self._init_connection()
        if not await self.is_authorized():
            if self.bot_token:
                await self.bot_sign_in(self.bot_token)
                _log.info("signed in as bot")
            else:
                await self._interactive_login()
            await self._conn.set_home_dc(self._conn.dc_id)
            await self._conn.save_session()
        else:
            _log.info("reusing existing session")
        return self

    async def _interactive_login(self) -> None:
        identifier = self._phone
        if identifier is None:
            identifier = input("Phone number (e.g. +91XXXXXXXXXX) or bot token: ").strip()

        if _is_bot_token(identifier):
            await self.bot_sign_in(identifier)
            _log.info("signed in as bot")
            print("\nPlease ensure your usage complies with Telegram's API Terms of Service.")
            return

        sent     = await self.request_login_code(identifier)
        pw_token = await self.sign_in(sent, input("Code: "))
        if pw_token is not None:
            hint = pw_token.get("hint", "")
            pwd  = self._password or input(f"2FA password (hint: {hint}): " if hint else "2FA password: ")
            await self.check_password(pw_token, pwd)
        _log.info("signed in as user")
        print("\nPlease ensure your usage complies with Telegram's API Terms of Service.")

    async def stop(self) -> None:
        if self._conn:
            await self.sign_out()
            self._conn = None
            _log.info("signed out")

    async def run_until_disconnected(self) -> None:
        await self.start()
        try:
            await self._run_updates()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

    def run(self) -> None:
        try:
            asyncio.run(self.run_until_disconnected())
        except KeyboardInterrupt:
            pass

    async def __aenter__(self) -> "Client":
        return await self.start()

    async def __aexit__(self, *_: Any) -> None:
        pass


    async def is_authorized(self) -> bool:
        try:
            result = await self._rpc({"_": "users.getUsers", "id": [{"_": "inputUserSelf"}]})
            users = result if isinstance(result, list) else result.get("users", [])
            return bool(users)
        except Exception:
            return False

    async def request_login_code(self, phone: str) -> dict:
        api_id, api_hash = self._require_creds()
        result = await self._rpc({
            "_": "auth.sendCode",
            "phone_number": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "settings": {"_": "codeSettings"},
        })
        # auth.sentCode does not carry phone_number back, so stash it
        # for sign_in()/resend_code() which need it.
        result["phone_number"] = phone
        return result

    async def sign_in(self, sent_code: dict, code: str) -> dict | None:
        phone = sent_code.get("phone_number", "")
        phone_code_hash = sent_code.get("phone_code_hash", "")
        result = await self._rpc({
            "_": "auth.signIn",
            "phone_number": phone,
            "phone_code_hash": phone_code_hash,
            "phone_code": code,
        })
        if result.get("_") == "auth.authorizationSignUpRequired":
            raise RuntimeError("Sign-up required - account does not exist.")
        if result.get("_") == "auth.authorization":
            return None  # success, no 2FA
        # SESSION_PASSWORD_NEEDED
        if result.get("_") == "rpc_error" or "error_code" in result:
            if result.get("error_message") == "SESSION_PASSWORD_NEEDED":
                return await self._rpc({"_": "account.getPassword"})
        return None

    async def check_password(self, pw_info: dict, password: str) -> None:
        srp = _srp_answer(pw_info, password)
        await self._rpc({"_": "auth.checkPassword", "password": srp})

    async def bot_sign_in(self, token: str) -> None:
        api_id, api_hash = self._require_creds()
        await self._rpc({
            "_": "auth.importBotAuthorization",
            "flags": 0,
            "api_id": api_id,
            "api_hash": api_hash,
            "bot_auth_token": token,
        })

    async def sign_out(self) -> None:
        try:
            await self._rpc({"_": "auth.logOut"})
        except Exception:
            pass

    async def login_bot(self, token: str) -> None:
        await self.bot_sign_in(token)
        await self._require_conn().save_session()

    async def export_session_string(self) -> str:
        return await self._require_conn().export_string()


    async def get_me(self) -> dict:
        result = await self._rpc({"_": "users.getUsers", "id": [{"_": "inputUserSelf"}]})
        users = result if isinstance(result, list) else []
        return users[0] if users else {}

    async def get_users_by_id(self, user_ids: list[int]) -> list[dict | None]:
        ids = [{"_": "inputUser", "user_id": uid, "access_hash": self._peer_cache.get_user(uid) or 0}
               for uid in user_ids]
        result = await self._rpc({"_": "users.getUsers", "id": ids})
        return result if isinstance(result, list) else []

    async def get_user_full(self, user_id: int) -> dict:
        peer = await self._resolve_peer(user_id)
        return await self._rpc({"_": "users.getFullUser", "id": peer})

    async def get_contacts(self) -> list[dict]:
        result = await self._rpc({"_": "contacts.getContacts", "hash": 0})
        return result.get("users", []) if isinstance(result, dict) else []


    async def send_message(self, peer: str, text: str, *,
                           parse_mode: str | None = None,
                           reply_markup=None) -> dict:
        pm = self._resolve_pm(parse_mode)
        if pm in ("markdown", "md"):
            plain, entities = _tl.parse_markdown(text)
        elif pm == "html":
            plain, entities = _tl.parse_html(text)
        else:
            plain, entities = text, []
        input_peer = await self._resolve_peer(peer)
        req: dict = {
            "_": "messages.sendMessage",
            "peer": input_peer,
            "message": plain,
            "random_id": random.randint(-(2**63), 2**63 - 1),
            "no_webpage": True,
            "entities": entities,
        }
        if reply_markup is not None:
            req["reply_markup"] = _markup_to_dict(reply_markup)
        return await self._rpc(req)

    async def send_to_self(self, text: str) -> None:
        await self.send_message("me", text)

    async def edit_message(self, peer: str, message_id: int, new_text: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.editMessage",
            "peer": input_peer,
            "id": message_id,
            "message": new_text,
            "no_webpage": True,
        })

    async def delete_message(self, message_id: int, revoke: bool = True) -> None:
        await self.delete_messages([message_id], revoke)

    async def delete_messages(self, message_ids: list[int], revoke: bool = True) -> None:
        await self._rpc({
            "_": "messages.deleteMessages",
            "id": message_ids,
            "revoke": revoke,
        })

    async def forward_messages(self, destination: str, source: str, message_ids: list[int]) -> None:
        from_peer = await self._resolve_peer(source)
        to_peer   = await self._resolve_peer(destination)
        await self._rpc({
            "_": "messages.forwardMessages",
            "from_peer": from_peer,
            "to_peer": to_peer,
            "id": message_ids,
            "random_id": [random.randint(-(2**63), 2**63 - 1) for _ in message_ids],
        })

    async def pin_message(self, peer: str, message_id: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.updatePinnedMessage",
            "peer": input_peer,
            "id": message_id,
        })

    async def unpin_message(self, peer: str, message_id: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.updatePinnedMessage",
            "peer": input_peer,
            "id": message_id,
            "unpin": True,
        })

    async def unpin_all_messages(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.unpinAllMessages", "peer": input_peer})

    async def mark_as_read(self, peer: str) -> None:
        await self.mark_dialog_read(peer)

    async def mark_dialog_read(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.readHistory", "peer": input_peer, "max_id": 0})

    async def clear_mentions(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.readMentions", "peer": input_peer})

    async def send_reaction(self, peer: str, message_id: int, emoji: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.sendReaction",
            "peer": input_peer,
            "msg_id": message_id,
            "reaction": [{"_": "reactionEmoji", "emoticon": emoji}],
        })

    async def send_chat_action(self, peer: str, action: "ChatAction | str") -> None:
        input_peer = await self._resolve_peer(peer)
        action_str = str(action)
        action_map = {
            "typing": "sendMessageTypingAction",
            "record_video": "sendMessageRecordVideoAction",
            "upload_video": "sendMessageUploadVideoAction",
            "record_audio": "sendMessageRecordAudioAction",
            "upload_audio": "sendMessageUploadAudioAction",
            "upload_photo": "sendMessageUploadPhotoAction",
            "upload_document": "sendMessageUploadDocumentAction",
            "find_location": "sendMessageGeoLocationAction",
            "record_video_note": "sendMessageRecordRoundAction",
            "upload_video_note": "sendMessageUploadRoundAction",
            "choose_sticker": "sendMessageChooseStickerAction",
            "cancel": "sendMessageCancelAction",
        }
        tl_action = action_map.get(action_str, action_str)
        await self._rpc({
            "_": "messages.setTyping",
            "peer": input_peer,
            "action": {"_": tl_action},
        })

    async def send_dice(self, peer: str, emoticon: str = "🎲") -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": {"_": "inputMediaDice", "emoticon": emoticon},
            "message": "",
            "random_id": random.randint(-(2**63), 2**63 - 1),
        })

    async def get_messages_by_id(self, peer: str, message_ids: list[int]) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "channels.getMessages",
            "channel": input_peer,
            "id": [{"_": "inputMessageID", "id": mid} for mid in message_ids],
        })
        return result.get("messages", []) if isinstance(result, dict) else []

    async def get_message(self, peer: str, msg_id: int) -> dict | None:
        msgs = await self.get_messages_by_id(peer, [msg_id])
        return msgs[0] if msgs else None

    async def get_message_history(self, peer: str, limit: int = 100, offset_id: int = 0) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getHistory",
            "peer": input_peer,
            "offset_id": offset_id,
            "offset_date": 0,
            "add_offset": 0,
            "limit": limit,
            "max_id": 0,
            "min_id": 0,
            "hash": 0,
        })
        return result.get("messages", []) if isinstance(result, dict) else []

    async def search_messages(self, peer: str, query: str, limit: int = 100) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.search",
            "peer": input_peer,
            "q": query,
            "filter": {"_": "inputMessagesFilterEmpty"},
            "min_date": 0,
            "max_date": 0,
            "offset_id": 0,
            "add_offset": 0,
            "limit": limit,
            "max_id": 0,
            "min_id": 0,
            "hash": 0,
        })
        return result.get("messages", []) if isinstance(result, dict) else []

    async def search_global(self, query: str, limit: int = 100) -> list[dict]:
        result = await self._rpc({
            "_": "messages.searchGlobal",
            "q": query,
            "filter": {"_": "inputMessagesFilterEmpty"},
            "min_date": 0,
            "max_date": 0,
            "offset_rate": 0,
            "offset_peer": {"_": "inputPeerEmpty"},
            "offset_id": 0,
            "limit": limit,
        })
        return result.get("messages", []) if isinstance(result, dict) else []

    async def delete_dialog(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.deleteHistory", "peer": input_peer, "max_id": 0, "revoke": False})

    async def get_pinned_message(self, peer: str) -> dict | None:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.search",
            "peer": input_peer,
            "q": "",
            "filter": {"_": "inputMessagesFilterPinned"},
            "min_date": 0, "max_date": 0, "offset_id": 0, "add_offset": 0,
            "limit": 1, "max_id": 0, "min_id": 0, "hash": 0,
        })
        msgs = result.get("messages", []) if isinstance(result, dict) else []
        return msgs[0] if msgs else None

    async def get_scheduled_messages(self, peer: str) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getScheduledHistory", "peer": input_peer, "hash": 0})
        return result.get("messages", []) if isinstance(result, dict) else []

    async def translate_messages(self, peer: str, msg_ids: list[int], to_lang: str) -> list[str]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.translateText",
            "peer": input_peer,
            "id": msg_ids,
            "to_lang": to_lang,
        })
        return [r.get("text", "") for r in (result.get("result") or [])]

    async def get_reply_to_message(self, peer: str, msg_id: int) -> dict | None:
        msg = await self.get_message(peer, msg_id)
        if not msg:
            return None
        reply_to = msg.get("reply_to", {})
        reply_id = reply_to.get("reply_to_msg_id") if isinstance(reply_to, dict) else None
        if reply_id is None:
            return None
        return await self.get_message(peer, reply_id)

    async def get_discussion_message(self, peer: str, msg_id: int) -> tuple[list[dict], int, int, int]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getDiscussionMessage", "peer": input_peer, "msg_id": msg_id})
        msgs = result.get("messages", [])
        return msgs, result.get("unread_count", 0), result.get("max_id", 0), result.get("read_inbox_max_id", 0)

    async def save_draft(self, peer: str, text: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.saveDraft", "peer": input_peer, "message": text})

    async def clear_all_drafts(self) -> None:
        await self._rpc({"_": "messages.clearAllDrafts"})

    async def sync_drafts(self) -> None:
        await self._rpc({"_": "messages.getAllDrafts"})

    async def send_poll(self, peer: str, question: str, answers: list[str], *,
                        quiz: bool = False, correct_index: int | None = None,
                        multiple_choice: bool = False, public_voters: bool = False,
                        shuffle_answers: bool = False, hide_results_until_close: bool = False,
                        close_period: int | None = None, close_date: int | None = None,
                        solution: str | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        poll: dict = {
            "_": "poll",
            "id": random.randint(0, 2**63 - 1),
            "question": {"_": "textWithEntities", "text": question, "entities": []},
            "answers": [
                {"_": "pollAnswer",
                 "text": {"_": "textWithEntities", "text": a, "entities": []},
                 "option": bytes([i])}
                for i, a in enumerate(answers)
            ],
            "quiz": quiz,
            "multiple_choice": multiple_choice,
            "public_voters": public_voters,
        }
        if close_period is not None:
            poll["close_period"] = close_period
        if close_date is not None:
            poll["close_date"] = close_date
        media: dict = {"_": "inputMediaPoll", "poll": poll}
        if quiz and correct_index is not None:
            media["correct_answers"] = [bytes([correct_index])]
        if solution:
            media["solution"] = solution
            media["solution_entities"] = []
        await self._rpc({
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": media,
            "message": "",
            "random_id": random.randint(-(2**63), 2**63 - 1),
        })

    async def send_vote(self, peer: str, msg_id: int, options: list[bytes]) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.sendVote", "peer": input_peer, "msg_id": msg_id, "options": options})

    async def get_poll_votes(self, peer: str, msg_id: int, limit: int = 100) -> list[tuple[int, bytes]]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getPollVotes",
            "peer": input_peer,
            "id": msg_id,
            "limit": limit,
        })
        votes = result.get("votes", []) if isinstance(result, dict) else []
        return [(v.get("user_id", 0), v.get("option", b"")) for v in votes]

    async def get_poll_results(self, peer: str, msg_id: int, poll_hash: int = 0) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.getPollResults", "peer": input_peer, "msg_id": msg_id})

    async def poll_results(self, peer: str, msg_id: int) -> str:
        return await self.get_poll_stats(peer, msg_id)

    async def get_poll_stats(self, peer: str, msg_id: int) -> str:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "stats.getMessagePublicForwards",
            "channel": input_peer,
            "msg_id": msg_id,
            "offset_rate": 0,
            "offset_peer": {"_": "inputPeerEmpty"},
            "offset_id": 0,
            "limit": 100,
        })
        return str(result)

    async def read_reactions(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.readReactions", "peer": input_peer})

    async def clear_recent_reactions(self) -> None:
        await self._rpc({"_": "messages.clearRecentReactions"})

    async def get_reaction_list(self, peer: str, msg_id: int, limit: int = 100) -> list[tuple[int, str]]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getMessageReactionsList",
            "peer": input_peer,
            "id": msg_id,
            "limit": limit,
        })
        reactions = result.get("reactions", []) if isinstance(result, dict) else []
        out = []
        for r in reactions:
            peer_id = r.get("peer_id", r.get("user_id", 0))
            emoji = ""
            reaction = r.get("reaction", {})
            if isinstance(reaction, dict):
                emoji = reaction.get("emoticon", "")
            out.append((peer_id, emoji))
        return out

    async def delete_reaction(self, peer: str, msg_id: int, participant: str) -> None:
        pass  # no direct TL for removing another user's reaction


    async def get_dialogs(self, limit: int = 100) -> list[dict]:
        result = await self._rpc({
            "_": "messages.getDialogs",
            "offset_date": 0,
            "offset_id": 0,
            "offset_peer": {"_": "inputPeerEmpty"},
            "limit": limit,
            "hash": 0,
            "exclude_pinned": False,
        })
        return result.get("dialogs", []) if isinstance(result, dict) else []

    async def get_pinned_dialogs(self, folder_id: int = 0) -> list[int]:
        result = await self._rpc({"_": "messages.getPinnedDialogs", "folder_id": folder_id})
        dialogs = result.get("dialogs", []) if isinstance(result, dict) else []
        out = []
        for d in dialogs:
            peer = d.get("peer", {})
            if isinstance(peer, dict):
                out.append(peer.get("user_id") or peer.get("chat_id") or peer.get("channel_id") or 0)
        return out

    async def archive_chat(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "folders.editPeerFolders",
            "folder_peers": [{"_": "inputFolderPeer", "peer": input_peer, "folder_id": 1}],
        })

    async def unarchive_chat(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "folders.editPeerFolders",
            "folder_peers": [{"_": "inputFolderPeer", "peer": input_peer, "folder_id": 0}],
        })

    async def pin_dialog(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.toggleDialogPin", "peer": {"_": "inputDialogPeer", "peer": input_peer}, "pinned": True})

    async def unpin_dialog(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.toggleDialogPin", "peer": {"_": "inputDialogPeer", "peer": input_peer}, "pinned": False})

    async def delete_dialog(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.deleteHistory", "peer": input_peer, "max_id": 0, "revoke": False})

    async def delete_chat_history(self, peer: str, max_id: int = 0, revoke: bool = False) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.deleteHistory", "peer": input_peer, "max_id": max_id, "revoke": revoke})


    async def join_chat(self, peer: str) -> None:
        if peer.startswith("+") or "/+" in peer:
            link = peer.split("/+")[-1] if "/+" in peer else peer[1:]
            await self._rpc({"_": "messages.importChatInvite", "hash": link})
        else:
            channel = await self._resolve_peer(peer)
            await self._rpc({"_": "channels.joinChannel", "channel": channel})

    async def leave_chat(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if "Channel" in t:
            await self._rpc({"_": "channels.leaveChannel", "channel": input_peer})
        else:
            me = await self.get_me()
            await self._rpc({"_": "messages.deleteChatUser", "chat_id": input_peer.get("chat_id", 0), "user_id": {"_": "inputUserSelf"}})

    async def get_online_count(self, peer: str) -> int:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getOnlines", "peer": input_peer})
        return result.get("onlines", 0) if isinstance(result, dict) else 0

    async def get_chat_administrators(self, peer: str) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "channels.getParticipants",
            "channel": input_peer,
            "filter": {"_": "channelParticipantsAdmins"},
            "offset": 0,
            "limit": 200,
            "hash": 0,
        })
        return result.get("participants", []) if isinstance(result, dict) else []

    async def get_participants(self, peer: str, limit: int = 200) -> list[dict]:
        return await self.get_participants_filtered(peer, "recent", limit)

    async def get_participants_filtered(self, peer: str, filter: str = "recent", limit: int = 200) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        filter_map = {
            "recent": "channelParticipantsRecent",
            "admins": "channelParticipantsAdmins",
            "kicked": "channelParticipantsKicked",
            "bots": "channelParticipantsBots",
            "contacts": "channelParticipantsContacts",
        }
        tl_filter = filter_map.get(filter, "channelParticipantsRecent")
        result = await self._rpc({
            "_": "channels.getParticipants",
            "channel": input_peer,
            "filter": {"_": tl_filter},
            "offset": 0,
            "limit": limit,
            "hash": 0,
        })
        return result.get("participants", []) if isinstance(result, dict) else []

    async def kick_participant(self, peer: str, user: str) -> None:
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        await self._rpc({
            "_": "channels.editBanned",
            "channel": channel,
            "participant": user_peer,
            "banned_rights": {
                "_": "chatBannedRights",
                "until_date": 0,
                "view_messages": True,
            },
        })

    async def ban_participant(self, peer: str, user: str) -> None:
        await self.kick_participant(peer, user)

    async def ban_participant_until(self, peer: str, user: str, until_date: int) -> None:
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        await self._rpc({
            "_": "channels.editBanned",
            "channel": channel,
            "participant": user_peer,
            "banned_rights": {
                "_": "chatBannedRights",
                "until_date": until_date,
                "view_messages": True,
            },
        })

    async def promote_participant(self, peer: str, user: str, rights: list[str] | None = None) -> None:
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        admin_rights: dict = {
            "_": "chatAdminRights",
            "change_info": True,
            "post_messages": True,
            "edit_messages": True,
            "delete_messages": True,
            "ban_users": True,
            "invite_users": True,
            "pin_messages": True,
            "manage_call": True,
            "manage_topics": True,
        }
        if rights:
            for r in rights:
                admin_rights[r] = True
        await self._rpc({
            "_": "channels.editAdmin",
            "channel": channel,
            "user_id": user_peer,
            "admin_rights": admin_rights,
            "rank": "",
        })

    async def demote_participant(self, peer: str, user: str) -> None:
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        await self._rpc({
            "_": "channels.editAdmin",
            "channel": channel,
            "user_id": user_peer,
            "admin_rights": {"_": "chatAdminRights"},
            "rank": "",
        })

    async def create_group(self, title: str, user_ids: list[int]) -> dict:
        result = await self._rpc({"_": "messages.createChat", "users": user_ids, "title": title})
        return result

    async def create_channel(self, title: str, about: str = "", broadcast: bool = True) -> dict:
        result = await self._rpc({
            "_": "channels.createChannel",
            "title": title,
            "about": about,
            "broadcast": broadcast,
            "megagroup": not broadcast,
        })
        return result

    async def delete_channel(self, peer: str) -> None:
        channel = await self._resolve_peer(peer)
        await self._rpc({"_": "channels.deleteChannel", "channel": channel})

    async def delete_chat(self, chat_id: int) -> None:
        await self._rpc({"_": "messages.deleteChat", "chat_id": chat_id})

    async def edit_chat_title(self, peer: str, title: str) -> None:
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if "Channel" in t:
            await self._rpc({"_": "channels.editTitle", "channel": input_peer, "title": title})
        else:
            await self._rpc({"_": "messages.editChatTitle", "chat_id": input_peer.get("chat_id", 0), "title": title})

    async def edit_chat_about(self, peer: str, about: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.editChatAbout", "peer": input_peer, "about": about})

    async def invite_users(self, peer: str, user_ids: list[int]) -> None:
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if "Channel" in t:
            for uid in user_ids:
                user_peer = {"_": "inputUser", "user_id": uid, "access_hash": self._peer_cache.get_user(uid) or 0}
                await self._rpc({"_": "channels.inviteToChannel", "channel": input_peer, "users": [user_peer]})
        else:
            for uid in user_ids:
                await self._rpc({"_": "messages.addChatUser", "chat_id": input_peer.get("chat_id", 0), "user_id": uid, "fwd_limit": 0})

    async def set_history_ttl(self, peer: str, period: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.setHistoryTTL", "peer": input_peer, "period": period})

    async def migrate_chat(self, chat_id: int) -> dict:
        result = await self._rpc({"_": "messages.migrateChat", "chat_id": chat_id})
        return result

    async def edit_chat_default_banned_rights(self, peer: str, restrictions: dict[str, bool]) -> None:
        input_peer = await self._resolve_peer(peer)
        banned_rights = {"_": "chatBannedRights", "until_date": 0}
        banned_rights.update({k: not v for k, v in restrictions.items()})
        await self._rpc({"_": "messages.editChatDefaultBannedRights", "peer": input_peer, "banned_rights": banned_rights})

    async def set_chat_reactions(self, peer: str, reactions: str) -> None:
        input_peer = await self._resolve_peer(peer)
        if reactions == "all":
            allowed = {"_": "chatReactionsAll"}
        elif reactions == "none":
            allowed = {"_": "chatReactionsNone"}
        else:
            emojis = [e.strip() for e in reactions.split(",") if e.strip()]
            allowed = {"_": "chatReactionsSome", "reactions": [{"_": "reactionEmoji", "emoticon": e} for e in emojis]}
        await self._rpc({"_": "messages.setChatAvailableReactions", "peer": input_peer, "available_reactions": allowed})

    async def transfer_chat_ownership(self, peer: str, new_owner_id: int) -> None:
        channel = await self._resolve_peer(peer)
        new_owner = {"_": "inputUser", "user_id": new_owner_id, "access_hash": self._peer_cache.get_user(new_owner_id) or 0}
        await self._rpc({
            "_": "channels.editCreator",
            "channel": channel,
            "user_id": new_owner,
            "password": {"_": "inputCheckPasswordEmpty"},
        })

    async def toggle_forum(self, peer: str, enabled: bool) -> None:
        channel = await self._resolve_peer(peer)
        await self._rpc({"_": "channels.toggleForum", "channel": channel, "enabled": enabled})

    async def get_forum_topics(self, peer: str, limit: int = 100) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "channels.getForumTopics",
            "channel": input_peer,
            "offset_date": 0,
            "offset_id": 0,
            "offset_topic": 0,
            "limit": limit,
        })
        return result.get("topics", []) if isinstance(result, dict) else []

    async def create_forum_topic(self, peer: str, title: str,
                                  icon_color: int | None = None,
                                  icon_emoji_id: int | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        req: dict = {
            "_": "channels.createForumTopic",
            "channel": input_peer,
            "title": title,
            "random_id": random.randint(0, 2**63 - 1),
        }
        if icon_color is not None:
            req["icon_color"] = icon_color
        if icon_emoji_id is not None:
            req["icon_emoji_id"] = icon_emoji_id
        await self._rpc(req)

    async def edit_forum_topic(self, peer: str, topic_id: int,
                                title: str | None = None,
                                closed: bool | None = None,
                                hidden: bool | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        req: dict = {"_": "channels.editForumTopic", "channel": input_peer, "topic_id": topic_id}
        if title is not None:
            req["title"] = title
        if closed is not None:
            req["closed"] = closed
        if hidden is not None:
            req["hidden"] = hidden
        await self._rpc(req)

    async def delete_forum_topic_history(self, peer: str, top_msg_id: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "channels.deleteTopicHistory", "channel": input_peer, "top_msg_id": top_msg_id})


    async def send_photo(self, peer: str, path: str, caption: str = "") -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        return await self._rpc({
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": {"_": "inputMediaUploadedPhoto", "file": file_input},
            "message": caption,
            "random_id": random.randint(-(2**63), 2**63 - 1),
        })

    async def send_file(self, peer: str, path: str, caption: str = "", mime_type: str | None = None) -> dict:
        return await self.send_document(peer, path, caption, mime_type)

    async def send_document(self, peer: str, path: str, caption: str = "", mime_type: str | None = None) -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        if mime_type is None:
            mime_type = "application/octet-stream"
        return await self._rpc({
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": {
                "_": "inputMediaUploadedDocument",
                "file": file_input,
                "mime_type": mime_type,
                "attributes": [{"_": "documentAttributeFilename", "file_name": os.path.basename(path)}],
            },
            "message": caption,
            "random_id": random.randint(-(2**63), 2**63 - 1),
        })

    async def send_audio(self, peer: str, path: str, caption: str = "") -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self.send_document(peer, path, caption, _AUDIO_MIME)

    async def send_video(self, peer: str, path: str, caption: str = "") -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self.send_document(peer, path, caption, _VIDEO_MIME)

    async def send_voice(self, peer: str, path: str, caption: str = "") -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self.send_document(peer, path, caption, _VOICE_MIME)

    async def send_sticker(self, peer: str, path: str) -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self.send_document(peer, path, "", _STICKER_MIME)

    async def upload_file(self, path: str) -> dict:
        PART_SIZE     = 512 * 1024
        BIG_THRESHOLD = 10 * 1024 * 1024
        file_id   = random.randint(-(2**63), 2**63 - 1)
        file_name = os.path.basename(path)
        file_size = os.path.getsize(path)
        is_big    = file_size >= BIG_THRESHOLD
        parts     = (file_size + PART_SIZE - 1) // PART_SIZE
        md5       = hashlib.md5()
        with open(path, "rb") as fh:
            for part_idx in range(parts):
                chunk = fh.read(PART_SIZE)
                if is_big:
                    req = {"_": "upload.saveBigFilePart", "file_id": file_id,
                           "file_part": part_idx, "file_total_parts": parts, "bytes": chunk}
                else:
                    md5.update(chunk)
                    req = {"_": "upload.saveFilePart", "file_id": file_id,
                           "file_part": part_idx, "bytes": chunk}
                ok = await self._rpc(req)
                if not ok:
                    raise RuntimeError(f"upload_file: part {part_idx} rejected")
        if is_big:
            return {"_": "inputFileBig", "id": file_id, "parts": parts, "name": file_name}
        return {"_": "inputFile", "id": file_id, "parts": parts, "name": file_name, "md5_checksum": md5.hexdigest()}

    async def upload_media(self, peer: str, path: str) -> int | None:
        result = await self.send_document(peer, path)
        msg = result.get("updates", [{}])[0] if isinstance(result.get("updates"), list) else {}
        return msg.get("id")

    async def download_media(self, peer: str, msg_id: int, path: str) -> str:
        msg = await self.get_message(peer, msg_id)
        if not msg:
            raise ValueError(f"Message {msg_id} not found")
        media = msg.get("media", {})
        return await self._download_media_object(media, path)

    async def _download_media_object(self, media: dict, path: str) -> str:
        if not isinstance(media, dict):
            raise ValueError("No media in message")
        t = media.get("_", "")
        if t == "messageMediaPhoto":
            photo = media.get("photo", {})
            sizes = photo.get("sizes", [])
            if not sizes:
                raise ValueError("Photo has no sizes")
            size = max(sizes, key=lambda s: s.get("size", 0) if isinstance(s, dict) else 0)
            location = {
                "_": "inputPhotoFileLocation",
                "id": photo.get("id", 0),
                "access_hash": photo.get("access_hash", 0),
                "file_reference": photo.get("file_reference", b""),
                "thumb_size": size.get("type", "s") if isinstance(size, dict) else "s",
            }
        elif t == "messageMediaDocument":
            doc = media.get("document", {})
            location = {
                "_": "inputDocumentFileLocation",
                "id": doc.get("id", 0),
                "access_hash": doc.get("access_hash", 0),
                "file_reference": doc.get("file_reference", b""),
                "thumb_size": "",
            }
        else:
            raise ValueError(f"Unsupported media type: {t}")
        offset = 0
        chunk_size = 1024 * 1024
        with open(path, "wb") as fh:
            while True:
                result = await self._rpc({
                    "_": "upload.getFile",
                    "location": location,
                    "offset": offset,
                    "limit": chunk_size,
                })
                data = result.get("bytes", b"") if isinstance(result, dict) else b""
                if not data:
                    break
                fh.write(data)
                offset += len(data)
                if len(data) < chunk_size:
                    break
        return path

    async def download_with_progress(self, peer: str, msg_id: int, path: str,
                                      on_progress: "Callable[[int, int], None] | None" = None) -> str:
        return await self.download_media(peer, msg_id, path)

    async def upload_with_progress(self, path: str,
                                    on_progress: "Callable[[int, int], None] | None" = None) -> str:
        result = await self.upload_file(path)
        return str(result.get("id", ""))

    async def edit_chat_photo(self, peer: str, path: str) -> None:
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        await self._rpc({
            "_": "messages.editChatPhoto",
            "chat_id": input_peer.get("chat_id") or input_peer.get("channel_id") or 0,
            "photo": {"_": "inputChatUploadedPhoto", "file": file_input},
        })

    async def delete_profile_photos(self) -> None:
        result = await self._rpc({"_": "photos.getUserPhotos", "user_id": {"_": "inputUserSelf"}, "offset": 0, "max_id": 0, "limit": 100})
        photos = result.get("photos", []) if isinstance(result, dict) else []
        if photos:
            ids = [{"_": "inputPhoto", "id": p.get("id", 0), "access_hash": p.get("access_hash", 0), "file_reference": p.get("file_reference", b"")} for p in photos]
            await self._rpc({"_": "photos.deletePhotos", "id": ids})

    async def get_profile_photos(self, peer: str, limit: int = 100) -> list[tuple[int, int, int]]:
        user_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "photos.getUserPhotos", "user_id": user_peer, "offset": 0, "max_id": 0, "limit": limit})
        photos = result.get("photos", []) if isinstance(result, dict) else []
        return [(p.get("id", 0), p.get("access_hash", 0), p.get("dc_id", 0)) for p in photos]


    async def block_user(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "contacts.block", "id": input_peer})

    async def unblock_user(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "contacts.unblock", "id": input_peer})

    async def get_blocked_users(self, limit: int = 100) -> list[int]:
        result = await self._rpc({"_": "contacts.getBlocked", "my_stories_from": False, "offset": 0, "limit": limit})
        blocked = result.get("blocked", []) if isinstance(result, dict) else []
        return [b.get("peer_id", {}).get("user_id", 0) for b in blocked]

    async def add_contact(self, user_id: int, first_name: str, last_name: str = "", phone: str = "") -> None:
        ah = self._peer_cache.get_user(user_id) or 0
        await self._rpc({
            "_": "contacts.addContact",
            "add_phone_privacy_exception": False,
            "id": {"_": "inputUser", "user_id": user_id, "access_hash": ah},
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
        })

    async def delete_contacts(self, user_ids: list[int]) -> None:
        ids = [{"_": "inputUser", "user_id": uid, "access_hash": self._peer_cache.get_user(uid) or 0} for uid in user_ids]
        await self._rpc({"_": "contacts.deleteContacts", "id": ids})

    async def get_common_chats(self, user_id: int, limit: int = 100) -> list[dict]:
        ah = self._peer_cache.get_user(user_id) or 0
        result = await self._rpc({
            "_": "messages.getCommonChats",
            "user_id": {"_": "inputUser", "user_id": user_id, "access_hash": ah},
            "max_id": 0,
            "limit": limit,
        })
        return result.get("chats", []) if isinstance(result, dict) else []

    async def search_peer(self, query: str) -> list[str]:
        result = await self._rpc({"_": "contacts.search", "q": query, "limit": 20})
        out = []
        for u in result.get("users", []) if isinstance(result, dict) else []:
            out.append(u.get("username") or str(u.get("id", "")))
        return out

    async def resolve_peer(self, peer: str) -> int:
        result = await self._resolve_peer(peer)
        return result.get("user_id") or result.get("channel_id") or result.get("chat_id") or 0

    async def resolve_username(self, username: str) -> int:
        uname = username.lstrip("@")
        result = await self._rpc({"_": "contacts.resolveUsername", "username": uname})
        peer = result.get("peer", {}) if isinstance(result, dict) else {}
        return peer.get("user_id") or peer.get("channel_id") or peer.get("chat_id") or 0

    async def resolve(self, peer: Any) -> dict:
        return await self._resolve_peer(peer)

    async def warm_peer_cache_from_dialogs(self) -> None:
        await self.get_dialogs(limit=500)


    async def get_authorizations(self) -> list[dict]:
        result = await self._rpc({"_": "account.getAuthorizations"})
        return result.get("authorizations", []) if isinstance(result, dict) else []

    async def terminate_session(self, hash: int) -> None:
        await self._rpc({"_": "account.resetAuthorization", "hash": hash})

    async def export_login_token(self) -> tuple[bytes, int]:
        api_id, api_hash = self._require_creds()
        result = await self._rpc({"_": "auth.exportLoginToken", "api_id": api_id, "api_hash": api_hash, "except_ids": []})
        return bytes(result.get("token", b"")), result.get("expires", 0)

    async def check_qr_login(self, token: bytes) -> str | None:
        try:
            result = await self._rpc({"_": "auth.acceptLoginToken", "token": token})
            return result.get("user", {}).get("username")
        except Exception:
            return None


    async def set_profile(self, first_name: str | None = None, last_name: str | None = None, about: str | None = None) -> None:
        req: dict = {"_": "account.updateProfile"}
        if first_name is not None:
            req["first_name"] = first_name
        if last_name is not None:
            req["last_name"] = last_name
        if about is not None:
            req["about"] = about
        await self._rpc(req)

    async def set_username(self, username: str) -> None:
        await self._rpc({"_": "account.updateUsername", "username": username})

    async def set_online(self) -> None:
        await self._rpc({"_": "account.updateStatus", "offline": False})

    async def set_offline(self) -> None:
        await self._rpc({"_": "account.updateStatus", "offline": True})

    async def get_privacy(self, key: "PrivacyKey | str") -> list[str]:
        key_map = {
            "status_timestamp": "inputPrivacyKeyStatusTimestamp",
            "phone": "inputPrivacyKeyPhoneNumber",
            "bio": "inputPrivacyKeyAbout",
            "profile_photo": "inputPrivacyKeyProfilePhoto",
            "forwards": "inputPrivacyKeyForwards",
            "voice_call": "inputPrivacyKeyPhoneCall",
            "groups": "inputPrivacyKeyChatInvite",
        }
        tl_key = key_map.get(str(key), str(key))
        result = await self._rpc({"_": "account.getPrivacy", "key": {"_": tl_key}})
        rules = result.get("rules", []) if isinstance(result, dict) else []
        return [r.get("_", "") for r in rules]

    async def set_privacy(self, key: "PrivacyKey | str", rule: "PrivacyRule | str") -> None:
        key_map = {
            "status_timestamp": "inputPrivacyKeyStatusTimestamp",
            "phone": "inputPrivacyKeyPhoneNumber",
        }
        rule_map = {
            "allow_all": "inputPrivacyValueAllowAll",
            "allow_contacts": "inputPrivacyValueAllowContacts",
            "disallow_all": "inputPrivacyValueDisallowAll",
        }
        tl_key  = key_map.get(str(key), str(key))
        tl_rule = rule_map.get(str(rule), str(rule))
        await self._rpc({"_": "account.setPrivacy", "key": {"_": tl_key}, "rules": [{"_": tl_rule}]})


    async def mute_chat(self, peer: str, mute_until: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "account.updateNotifySettings",
            "peer": {"_": "inputNotifyPeer", "peer": input_peer},
            "settings": {"_": "inputPeerNotifySettings", "mute_until": mute_until},
        })

    async def unmute_chat(self, peer: str) -> None:
        await self.mute_chat(peer, 0)

    async def get_notify_settings(self, peer: str) -> dict:
        input_peer = await self._resolve_peer(peer)
        return await self._rpc({"_": "account.getNotifySettings", "peer": {"_": "inputNotifyPeer", "peer": input_peer}})

    async def update_notify_settings(self, peer: str, mute_until: int | None = None,
                                      silent: bool | None = None, show_previews: bool | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        settings: dict = {"_": "inputPeerNotifySettings"}
        if mute_until is not None:
            settings["mute_until"] = mute_until
        if silent is not None:
            settings["silent"] = silent
        if show_previews is not None:
            settings["show_previews"] = show_previews
        await self._rpc({"_": "account.updateNotifySettings", "peer": {"_": "inputNotifyPeer", "peer": input_peer}, "settings": settings})


    async def set_bot_commands(self, commands: list[tuple[str, str]], lang_code: str = "") -> None:
        await self._rpc({
            "_": "bots.setBotCommands",
            "scope": {"_": "botCommandScopeDefault"},
            "lang_code": lang_code,
            "commands": [{"_": "botCommand", "command": c, "description": d} for c, d in commands],
        })

    async def delete_bot_commands(self, lang_code: str = "") -> None:
        await self._rpc({
            "_": "bots.resetBotCommands",
            "scope": {"_": "botCommandScopeDefault"},
            "lang_code": lang_code,
        })

    async def set_bot_info(self, name: str | None = None, about: str | None = None,
                           description: str | None = None, lang_code: str = "") -> None:
        req: dict = {"_": "bots.setBotInfo", "lang_code": lang_code}
        if name is not None:
            req["name"] = name
        if about is not None:
            req["about"] = about
        if description is not None:
            req["description"] = description
        await self._rpc(req)

    async def get_bot_info(self, lang_code: str = "") -> dict:
        return await self._rpc({"_": "bots.getBotInfo", "lang_code": lang_code})

    async def answer_callback_query(self, query_id: int, text: str | None = None, alert: bool = False) -> None:
        req: dict = {"_": "messages.setBotCallbackAnswer", "query_id": query_id, "alert": alert}
        if text:
            req["message"] = text
        await self._rpc(req)

    async def answer_inline_query(self, query_id: int,
                                   results: "list[InlineArticle | InlinePhoto | InlineDocument | tuple]",
                                   cache_time: int = 300, is_personal: bool = False,
                                   next_offset: str | None = None,
                                   switch_pm: "tuple[str, str] | None" = None) -> None:
        raw = [_inline_result_to_tuple(r) for r in results]
        tl_results = [_inline_tuple_to_tl(r) for r in raw]
        req: dict = {
            "_": "messages.setInlineBotResults",
            "query_id": query_id,
            "results": tl_results,
            "cache_time": cache_time,
            "is_personal": is_personal,
        }
        if next_offset is not None:
            req["next_offset"] = next_offset
        if switch_pm:
            req["switch_pm"] = {"_": "inlineBotSwitchPM", "text": switch_pm[0], "start_param": switch_pm[1]}
        await self._rpc(req)

    async def answer_inline_query_articles(self, query_id: int, articles: "list[tuple[str, str, str]]",
                                            cache_time: int = 300, is_personal: bool = False,
                                            next_offset: str | None = None) -> None:
        tl_results = [
            {"_": "inputBotInlineResult",
             "id": str(i),
             "type": "article",
             "title": title,
             "description": desc,
             "send_message": {"_": "inputBotInlineMessageText", "message": text}}
            for i, (title, desc, text) in enumerate(articles)
        ]
        req: dict = {
            "_": "messages.setInlineBotResults",
            "query_id": query_id,
            "results": tl_results,
            "cache_time": cache_time,
            "is_personal": is_personal,
        }
        if next_offset:
            req["next_offset"] = next_offset
        await self._rpc(req)

    async def edit_inline_message(self, msg_id: "InlineMessageId | tuple[int, bytes]",
                                   new_text: str, reply_markup=None) -> bool:
        if isinstance(msg_id, InlineMessageId):
            dc_id, id_bytes = msg_id.dc_id, msg_id.id_bytes
        else:
            dc_id, id_bytes = msg_id
        req: dict = {
            "_": "messages.editInlineBotMessage",
            "id": {"_": "inputBotInlineMessageID64", "dc_id": dc_id, "id": int.from_bytes(id_bytes[:8], "little")},
            "message": new_text,
            "no_webpage": True,
        }
        if reply_markup is not None:
            req["reply_markup"] = _markup_to_dict(reply_markup)
        await self._rpc(req)
        return True

    async def open_mini_app(self, peer: str, app_type: str = "main", app_value: str = "") -> dict:
        input_peer = await self._resolve_peer(peer)
        return await self._rpc({
            "_": "messages.requestWebView",
            "peer": input_peer,
            "bot": input_peer,
            "platform": "android",
        })


    async def get_broadcast_stats(self, peer: str, dark: bool = False) -> dict:
        channel = await self._resolve_peer(peer)
        return await self._rpc({"_": "stats.getBroadcastStats", "channel": channel, "dark": dark})

    async def get_megagroup_stats(self, peer: str, dark: bool = False) -> dict:
        channel = await self._resolve_peer(peer)
        return await self._rpc({"_": "stats.getMegagroupStats", "channel": channel, "dark": dark})


    async def get_chat_full(self, peer: str) -> tuple[int, str, int | None]:
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if "Channel" in t:
            result = await self._rpc({"_": "channels.getFullChannel", "channel": input_peer})
        else:
            result = await self._rpc({"_": "messages.getFullChat", "chat_id": input_peer.get("chat_id", 0)})
        full = result.get("full_chat", {}) if isinstance(result, dict) else {}
        return full.get("id", 0), full.get("about", ""), full.get("participants_count")

    async def get_admins_with_invites(self, peer: str) -> list[tuple[int, int]]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getAdminsWithInvites", "peer": input_peer})
        admins = result.get("admins", []) if isinstance(result, dict) else []
        return [(a.get("admin_id", 0), a.get("invites_count", 0)) for a in admins]

    async def get_custom_emoji_documents(self, document_ids: list[int]) -> list[int]:
        result = await self._rpc({"_": "messages.getCustomEmojiDocuments", "document_id": document_ids})
        docs = result if isinstance(result, list) else []
        return [d.get("id", 0) for d in docs if isinstance(d, dict)]

    async def get_game_high_scores(self, peer: str, msg_id: int, user_id: int) -> list[tuple[int, int, int]]:
        input_peer = await self._resolve_peer(peer)
        ah = self._peer_cache.get_user(user_id) or 0
        result = await self._rpc({
            "_": "messages.getGameHighScores",
            "peer": input_peer,
            "id": msg_id,
            "user_id": {"_": "inputUser", "user_id": user_id, "access_hash": ah},
        })
        scores = result.get("scores", []) if isinstance(result, dict) else []
        return [(s.get("pos", 0), s.get("user_id", 0), s.get("score", 0)) for s in scores]

    async def get_web_page_preview(self, text: str) -> str | None:
        result = await self._rpc({"_": "messages.getWebPagePreview", "message": text})
        if isinstance(result, dict) and result.get("_") == "messageMediaWebPage":
            page = result.get("webpage", {})
            return page.get("url") if isinstance(page, dict) else None
        return None

    async def send_invoice(self, peer: str, title: str, description: str, payload: str,
                           currency: str, prices: list[tuple[str, int]],
                           photo_url: str | None = None, need_name: bool = False,
                           need_phone: bool = False, need_email: bool = False,
                           need_shipping_address: bool = False, is_flexible: bool = False) -> dict:
        input_peer = await self._resolve_peer(peer)
        invoice: dict = {
            "_": "invoice",
            "currency": currency,
            "prices": [{"_": "labeledPrice", "label": l, "amount": a} for l, a in prices],
            "test": False,
            "name_requested": need_name,
            "phone_requested": need_phone,
            "email_requested": need_email,
            "shipping_address_requested": need_shipping_address,
            "flexible": is_flexible,
        }
        media: dict = {
            "_": "inputMediaInvoice",
            "title": title,
            "description": description,
            "invoice": invoice,
            "payload": payload.encode(),
            "provider": "",
            "provider_data": {"_": "dataJSON", "data": "{}"},
        }
        if photo_url:
            media["photo"] = {"_": "inputWebDocument", "url": photo_url, "size": 0, "mime_type": "image/jpeg", "attributes": []}
        return await self._rpc({
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": media,
            "message": "",
            "random_id": random.randint(-(2**63), 2**63 - 1),
        })

    async def join_request(self, peer: str, user_id: int, approve: bool) -> None:
        input_peer = await self._resolve_peer(peer)
        ah = self._peer_cache.get_user(user_id) or 0
        user = {"_": "inputUser", "user_id": user_id, "access_hash": ah}
        if approve:
            await self._rpc({"_": "messages.hideChatJoinRequest", "peer": input_peer, "user_id": user, "approved": True})
        else:
            await self._rpc({"_": "messages.hideChatJoinRequest", "peer": input_peer, "user_id": user, "approved": False})

    async def all_join_requests(self, peer: str, approve: bool, link: str | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        req: dict = {"_": "messages.hideAllChatJoinRequests", "peer": input_peer, "approved": approve}
        if link:
            req["link"] = link
        await self._rpc(req)

    async def signal_network_restored(self) -> None:
        pass


    async def invite_links(self, peer: str, *, primary_only: bool = False, revoked: bool = False, limit: int = 100):
        input_peer = await self._resolve_peer(peer)
        if primary_only:
            return await self._rpc({"_": "messages.exportChatInvite", "peer": input_peer})
        me = await self.get_me()
        return await self._rpc({
            "_": "messages.getExportedChatInvites",
            "peer": input_peer,
            "admin_id": {"_": "inputUser", "user_id": me.get("id", 0), "access_hash": self._peer_cache.get_user(me.get("id", 0)) or 0},
            "revoked": revoked,
            "limit": limit,
        })

    async def iter_invite_links(self, peer: str, *, revoked: bool = False):
        result = await self.invite_links(peer, revoked=revoked, limit=100)
        invites = result.get("invites", []) if isinstance(result, dict) else []
        for link in invites:
            yield link

    async def iter_invite_link_members(self, peer: str, link: str, *, requested: bool = False):
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getChatInviteImporters",
            "peer": input_peer,
            "link": link,
            "requested": requested,
            "offset_date": 0,
            "offset_user": {"_": "inputUserEmpty"},
            "limit": 100,
        })
        importers = result.get("importers", []) if isinstance(result, dict) else []
        for m in importers:
            yield m

    async def edit_invite_link(self, peer: str, link: str, *, expire_date: int | None = None,
                                usage_limit: int | None = None, request_needed: bool | None = None,
                                title: str | None = None):
        input_peer = await self._resolve_peer(peer)
        req: dict = {"_": "messages.editExportedChatInvite", "peer": input_peer, "link": link}
        if expire_date is not None:
            req["expire_date"] = expire_date
        if usage_limit is not None:
            req["usage_limit"] = usage_limit
        if request_needed is not None:
            req["request_needed"] = request_needed
        if title is not None:
            req["title"] = title
        return await self._rpc(req)

    async def revoke_invite_link(self, peer: str, link: str):
        input_peer = await self._resolve_peer(peer)
        return await self._rpc({"_": "messages.editExportedChatInvite", "peer": input_peer, "link": link, "revoked": True})

    async def delete_invite_link(self, peer: str, link: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.deleteExportedChatInvite", "peer": input_peer, "link": link})

    async def clear_revoked_invite_links(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        me = await self.get_me()
        ah = self._peer_cache.get_user(me.get("id", 0)) or 0
        await self._rpc({
            "_": "messages.deleteRevokedExportedChatInvites",
            "peer": input_peer,
            "admin_id": {"_": "inputUser", "user_id": me.get("id", 0), "access_hash": ah},
        })

    async def resolve_invite_link(self, link: str):
        return await self._rpc({"_": "messages.checkChatInvite", "hash": _extract_invite_hash(link)})

    async def join_invite_link(self, link: str):
        return await self._rpc({"_": "messages.importChatInvite", "hash": _extract_invite_hash(link)})

    async def iter_reaction_users(self, peer: str, msg_id: int, *, reaction: str | None = None):
        input_peer = await self._resolve_peer(peer)
        req: dict = {"_": "messages.getMessageReactionsList", "peer": input_peer, "id": msg_id, "limit": 100}
        if reaction:
            req["reaction"] = {"_": "reactionEmoji", "emoticon": reaction}
        result = await self._rpc(req)
        reactions = result.get("reactions", []) if isinstance(result, dict) else []
        for r in reactions:
            yield r


    async def iter_dialogs(self, *, limit: int | None = None):
        fetch_limit = limit if limit is not None else 5000
        dialogs = await self.get_dialogs(fetch_limit)
        for d in dialogs:
            yield d

    async def iter_messages(self, peer: str, *, limit: int | None = None, offset_id: int = 0):
        remaining = limit
        cur_offset = offset_id
        batch = 100
        while True:
            chunk_size = batch if remaining is None else min(batch, remaining)
            if chunk_size <= 0:
                return
            msgs = await self.get_message_history(peer, chunk_size, cur_offset)
            if not msgs:
                return
            for m in msgs:
                yield m
            if remaining is not None:
                remaining -= len(msgs)
                if remaining <= 0:
                    return
            if len(msgs) < chunk_size:
                return
            cur_offset = msgs[-1].get("id", 0)


    async def invoke(self, func: Any) -> dict:
        if hasattr(func, "to_bytes"):
            tl_bytes = func.to_bytes()
        elif isinstance(func, dict):
            tl_bytes = _tl.serialize(func, _SCHEMA)
        else:
            tl_bytes = _tl.serialize_object(func.to_dict(), _SCHEMA)
        conn = self._require_conn()
        resp_bytes = await conn.rpc_call(tl_bytes)
        result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
        self._populate_cache(result)
        return result

    async def __call__(self, func: Any) -> dict:
        return await self.invoke(func)

    def __repr__(self) -> str:
        state = "connected" if self._conn else "disconnected"
        return f"Client(session={self.session!r}, {state})"


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


def _inline_tuple_to_tl(r: tuple) -> dict:
    kind = r[0] if r else "article"
    if kind == "article":
        _, id_, title, desc, text = r
        return {
            "_": "inputBotInlineResult",
            "id": str(id_),
            "type": "article",
            "title": title,
            "description": desc,
            "send_message": {"_": "inputBotInlineMessageText", "message": text},
        }
    return {}


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
