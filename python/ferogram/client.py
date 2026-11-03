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

import asyncio
import inspect
import os
import time
from contextlib import asynccontextmanager, suppress
from typing import Any, Callable

from ._ferogram import DcConnection, MessageBox
from ._ferogram import (
    FileSession, MemorySession, StringSession,
    SqliteSession, CustomSession,
)
from .raw import tl as _tl
from .rich import _RichMixin
from .raw.generated._tl_schema import _SCHEMA, _SCHEMA_BY_CID, LAYER
from .raw.proxy import RawProxy, PeerCache, resolve_peer as _resolve_peer_fn
from .types import (
    Message,
)
from .updates import wrap_update
from .methods import (
    AuthMethods,
    UserMethods,
    MessageMethods,
    DialogMethods,
    ChatMethods,
    ParticipantMethods,
    InviteMethods,
    MediaMethods,
    BotMethods,
)
from ._internal import (
    _log,  # noqa: F401
    _ClientLoggerAdapter,  # noqa: F401
    _session_tag,  # noqa: F401
    SignInCodeInvalid,  # noqa: F401
    _Handler,  # noqa: F401
    _DEVICE_MODEL,  # noqa: F401
    _SYSTEM_VERSION,  # noqa: F401
    _APP_VERSION,  # noqa: F401
    _LANG_CODE,  # noqa: F401
    _SYSTEM_LANG,  # noqa: F401
    _LANG_PACK,  # noqa: F401
    _CID_INVOKE_WITH_LAYER,  # noqa: F401
    _CID_INIT_CONNECTION,  # noqa: F401
    _CID_HELP_GET_CONFIG,  # noqa: F401
    _CID_IMPORT_AUTHORIZATION,  # noqa: F401
    _pack_u32,  # noqa: F401
    _pack_i32,  # noqa: F401
    _pack_i64,  # noqa: F401
    _pack_str,  # noqa: F401
    _pack_bytes,  # noqa: F401
    _build_init_connection,  # noqa: F401
    _build_invoke_with_layer,  # noqa: F401
    _build_help_get_config,  # noqa: F401
    _build_import_authorization,  # noqa: F401
    _parse_proxy_link,  # noqa: F401
    StopPropagation,  # noqa: F401
    ContinuePropagation,  # noqa: F401
    _ALL_EVENTS,  # noqa: F401
    _markup_to_dict,  # noqa: F401
    _extract_invite_hash,  # noqa: F401
    _inline_tuple_to_tl,  # noqa: F401
    _srp_answer,  # noqa: F401
    _parse_migrate,  # noqa: F401
    _is_bot_token,  # noqa: F401
)
from .transfer import (
    TransferHandle,  # noqa: F401
    TransferCancelled,  # noqa: F401
    TransferLimits,  # noqa: F401
    _quality_candidates,  # noqa: F401
    _video_resolution,  # noqa: F401
    available_qualities,  # noqa: F401
    _resolve_quality_document,  # noqa: F401
    _AUDIO_MIME,  # noqa: F401
    _VIDEO_MIME,  # noqa: F401
    _VOICE_MIME,  # noqa: F401
    _STICKER_MIME,  # noqa: F401
)

__all__ = ["Client", "StopPropagation", "ContinuePropagation", "TransferHandle", "TransferLimits", "TransferCancelled", "SignInCodeInvalid", "available_qualities"]

class Client(AuthMethods, UserMethods, MessageMethods, DialogMethods, ChatMethods, ParticipantMethods, InviteMethods, MediaMethods, BotMethods, _RichMixin):
    def __init__(
        self,
        session: "str | FileSession | MemorySession | StringSession | SqliteSession | CustomSession" = "ferogram",
        *,
        api_id: int | None = None,
        api_hash: str | None = None,
        bot_token: str | None = None,
        phone: str | None = None,
        password: str | None = None,
        proxy: str | None = None,
        proxy_secret: str | None = None,
        proxy_link: str | None = None,
        domain: str | None = None,
        transport: str | None = None,
        test_mode: bool = False,
        dc_id: int = 0,
        allow_ipv6: bool = False,
        dc_addr: str | None = None,
        resilient_connect: bool = False,
        catch_up: bool = False,
        pfs: bool = False,
        future_auth_token: bytes | None = None,
        device: str | None = None,
        system_version: str | None = None,
        app_version: str | None = None,
        lang_code: str | None = None,
        system_lang_code: str | None = None,
        lang_pack: str | None = None,
        session_string: str | None = None,
        update_queue_capacity: int | None = None,
        update_overflow: str | None = "drop_oldest",
        parse_mode: str | None = None,
        workers: int = 4,
        flood_sleep_threshold: int = 60,
        transfer_limits: "TransferLimits | None" = None,
    ) -> None:
        self.session                  = session
        self._log                     = _ClientLoggerAdapter(_log, {"client": _session_tag(session, session_string)})
        self.api_id                   = api_id or int(os.environ.get("API_ID", 0)) or None
        self.api_hash                 = api_hash or os.environ.get("API_HASH")
        self.bot_token                = bot_token or os.environ.get("BOT_TOKEN")
        self._phone                   = phone
        self._password                = password
        self.proxy                    = proxy
        # `proxy_secret` only configures the AES-obfuscation secret used
        # together with `transport="obfuscated"`/`"padded_intermediate"`.
        # It does not address a proxy on its own - `proxy` above is a SOCKS5
        # relay, unrelated to MTProxy. Pass a full `tg://proxy?...` link via
        # `proxy_link` instead for the common case; it derives dc_addr,
        # transport, and proxy_secret from the link for you.
        self.proxy_secret             = proxy_secret
        # "full" (default), "abridged", "intermediate", "http",
        # "obfuscated", "padded_intermediate", or "fastest" (races a couple
        # of built-in transports on a fresh handshake only; a resumed
        # connection with a saved key ignores this and reuses whatever
        # transport it was established on).
        self.transport                = transport
        # SNI hostname presented in the fake TLS ClientHello. Only used (and
        # required) when `transport="faketls"`; ignored for every other
        # transport.
        self.domain                   = domain
        self.test_mode                = test_mode
        # 0 = auto (session's persisted home DC, else DC2). Only applied on
        # the initial connect in start() - _migrate() and worker
        # connections always target an explicit DC of their own.
        self._dc_id_override          = dc_id
        self.allow_ipv6               = allow_ipv6
        self.dc_addr                  = dc_addr
        if proxy_link:
            # An MTProxy link dictates its own address and transport, same
            # as ferogram's Rust `ClientBuilder.proxy_link()` - it wins over
            # any `dc_addr`/`transport`/`proxy_secret`/`domain` passed
            # alongside it. Connecting to the proxy's host:port with the
            # transport it requires is functionally identical to the Rust
            # core's dedicated MTProxy path: both just apply the same
            # obfuscated/padded-intermediate/faketls framing to whatever
            # address gets dialed.
            derived = _parse_proxy_link(proxy_link)
            self.dc_addr      = derived["dc_addr"]
            self.transport    = derived["transport"]
            self.proxy_secret = derived["proxy_secret"]
            self.domain       = derived["domain"]
        self.resilient_connect        = resilient_connect
        self.catch_up                 = catch_up
        self.pfs                      = pfs
        # Seeds a future_auth_token for fast re-login on the very first
        # connect, for stateless setups that store the token themselves
        # instead of relying on the session file. Only applied if the
        # session doesn't already have one persisted - see start().
        self._future_auth_token       = future_auth_token
        self.device                   = device or _DEVICE_MODEL
        self.system_version           = system_version or _SYSTEM_VERSION
        self.app_version              = app_version or _APP_VERSION
        self.lang_code                = lang_code or _LANG_CODE
        self.system_lang_code         = system_lang_code or _SYSTEM_LANG
        self.lang_pack                = lang_pack or _LANG_PACK
        self.session_string           = session_string
        self.update_queue_capacity    = update_queue_capacity
        self.update_overflow          = update_overflow
        self.parse_mode               = parse_mode
        self._workers                 = workers
        self._flood_sleep_threshold   = flood_sleep_threshold
        self._transfer_limits         = transfer_limits or TransferLimits()
        # Bounds total worker connections open at once across every
        # concurrent upload/download this client is running - mirrors the
        # Rust core's `max_tcp_connections` (the "city-wide speed limit").
        self._transfer_semaphore      = asyncio.Semaphore(self._transfer_limits.max_tcp_connections)
        self._conn: DcConnection | None = None
        self._frame_pump_task: asyncio.Task | None = None
        # Periodic flush of the peer access-hash cache to the session file.
        # Mirrors the Rust core's dirty-flag + 60s interval snapshot saver:
        # the cache changes far more often than it's worth hitting disk for,
        # so writes are batched instead of happening on every new peer.
        self._peer_cache_save_task: asyncio.Task | None = None
        self._peer_cache_save_interval = 60
        self._dc_id: int = 0
        # DCs we've already bound a worker connection's auth key to via
        # auth.importAuthorization this process run (export tokens are
        # single-use, so this is only ever done once per foreign DC).
        self._auth_imported_dcs: set[int] = set()
        # DcConnection.connect() loads + saves the session file on every
        # call. Worker connections for parallel transfers are opened one at
        # a time under this lock so two opens can't race that load/save
        # cycle and clobber each other's auth key entries.
        self._worker_conn_lock = asyncio.Lock()
        self._handlers: dict[str, dict[int, list[_Handler]]] = {
            e: {} for e in _ALL_EVENTS
        }
        # _dispatch() runs on every incoming update and needs handler groups
        # in ascending order; handlers are registered once at startup but
        # dispatched at update-rate, so cache the sort instead of redoing
        # it per update. Invalidated in _add_handler().
        self._handler_groups_sorted: dict[str, list[int]] = {}
        self._update_queue: asyncio.Queue | None = None
        self._peer_cache = PeerCache()
        # Owns pts/qts/date/seq + per-channel pts and does the actual gap
        # detection/buffering (see ferogram-msgbox). Lives here, not on
        # DcConnection, so it survives a DC migration - `start()`/`_migrate()`
        # rebind it to whichever connection is current via
        # `conn.bind_message_box(self._message_box)`.
        self._message_box = MessageBox()
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
        self._handler_groups_sorted.pop(event_type, None)

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
        groups = self._handler_groups_sorted.get(event_type)
        if groups is None:
            groups = sorted(self._handlers.get(event_type, {}).keys())
            self._handler_groups_sorted[event_type] = groups
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
                    self._log.error("handler error in %s: %s", event_type, exc, exc_info=True)
                break

    async def _enqueue_update(self, item: tuple) -> None:
        """Put an update on the dispatch queue, honoring `update_overflow`.

        - "drop_oldest" (default): when full, evict the queue's oldest item
          to make room for the incoming one (mirrors the Rust core's default
          `OverflowStrategy::DropOldest`).
        - "drop_newest": when full, drop the incoming item and keep the
          queue as-is.
        - None: block until there's room - never drops an update. Opt-in
          only; not the default, since an unbounded stall here can back up
          the whole update pipeline.
        """
        if self.update_overflow is None:
            await self._update_queue.put(item)
            return
        try:
            self._update_queue.put_nowait(item)
        except asyncio.QueueFull:
            if self.update_overflow == "drop_oldest":
                try:
                    self._update_queue.get_nowait()
                    self._update_queue.task_done()
                except asyncio.QueueEmpty:
                    pass
                self._update_queue.put_nowait(item)
            elif self.update_overflow == "drop_newest":
                pass
            else:
                raise ValueError(
                    f"unknown update_overflow {self.update_overflow!r}; "
                    "expected None, 'drop_oldest', or 'drop_newest'"
                )

    async def _worker(self) -> None:
        while True:
            item = await self._update_queue.get()
            try:
                if item is None:
                    return
                event_type, update = item
                await self._dispatch(event_type, update)
            except Exception as exc:
                self._log.error("worker error: %s", exc, exc_info=True)
            finally:
                self._update_queue.task_done()

    # Update-type routing, split into three buckets: the two that need
    # unwrapping ("message" lives inside the update, or falls back to the
    # update itself for short forms) and everything else, which is a plain
    # 1:1 type->event_type mapping. _route_update runs on every incoming
    # update, so this trades ~15 sequential string comparisons for a couple
    # of set/dict lookups.
    _MESSAGE_WRAP_TYPES = frozenset((
        "updateNewMessage", "updateNewChannelMessage",
        "updateNewScheduledMessage", "updateShortMessage",
    ))

    _EDITED_WRAP_TYPES = frozenset(("updateEditMessage", "updateEditChannelMessage"))

    _SIMPLE_ROUTE_MAP = {
        "updateDeleteMessages":        "message_deleted",
        "updateBotCallbackQuery":      "callback_query",
        "updateInlineBotCallbackQuery": "callback_query",
        "updateBotInlineQuery":        "inline_query",
        "updateBotInlineSend":         "inline_send",
        "updateUserStatus":            "user_status",
        "updateUserTyping":            "chat_action",
        "updateChatUserTyping":        "chat_action",
        "updateChannelUserTyping":     "chat_action",
        "updateChannelParticipant":    "participant_update",
        "updateBotJoinRequest":        "join_request",
        "updateMessageReactions":      "message_reaction",
        "updateMessagePoll":           "poll_vote",
        "updateBotStopped":            "bot_stopped",
        "updateBotShippingQuery":      "shipping_query",
        "updateBotPrecheckoutQuery":   "pre_checkout_query",
        "updateBotChatBoost":          "chat_boost",
    }

    def _route_update(self, upd: dict) -> tuple[str, Any] | None:
        t = upd.get("_", "")
        if t in self._MESSAGE_WRAP_TYPES:
            return ("message", upd.get("message") or upd)
        if t in self._EDITED_WRAP_TYPES:
            return ("edited_message", upd.get("message") or upd)
        event_type = self._SIMPLE_ROUTE_MAP.get(t)
        if event_type is not None:
            return (event_type, upd)
        # everything else goes to raw_update
        return ("raw_update", upd)

    async def _dispatch_raw_batch(
        self, updates_b: list[bytes], users_b: list[bytes], chats_b: list[bytes],
    ) -> None:
        """Deserialize a `(updates, users, chats)` batch of individually
        TL-serialized items (as returned by `MessageBox.apply_difference`,
        `apply_channel_difference`, or `process_raw`) and route/enqueue each
        update exactly like the old dict-based diff path did.
        """
        if users_b or chats_b:
            self._populate_cache({
                "users": [_tl.deserialize(b, _SCHEMA_BY_CID) for b in users_b],
                "chats": [_tl.deserialize(b, _SCHEMA_BY_CID) for b in chats_b],
            })
        for b in updates_b:
            upd = _tl.deserialize(b, _SCHEMA_BY_CID)
            routed = self._route_update(upd)
            if routed is None:
                continue
            event_type, event = routed
            self._log.debug("dispatching %s", event_type)
            wrapped = wrap_update(event_type, event)
            if event_type in ("message", "edited_message"):
                entity = wrapped.message
            else:
                entity = wrapped
            if hasattr(entity, "_client"):
                entity._client = self
            await self._enqueue_update((event_type, entity))

    async def _run_updates(self) -> None:
        self._log.debug("update loop started")
        self._update_queue = asyncio.Queue(
            maxsize=self.update_queue_capacity or (self._workers * 4)
        )
        worker_tasks = [
            asyncio.create_task(self._worker())
            for _ in range(self._workers)
        ]
        try:
            # Seed pts/qts/date/seq. seed_state() re-checks emptiness and
            # writes atomically in one lock acquisition on the Rust side, so
            # a real update landing during the getState RPC below (this box
            # is bound to the live connection) can't race the write and
            # trip MessageBox's is-empty invariant - it just means seeding
            # is skipped because the live update already got there first.
            if await self._message_box.is_empty():
                try:
                    state = await self._rpc({"_": "updates.getState"})
                    seeded = await self._message_box.seed_state(
                        state.get("pts", 0), state.get("qts", 0),
                        state.get("date", 0), state.get("seq", 0),
                    )
                    if seeded:
                        self._log.debug(
                            "seeded state: pts=%s qts=%s date=%s seq=%s",
                            state.get("pts", 0), state.get("qts", 0),
                            state.get("date", 0), state.get("seq", 0),
                        )
                    else:
                        self._log.debug(
                            "getState returned but message_box was already "
                            "seeded by a live update in the meantime; skipped"
                        )
                except Exception as e:
                    self._log.warning("getState failed: %s", e)

            while True:
                conn = self._conn
                if conn is None:
                    return

                # MessageBox is the single authority on timing: it reports
                # 0.0 the instant a diff is actually owed (gap detected, or
                # the no-updates deadline elapsed), and a longer wait otherwise.
                delay = await self._message_box.check_deadline_secs()
                if delay > 0:
                    # Cap the sleep so cancellation/shutdown stays responsive
                    # even if a channel's deadline is far out.
                    await asyncio.sleep(min(delay, 30.0))
                    continue

                # Global (pts/qts) difference, if one is due.
                req = await self._message_box.get_difference_bytes()
                if req is not None:
                    try:
                        body = await conn.rpc_call(req)
                    except Exception as e:
                        self._log.debug("getDifference error: %s", e)
                        await self._message_box.abort_difference()
                        await asyncio.sleep(2)
                        continue
                    try:
                        updates_b, users_b, chats_b = await self._message_box.apply_difference(body)
                    except Exception as e:
                        self._log.warning("apply_difference failed: %s", e)
                        await self._message_box.abort_difference()
                        continue
                    self._log.debug("global diff applied: %d updates", len(updates_b))
                    await self._dispatch_raw_batch(updates_b, users_b, chats_b)
                    continue

                # Otherwise, a specific channel may need getChannelDifference.
                chan = await self._message_box.next_channel_diff()
                if chan is None:
                    # Nothing owed right now; re-check next deadline.
                    continue
                channel_id, pts = chan
                access_hash = self._peer_cache.get_channel(channel_id)
                if access_hash is None:
                    # Can't build a valid request without the access_hash -
                    # give up on this round; it'll be retried once the
                    # channel gets resolved through normal use (e.g. the
                    # next message the client sends/receives there).
                    self._log.debug(
                        "channel %s: no access_hash cached, skipping diff at pts=%s "
                        "(will retry once the channel is resolved through normal use)",
                        channel_id, pts,
                    )
                    await self._message_box.end_channel_difference(banned=False)
                    continue
                try:
                    diff = await self._rpc({
                        "_": "updates.getChannelDifference",
                        "force": False,
                        "channel": {
                            "_": "inputChannel",
                            "channel_id": channel_id,
                            "access_hash": access_hash,
                        },
                        "filter": {"_": "channelMessagesFilterEmpty"},
                        "pts": pts,
                        "limit": 100,
                    }, return_bytes=True)
                except Exception as e:
                    msg = str(e)
                    banned = "CHANNEL_PRIVATE" in msg or "CHANNEL_INVALID" in msg
                    self._log.debug("getChannelDifference error for %s: %s", channel_id, e)
                    await self._message_box.end_channel_difference(banned=banned)
                    continue
                try:
                    updates_b, users_b, chats_b = await self._message_box.apply_channel_difference(diff)
                except Exception as e:
                    self._log.warning("apply_channel_difference failed for %s: %s", channel_id, e)
                    await self._message_box.end_channel_difference(banned=False)
                    continue
                self._log.debug("channel %s diff applied: %d updates", channel_id, len(updates_b))
                await self._dispatch_raw_batch(updates_b, users_b, chats_b)

        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            for _ in worker_tasks:
                await self._update_queue.put(None)
            await asyncio.gather(*worker_tasks)

    async def _run_frame_pump(self) -> None:
        """Drain `DcConnection.recv_frame()` and feed pushed update frames
        into the MessageBox as they arrive.

        `_run_updates()` only discovers updates when it already knows a gap
        exists (via `check_deadline_secs()`), so it needs something reading
        the socket continuously to notice pushed updates at all. This is
        that reader: it runs alongside `_run_updates()`, not instead of it -
        the deadline/gap poll is still what performs the actual catch-up
        diff, including for channels.

        Reads `self._conn` fresh every iteration instead of capturing it
        once, since `_migrate()` swaps that attribute out. A connection
        already blocked inside `recv_frame()` can't observe that swap until
        the call returns, so `_migrate()` cancels and restarts this task
        against the new connection rather than relying on the fresh read
        alone.
        """
        self._log.debug("frame pump started")
        while True:
            conn = self._conn
            if conn is None:
                return
            frame = await conn.recv_frame()
            if frame is None:
                self._log.warning("frame pump: sender task shut down; pushed updates stopped arriving")
                return
            kind, payload = frame
            if kind == "update":
                try:
                    result = await self._message_box.process_raw(payload)
                except Exception as e:
                    self._log.debug("process_raw failed for pushed frame: %s", e)
                    continue
                if result is None:
                    # No dispatchable content, or a gap was detected -
                    # _run_updates()'s deadline poll will catch it up.
                    continue
                updates_b, users_b, chats_b = result
                self._log.debug("pushed frame applied: %d updates", len(updates_b))
                await self._dispatch_raw_batch(updates_b, users_b, chats_b)
            elif kind == "connected":
                self._log.debug("frame pump: sender task (re)connected")
                await self._message_box.mark_gap()
            elif kind == "error":
                self._log.warning("frame pump: connection error: %s", payload.decode("utf-8", "replace"))
                # Streaming connections aren't reconnected in place here;
                # stop the pump rather than loop silently on a dead socket.
                return

    async def _rpc(
        self, obj: dict, _retried_restart: bool = False, return_bytes: bool = False,
    ) -> dict | bytes:
        conn = self._require_conn()
        method = obj.get("_", "?")
        req_bytes = _tl.serialize(obj, _SCHEMA)
        t0 = time.monotonic()
        try:
            resp_bytes = await conn.rpc_call(req_bytes)
        except RuntimeError as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            msg = str(e)
            dc = _parse_migrate(msg)
            if dc is not None:
                self._log.debug("rpc %s failed after %dms: %s", method, elapsed_ms, msg)
                await self._migrate(dc, reason=f"{method} -> {msg}")
                return await self._rpc(obj, return_bytes=return_bytes)
            if "SESSION_PASSWORD_NEEDED" in msg:
                if return_bytes:
                    raise
                return {"_": "rpc_error", "error_code": 401,
                        "error_message": "SESSION_PASSWORD_NEEDED"}
            if "AUTH_RESTART" in msg and not _retried_restart:
                # AUTH_RESTART is transient right after a fresh auth key is
                # created on a new DC (e.g. after migrating for auth.sendCode).
                # Telegram expects the same request to simply be resent.
                self._log.debug("AUTH_RESTART received for %s, retrying request once", method)
                return await self._rpc(obj, _retried_restart=True, return_bytes=return_bytes)
            self._log.debug("rpc %s failed after %dms: %s", method, elapsed_ms, msg)
            raise
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        self._log.debug("rpc %s (%dms)", method, elapsed_ms)
        if return_bytes:
            # Caller needs the exact wire bytes (e.g. to feed straight into
            # `MessageBox.apply_difference`/`apply_channel_difference`), not
            # the dict form. Cache population still runs off a best-effort
            # dict decode so peer resolution keeps working either way.
            try:
                self._populate_cache(_tl.deserialize(resp_bytes, _SCHEMA_BY_CID))
            except Exception:
                pass
            return resp_bytes
        result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
        self._populate_cache(result)
        return result

    async def _migrate(self, dc_id: int, reason: str = "") -> None:
        api_id, api_hash = self._require_creds()
        if reason:
            self._log.info("migrating to DC%d (%s)", dc_id, reason)
        else:
            self._log.info("migrating to DC%d", dc_id)
        session = self.session
        if isinstance(session, str):
            path = session if session.endswith(".session") else session + ".session"
            from ._ferogram import FileSession
            session = FileSession(path)
        t0 = time.monotonic()
        self._conn = await DcConnection.connect(
            session, api_id, api_hash, dc_id,
            test_mode=self.test_mode, transport=self.transport,
            proxy_secret=self.proxy_secret, domain=self.domain,
            proxy=self.proxy, pfs=self.pfs,
            flood_sleep_threshold=self._flood_sleep_threshold,
            stream_updates=True,
        )
        self._dc_id = dc_id
        self._log.extra["client"] = f"{_session_tag(self.session, self.session_string)} dc{self._dc_id}"
        # Same MessageBox, new connection - rebind so pts/qts/gap state
        # carries over the migration instead of resetting.
        self._conn.bind_message_box(self._message_box)
        # The pump task (if `run_until_disconnected()` started one) is
        # sitting in an `await conn.recv_frame()` on the *old* connection
        # object, which just got replaced above - it can't see the swap
        # until that await returns (which, for a healthy old connection,
        # may be a long time / never). Restart it against the new one
        # rather than leave pushed updates undrained after a migration.
        if self._frame_pump_task is not None:
            self._frame_pump_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._frame_pump_task
            self._frame_pump_task = asyncio.create_task(self._run_frame_pump())
        await self._init_connection()
        connect_ms = int((time.monotonic() - t0) * 1000)
        self._log.info("migrated to DC%d in %dms", dc_id, connect_ms)

    async def _init_connection_on(self, conn: "DcConnection", inner: bytes | None = None) -> dict:
        """Send invokeWithLayer(initConnection(...)) on an arbitrary connection.

        `inner` defaults to help.getConfig (the normal registration query).
        Pass a different pre-serialized inner query (e.g.
        auth.importAuthorization) to combine connection registration with
        authorization binding in a single round trip -- the same thing
        ferogram's Rust core does in `Client::open_worker_conn`.
        """
        api_id, _ = self._require_creds()
        if inner is None:
            inner = _build_help_get_config()
        init = _build_init_connection(
            api_id, self.device, self.system_version, self.app_version,
            self.system_lang_code, self.lang_pack, self.lang_code, inner,
        )
        wrapped = _build_invoke_with_layer(LAYER, init)
        resp_bytes = await conn.rpc_call(wrapped)
        return _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)

    async def _init_connection(self) -> None:
        config = await self._init_connection_on(self._require_conn())
        await self._apply_dc_options(config.get("dc_options") or [])

    async def _apply_dc_options(self, dc_options: "list[dict]") -> None:
        """Persist the address help.getConfig reports for our current DC,
        honoring `allow_ipv6`. Only touches the DC we're connected to right
        now - not a full multi-DC table refresh, and it never forces a
        reconnect; it just makes the *next* connect pick the right family.
        """
        if not dc_options or self._conn is None:
            return
        best = None
        for opt in dc_options:
            if opt.get("id") != self._dc_id:
                continue
            if opt.get("media_only") or opt.get("cdn") or opt.get("tcpo_only"):
                continue
            if bool(opt.get("ipv6")) == self.allow_ipv6:
                best = opt
                break
            if best is None:
                best = opt  # fallback: still connectable, just not the preferred family
        if best is None:
            return
        addr = f"{best['ip_address']}:{best['port']}"
        try:
            await self._conn.set_dc_addr(self._dc_id, addr)
        except Exception as exc:
            self._log.debug("failed to persist DC address from getConfig: %s", exc)

    def _session_backend(self):
        """Resolve self.session into a concrete session backend object."""
        session = self.session
        if self.session_string:
            return StringSession(self.session_string)
        if isinstance(session, str):
            path = session if session.endswith(".session") else session + ".session"
            return FileSession(path)
        return session

    async def _open_worker_conn(self, dc_id: int | None = None) -> "DcConnection":
        """Open an independent, fully-authorized DcConnection to `dc_id`.

        This is what makes parallel transfers actually parallel: each
        worker gets its own socket and its own `rpc_call`, so concurrent
        calls never contend on the lock inside a single shared
        DcConnection. Mirrors ferogram's Rust `Client::open_worker_conn`.

        - Same DC as the home connection: reuses the cached home auth key.
          No DH, no authorization step.
        - A different DC: reuses a cached key for that DC if the session
          already has one, otherwise performs a fresh DH. Either way the
          resulting connection is bound to the account via
          auth.exportAuthorization / auth.importAuthorization unless this
          DC was already bound earlier in this run (export tokens are
          single-use, so that binding only ever happens once per DC per
          process).
        """
        api_id, api_hash = self._require_creds()
        target_dc = dc_id or self._dc_id
        session = self._session_backend()

        # DcConnection.connect() persists to the session backend on every
        # call. Serialize opens so concurrent worker startups can't
        # load+save the session file at the same time and clobber each
        # other's entries; this only costs one handshake's worth of
        # latency at transfer setup, not per-chunk.
        async with self._worker_conn_lock:
            conn = await DcConnection.connect(
                session, api_id, api_hash, target_dc,
                test_mode=self.test_mode, transport=self.transport,
                proxy_secret=self.proxy_secret, domain=self.domain,
                proxy=self.proxy, pfs=self.pfs,
                flood_sleep_threshold=self._flood_sleep_threshold,
            )

            if target_dc == self._dc_id or target_dc in self._auth_imported_dcs:
                await self._init_connection_on(conn)
                return conn

            export = await self._rpc({"_": "auth.exportAuthorization", "dc_id": target_dc})
            inner = _build_import_authorization(export["id"], export["bytes"])
            await self._init_connection_on(conn, inner=inner)
            self._auth_imported_dcs.add(target_dc)
            return conn

    @asynccontextmanager
    async def _worker_slot(self, dc_id: int | None = None):
        """Open a worker connection, holding one `max_tcp_connections`
        permit for as long as it's in use.

        Use this instead of calling `_open_worker_conn` directly whenever
        the connection is part of a parallel transfer's worker pool - it's
        what actually enforces the global cap across every upload/download
        running at once, not just within a single transfer.
        """
        async with self._transfer_semaphore:
            conn = await self._open_worker_conn(dc_id)
            yield conn

    async def _resolve_peer(self, peer: Any) -> dict:
        return await _resolve_peer_fn(self, peer)

    def _extract_sent_message(self, resp: dict, *, text: str = "",
                               peer_id: dict | None = None) -> Message:
        """Build a bound Message from a sendMessage/sendMedia RPC response.

        Telegram replies to these calls with either an Updates container
        (carrying the full message) or a slimmer updateShortSentMessage
        (id/date/media only, no echoed text/peer). Either way the caller
        gets back a real Message with .id, .reply(), etc. instead of a
        bare dict.
        """
        t = resp.get("_", "")
        if t in ("updates", "updatesCombined"):
            self._populate_cache(resp)
            for u in resp.get("updates") or []:
                if u.get("_") in ("updateNewMessage", "updateNewChannelMessage",
                                   "updateNewScheduledMessage"):
                    msg = Message.from_tl(u.get("message") or {})
                    msg._client = self
                    return msg
        if t == "updateShortSentMessage":
            msg = Message(
                id=resp.get("id", 0), text=text, sender_id=None,
                peer_id=peer_id or {}, date=resp.get("date", 0), edit_date=None,
                reply_to_msg_id=None, forward_from_id=None, media=resp.get("media"),
                entities=resp.get("entities") or [], views=None, via_bot_id=None,
                grouped_id=None, out=bool(resp.get("out", True)), mentioned=False,
                silent=False, pinned=False, _raw=resp,
            )
            msg._client = self
            return msg
        self._log.warning("_extract_sent_message: unrecognised response type %r, constructing minimal Message", t)
        msg = Message(
            id=resp.get("id", 0), text=text, sender_id=None, peer_id=peer_id or {},
            date=resp.get("date", 0), edit_date=None, reply_to_msg_id=None,
            forward_from_id=None, media=resp.get("media"), entities=resp.get("entities") or [],
            views=None, via_bot_id=None, grouped_id=None, out=True, mentioned=False,
            silent=False, pinned=False, _raw=resp,
        )
        msg._client = self
        return msg

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
            self._peer_cache.store_chat_entity(ch)

    async def _load_persisted_update_state(self) -> None:
        """If `catch_up=True`, restore `MessageBox` from whatever
        pts/qts/date/seq state was persisted last run, so `getDifference`
        resumes from the pre-shutdown position instead of jumping straight
        to the current server state and silently skipping whatever came in
        while disconnected. No-op when `catch_up` is off, or when nothing
        has been saved yet (first run, fresh session) - the existing
        `MessageBox()` in `__init__` is left as-is and gets seeded from a
        fresh `updates.getState` at the start of `_run_updates()`, same as
        before."""
        if not self.catch_up:
            return
        conn = self._require_conn()
        pts, qts, date, seq, channels = await conn.get_persisted_update_state()
        if pts <= 0:
            self._log.debug(
                "catch_up requested but no saved update state; starting fresh"
            )
            return
        self._message_box = MessageBox.load(pts, qts, date, seq, channels)
        self._log.debug(
            "update state restored: pts=%d, qts=%d, seq=%d, %d channels tracked",
            pts, qts, seq, len(channels),
        )

    async def _flush_update_state(self) -> None:
        """Push the current pts/qts/date/seq snapshot into the Rust
        binding's in-memory session record and persist it, so a future
        `catch_up=True` run has something real to load. Cheap enough to
        call unconditionally on every autosave tick and on shutdown -
        unlike the peer cache there's no dirty flag, since pts advances on
        essentially every update."""
        conn = self._conn
        if conn is None:
            return
        pts, qts, date, seq, channels = await self._message_box.session_state()
        if pts <= 0:
            return
        await conn.sync_persisted_update_state(pts, qts, date, seq, channels)
        await conn.save_session()

    async def _load_persisted_peer_cache(self) -> None:
        """Seed `self._peer_cache` from whatever the session file already
        has, right after connect() and before the first RPC. Without this,
        every peer has to be re-resolved from scratch each run even though
        the Rust binding already persisted them - see
        `DcConnection.get_persisted_peers()`."""
        conn = self._require_conn()
        peers, min_peers = await conn.get_persisted_peers()
        self._peer_cache.load_persisted(peers, min_peers)
        cache = self._peer_cache
        self._log.debug(
            "peer cache restored: %d users, %d channels, %d communities, "
            "%d chats, %d channels_min, %d min-peer contexts",
            len(cache._users),
            len(cache._channels),
            len(cache._communities),
            len(cache._chats),
            len(cache.channels_min),
            len(cache.min_contexts),
        )

    async def _flush_peer_cache(self) -> None:
        """Push the current peer cache into the Rust binding's in-memory
        snapshot and persist it. Safe to call even when nothing changed -
        callers should check `self._peer_cache.dirty` first to avoid
        needless disk writes on the autosave interval."""
        conn = self._conn
        if conn is None:
            return
        peers, min_peers = self._peer_cache.to_persisted()
        await conn.sync_persisted_peers(peers, min_peers)
        await conn.save_session()
        self._peer_cache.dirty = False

    async def _peer_cache_autosave_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._peer_cache_save_interval)
                if self._peer_cache.dirty:
                    try:
                        await self._flush_peer_cache()
                    except Exception as exc:
                        self._log.warning("peer cache autosave failed: %s", exc)
                try:
                    await self._flush_update_state()
                except Exception as exc:
                    self._log.warning("update state autosave failed: %s", exc)
        except asyncio.CancelledError:
            pass

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

        # session_string may have been overridden by this call (vs the
        # constructor), so recompute the tag before it appears in any log
        # line below.
        self._log.extra["client"] = _session_tag(self.session, self.session_string)

        self._log.info("connecting (session=%r)", repr(session))
        t0 = time.monotonic()
        self._conn = await DcConnection.connect(
            session, api_id, api_hash, self._dc_id_override,
            test_mode=self.test_mode, transport=self.transport,
            proxy_secret=self.proxy_secret, domain=self.domain,
            dc_addr=self.dc_addr, proxy=self.proxy, pfs=self.pfs,
            flood_sleep_threshold=self._flood_sleep_threshold,
            stream_updates=True,
        )
        connect_ms = int((time.monotonic() - t0) * 1000)
        self._dc_id = self._conn.dc_id
        self._log.extra["client"] = f"{_session_tag(self.session, self.session_string)} dc{self._dc_id}"
        self._log.info("connected to DC%d in %dms", self._dc_id, connect_ms)
        await self._load_persisted_update_state()
        self._conn.bind_message_box(self._message_box)
        await self._load_persisted_peer_cache()
        self._peer_cache_save_task = asyncio.create_task(self._peer_cache_autosave_loop())
        if self._future_auth_token is not None:
            # Don't clobber a real token the session already persisted
            # from a previous sign_out() with a stale constructor value.
            existing = await self._conn.get_future_auth_token()
            if existing is None:
                await self._conn.set_future_auth_token(self._future_auth_token)
        await self._init_connection()
        if not await self.is_authorized():
            if self.bot_token:
                await self.bot_sign_in(self.bot_token)
                self._log.info("signed in as bot")
            else:
                await self._interactive_login()
            await self._conn.set_home_dc(self._conn.dc_id)
            await self._conn.save_session()
        else:
            self._log.info("reusing existing session")
        return self

    async def stop(self) -> None:
        """Disconnect and persist final state. Does NOT log the account out
        of Telegram - the auth key and session stay valid for next start().
        Call `sign_out()` yourself first if you actually want to deauthorize."""
        if self._conn:
            if self._peer_cache_save_task is not None:
                self._peer_cache_save_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._peer_cache_save_task
                self._peer_cache_save_task = None
            with suppress(Exception):
                # Final unconditional flush so nothing learned since the
                # last autosave tick is lost - mirrors the Rust core's
                # save-on-shutdown in its own snapshot saver task.
                await self._flush_peer_cache()
            with suppress(Exception):
                await self._flush_update_state()
            with suppress(Exception):
                await self._conn.save_session()
            self._conn = None
            self._log.info("disconnected")

    async def run_until_disconnected(self) -> None:
        await self.start()
        self._frame_pump_task = asyncio.create_task(self._run_frame_pump())
        try:
            await self._run_updates()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            if self._frame_pump_task is not None:
                self._frame_pump_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._frame_pump_task
            if self._peer_cache_save_task is not None:
                self._peer_cache_save_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._peer_cache_save_task
                self._peer_cache_save_task = None
            with suppress(Exception):
                await self._flush_peer_cache()
            with suppress(Exception):
                await self._flush_update_state()

    def run(self) -> None:
        try:
            asyncio.run(self.run_until_disconnected())
        except KeyboardInterrupt:
            pass

    async def __aenter__(self) -> "Client":
        return await self.start()

    async def __aexit__(self, *_: Any) -> None:
        await self.stop()

    async def signal_network_restored(self) -> None:
        """Reconnect after a network outage.

        Drops the current connection (if any) and re-establishes it.
        The Rust layer has no explicit reconnect signal; dropping and
        reconnecting is equivalent and safe since sessions are persisted.
        Does nothing if the client was never started.
        """
        if self._conn is None:
            return
        self._conn = None
        await self.start()

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
