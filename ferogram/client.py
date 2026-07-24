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
import hashlib
import inspect
import logging
import os
import random
import struct
from collections import deque
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Callable

from ._ferogram import DcConnection, srp_calculate
from ._ferogram import (
    FileSession, MemorySession, StringSession,
    SqliteSession, LibSqlSession, CustomSession,
)
from .raw import tl as _tl
from .rich import _RichMixin
from .raw.generated._tl_schema import _SCHEMA, _SCHEMA_BY_CID, LAYER
from .raw.proxy import RawProxy, PeerCache, resolve_peer as _resolve_peer_fn
from .types import (
    ChatAction, PrivacyKey, PrivacyRule,
    InlineMessageId, InlineArticle, InlinePhoto, InlineDocument,
    Message, Chat, User, _inline_result_to_tuple,
)
from .updates import wrap_update
from .keyboards import InlineKeyboard, ReplyKeyboard, RemoveKeyboard, ForceReply

__all__ = ["Client", "StopPropagation", "ContinuePropagation", "TransferHandle", "TransferLimits", "TransferCancelled", "available_qualities"]

_log = logging.getLogger("ferogram")


class TransferHandle:
    """Pause / resume / cancel control for upload and download operations.

    Mirrors ferogram's Rust TransferHandle. Create one, optionally pass it to
    upload_file / download_media / upload_with_progress / download_with_progress,
    and call pause() / resume() / cancel() from any coroutine or thread.

    Progress is read via .progress() which returns a dict with keys:
        done       - bytes transferred so far
        total      - total bytes (0 if unknown)
        elapsed_ms - milliseconds elapsed since transfer started
        percent    - completion 0.0-100.0
        speed_bps  - bytes per second
        eta_secs   - estimated seconds remaining
        speed_human - e.g. "1.4 MB/s"
        bytes_human - e.g. "12.3 MB / 50.0 MB"

    Example::

        handle = TransferHandle()
        asyncio.get_event_loop().call_later(10, handle.cancel)
        await client.upload_with_progress("big.mp4", on_progress=lambda d, t: print(f"{d}/{t}"), handle=handle)
    """

    def __init__(self) -> None:
        import time
        self._paused    = False
        self._cancelled = False
        self._done      = 0
        self._total     = 0
        self._start_ms  = int(time.time() * 1000)

    def pause(self) -> None:
        """Pause after the current chunk finishes."""
        self._paused = True

    def resume(self) -> None:
        """Resume a paused transfer."""
        self._paused = False

    def cancel(self) -> None:
        """Cancel the transfer. The worker raises TransferCancelled after the current chunk."""
        self._cancelled = True

    def is_paused(self) -> bool:
        return self._paused

    def is_cancelled(self) -> bool:
        return self._cancelled

    def progress(self) -> dict:
        import time
        now_ms   = int(time.time() * 1000)
        elapsed  = max(now_ms - self._start_ms, 1)
        done     = self._done
        total    = self._total
        elapsed_s = elapsed / 1000.0
        speed    = int(done / elapsed_s) if elapsed_s > 0 else 0
        pct      = (done / total * 100.0) if total > 0 else 0.0
        eta      = int((total - done) / speed) if speed > 0 and done < total else 0

        if speed >= 1024 * 1024:
            speed_h = f"{speed / (1024 * 1024):.1f} MB/s"
        elif speed >= 1024:
            speed_h = f"{speed / 1024:.1f} KB/s"
        else:
            speed_h = f"{speed} B/s"

        def _fmt(b: int) -> str:
            if b >= 1024 ** 3:
                return f"{b / 1024**3:.1f} GB"
            if b >= 1024 ** 2:
                return f"{b / 1024**2:.1f} MB"
            if b >= 1024:
                return f"{b / 1024:.1f} KB"
            return f"{b} B"

        return {
            "done":        done,
            "total":       total,
            "elapsed_ms":  elapsed,
            "percent":     min(pct, 100.0),
            "speed_bps":   speed,
            "eta_secs":    eta,
            "speed_human": speed_h,
            "bytes_human": f"{_fmt(done)} / {_fmt(total)}",
        }

    # Internal helpers used by Client methods
    def _set_total(self, total: int) -> None:
        self._total = total

    def _add_bytes(self, n: int) -> None:
        self._done += n

    def _reset_start(self) -> None:
        import time
        self._start_ms = int(time.time() * 1000)
        self._done = 0

    async def _poll_pause_cancel(self) -> None:
        """Yield to the event loop while paused; raise if cancelled."""
        while True:
            if self._cancelled:
                raise TransferCancelled("transfer cancelled by caller")
            if not self._paused:
                return
            await asyncio.sleep(0.1)


class TransferCancelled(Exception):
    """Raised when a TransferHandle is cancelled during upload or download."""


class TransferLimits:
    """Concurrency ceilings for file transfers. Mirrors ferogram's Rust
    `TransferLimits` (same highway/trucks model, same field names).

    - `download_tcp_connections` / `upload_tcp_connections` (**Y**): how many
      parallel worker connections a single transfer may open for itself.
      Small files always use 1 regardless of this value; larger files scale
      up towards this ceiling. Default: 4.
    - `max_tcp_connections`: total worker connections allowed across the
      whole client at once, shared by every upload and download running
      concurrently. Lower this on memory- or socket-constrained devices
      (e.g. Termux on older Android hardware). Default: 12.
    - `download_pipeline_depth` / `upload_pipeline_depth` (**X**): how many
      chunk requests a single connection keeps in flight at once instead of
      waiting for each response before sending the next. Enforced for
      dedicated worker connections (via `DcConnection.into_pipelined_sender()`);
      the shared home-connection fallback path (used when no extra worker
      connections could be opened) still goes one request at a time, since
      that socket can't be handed off to a pipelined sender.
      Default: 4.
    - `bypass_tcp_allotments`: skip the size-based lookup tables for **Y**
      entirely and always use `download_tcp_connections` /
      `upload_tcp_connections` directly, regardless of file size. This is an
      override, not just a tuning knob - turning it on means small files
      open as many connections as large ones would. Default: False.

    Example::

        Client(
            ...,
            transfer_limits=TransferLimits(
                download_tcp_connections=1,
                upload_tcp_connections=1,
                max_tcp_connections=12,
                download_pipeline_depth=16,
                upload_pipeline_depth=16,
                bypass_tcp_allotments=False,
            ),
        )
    """

    __slots__ = (
        "download_tcp_connections",
        "upload_tcp_connections",
        "max_tcp_connections",
        "download_pipeline_depth",
        "upload_pipeline_depth",
        "bypass_tcp_allotments",
    )

    def __init__(
        self,
        download_tcp_connections: int = 4,
        upload_tcp_connections: int = 4,
        max_tcp_connections: int = 12,
        download_pipeline_depth: int = 4,
        upload_pipeline_depth: int = 4,
        bypass_tcp_allotments: bool = False,
    ) -> None:
        self.download_tcp_connections = max(1, download_tcp_connections)
        self.upload_tcp_connections   = max(1, upload_tcp_connections)
        self.max_tcp_connections      = max(1, max_tcp_connections)
        self.download_pipeline_depth  = max(1, download_pipeline_depth)
        self.upload_pipeline_depth    = max(1, upload_pipeline_depth)
        self.bypass_tcp_allotments    = bypass_tcp_allotments

    def __repr__(self) -> str:
        return (
            "TransferLimits("
            f"download_tcp_connections={self.download_tcp_connections}, "
            f"upload_tcp_connections={self.upload_tcp_connections}, "
            f"max_tcp_connections={self.max_tcp_connections}, "
            f"download_pipeline_depth={self.download_pipeline_depth}, "
            f"upload_pipeline_depth={self.upload_pipeline_depth}, "
            f"bypass_tcp_allotments={self.bypass_tcp_allotments})"
        )

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


def _quality_candidates(media: dict) -> "list[dict]":
    """Every Document on `media` that could be a quality variant: the
    primary document (if any) followed by every entry in `alt_documents`
    (if any). Order is: primary first, then alternates in the order
    Telegram sent them - not sorted by resolution. Mirrors ferogram's Rust
    `quality_candidates`."""
    if not isinstance(media, dict) or media.get("_") != "messageMediaDocument":
        return []
    docs: "list[dict]" = []
    doc = media.get("document")
    if isinstance(doc, dict):
        docs.append(doc)
    for alt in media.get("alt_documents") or []:
        if isinstance(alt, dict):
            docs.append(alt)
    return docs


def _video_resolution(doc: dict) -> int:
    """Resolution (width * height) of a document, from its
    documentAttributeVideo if it has one. 0 for documents with no video
    attribute (audio, plain files) so they sort below anything with a
    real resolution."""
    for attr in doc.get("attributes", []) or []:
        if isinstance(attr, dict) and attr.get("_") == "documentAttributeVideo":
            return attr.get("w", 0) * attr.get("h", 0)
    return 0


def available_qualities(media: dict) -> "list[dict]":
    """List every quality variant available for `media` (a raw
    messageMediaDocument dict), sorted ascending by resolution (primary
    document included if it has a video attribute). Empty for media with
    no video attributes at all - photos, audio, and documents Telegram
    didn't transcode into multiple qualities. Mirrors ferogram's Rust
    `available_qualities`.

    Each entry is `{"width": int, "height": int, "size": int}`. Use this
    to build your own quality picker, or just pass `"highest"`/`"lowest"`
    straight to `download_media` if you don't need the full list.
    """
    out: "list[dict]" = []
    for doc in _quality_candidates(media):
        for attr in doc.get("attributes", []) or []:
            if isinstance(attr, dict) and attr.get("_") == "documentAttributeVideo":
                out.append({
                    "width": attr.get("w", 0),
                    "height": attr.get("h", 0),
                    "size": doc.get("size", 0),
                })
                break
    out.sort(key=lambda q: q["width"] * q["height"])
    return out


def _resolve_quality_document(media: dict, quality: str) -> "dict | None":
    """Resolve `quality` ("original" | "highest" | "lowest") against
    `media`, returning the chosen document dict. Falls back to the
    primary document whenever the requested quality doesn't actually
    exist for this media (no alternates present, the media isn't a
    document at all, or "original" was requested outright). Mirrors
    ferogram's Rust `resolve_quality_document`."""
    primary = None
    if isinstance(media, dict) and media.get("_") == "messageMediaDocument":
        doc = media.get("document")
        if isinstance(doc, dict):
            primary = doc

    chosen = None
    if quality == "highest":
        candidates = _quality_candidates(media)
        if candidates:
            chosen = max(candidates, key=_video_resolution)
    elif quality == "lowest":
        candidates = _quality_candidates(media)
        if candidates:
            chosen = min(candidates, key=_video_resolution)

    return chosen or primary


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


class Client(_RichMixin):
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
        update_queue_capacity: int | None = None,
        update_overflow: str | None = "drop_oldest",
        parse_mode: str | None = None,
        workers: int = 4,
        flood_sleep_threshold: int = 60,
        transfer_limits: "TransferLimits | None" = None,
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
        self._update_queue = asyncio.Queue(
            maxsize=self.update_queue_capacity or (self._workers * 4)
        )
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
                    if event_type in ("message", "edited_message"):
                        entity = wrapped.message
                    else:
                        entity = wrapped
                    if hasattr(entity, "_client"):
                        entity._client = self
                    await self._enqueue_update((event_type, entity))

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
        self._conn = await DcConnection.connect(
            session, api_id, api_hash, dc_id,
            proxy=self.proxy, pfs=self.pfs,
            flood_sleep_threshold=self._flood_sleep_threshold,
        )
        self._dc_id = dc_id
        await self._init_connection()
        _log.info("migrated to DC%d", dc_id)

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
            _log.debug("failed to persist DC address from getConfig: %s", exc)

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
        _log.warning("_extract_sent_message: unrecognised response type %r, constructing minimal Message", t)
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
        self._conn = await DcConnection.connect(
            session, api_id, api_hash,
            dc_addr=self.dc_addr, proxy=self.proxy, pfs=self.pfs,
            flood_sleep_threshold=self._flood_sleep_threshold,
        )
        self._dc_id = self._conn.dc_id
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

        sent = await self.request_login_code(identifier)
        if sent.get("_") == "auth.sentCodeSuccess":
            # Fast re-auth via a stored future_auth_token; no code needed.
            _log.info("signed in as user (fast re-auth, no code needed)")
            print("\nPlease ensure your usage complies with Telegram's API Terms of Service.")
            return
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
        if self._conn:
            self._conn = None


    async def is_authorized(self) -> bool:
        try:
            result = await self._rpc({"_": "users.getUsers", "id": [{"_": "inputUserSelf"}]})
            users = result if isinstance(result, list) else result.get("users", [])
            return bool(users)
        except Exception:
            return False

    async def request_login_code(self, phone: str) -> dict:
        """Ask Telegram to send a login code.

        If a previous `sign_out()` on this session captured a
        `future_auth_token`, it's replayed automatically here so Telegram
        can skip code entry and authorize the session immediately
        (`auth.sentCodeSuccess`). In that case the returned dict has
        `"_": "auth.sentCodeSuccess"` and no code needs to be entered -
        check for that before prompting the user.
        """
        api_id, api_hash = self._require_creds()
        code_settings: dict = {"_": "codeSettings"}
        stored_token = await self._require_conn().get_future_auth_token()
        if stored_token is not None:
            code_settings["logout_tokens"] = [stored_token]

        result = await self._rpc({
            "_": "auth.sendCode",
            "phone_number": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "settings": code_settings,
        })
        if result.get("_") == "auth.sentCodeSuccess":
            # Telegram authorized the session outright; the token was
            # single-use, so drop it rather than risk replaying a stale one.
            await self._require_conn().set_future_auth_token(None)
            authorization = result.get("authorization", {})
            user = authorization.get("user") if isinstance(authorization, dict) else None
            if isinstance(user, dict):
                self._populate_cache({"users": [user]})
            return result
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
            result = await self._rpc({"_": "auth.logOut"})
            if isinstance(result, dict) and result.get("_") == "auth.loggedOut":
                token = result.get("future_auth_token")
                if isinstance(token, (bytes, bytearray)):
                    await self._require_conn().set_future_auth_token(bytes(token))
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

    async def get_user(self, user_id: int) -> "User | None":
        from .types import User as _User
        peers = await self.get_users_by_id([user_id])
        raw = peers[0] if peers else None
        if not raw:
            return None
        return _User.from_tl(raw)

    async def get_chat(self, peer: Any) -> "Chat | None":
        from .types import Chat as _Chat
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if t == "inputPeerChat":
            result = await self._rpc({
                "_": "messages.getChats",
                "id": [input_peer["chat_id"]],
            })
            chats = result.get("chats") or [] if isinstance(result, dict) else []
            return _Chat.from_tl(chats[0]) if chats else None
        if t == "inputPeerChannel":
            result = await self._rpc({
                "_": "channels.getChannels",
                "id": [{
                    "_": "inputChannel",
                    "channel_id": input_peer["channel_id"],
                    "access_hash": input_peer.get("access_hash", 0),
                }],
            })
            chats = result.get("chats") or [] if isinstance(result, dict) else []
            return _Chat.from_tl(chats[0]) if chats else None
        if t == "inputPeerUser":
            users = await self.get_users_by_id([input_peer["user_id"]])
            raw = users[0] if users else None
            if not raw:
                return None
            return _Chat(
                id=raw.get("id", 0),
                title=((raw.get("first_name") or "") + " " + (raw.get("last_name") or "")).strip(),
                username=raw.get("username"),
                is_channel=False, is_megagroup=False, is_gigagroup=False,
                is_broadcast=False, is_community=False, members_count=None,
                access_hash=raw.get("access_hash", 0), _raw=raw,
            )
        return None

    async def get_contacts(self) -> list[dict]:
        result = await self._rpc({"_": "contacts.getContacts", "hash": 0})
        return result.get("users", []) if isinstance(result, dict) else []


    async def send_message(self, peer: Any, text: str, *,
                           parse_mode: str | None = None,
                           reply_to: int | None = None,
                           reply_markup=None,
                           no_webpage: bool = True,
                           silent: bool = False,
                           schedule_date: int | None = None,
                           send_as: Any = None,
                           noforwards: bool = False,
                           background: bool = False,
                           clear_draft: bool = False,
                           effect: int | None = None,
                           invert_media: bool = False) -> Message:
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
            "entities": entities,
        }
        if no_webpage:
            req["no_webpage"] = True
        if silent:
            req["silent"] = True
        if noforwards:
            req["noforwards"] = True
        if background:
            req["background"] = True
        if clear_draft:
            req["clear_draft"] = True
        if invert_media:
            req["invert_media"] = True
        if schedule_date is not None:
            req["schedule_date"] = schedule_date
        if effect is not None:
            req["effect"] = effect
        if send_as is not None:
            req["send_as"] = await self._resolve_peer(send_as)
        if reply_to is not None:
            req["reply_to"] = {"_": "inputReplyToMessage", "reply_to_msg_id": reply_to}
        if reply_markup is not None:
            req["reply_markup"] = _markup_to_dict(reply_markup)
        resp = await self._rpc(req)
        return self._extract_sent_message(resp, text=plain, peer_id=input_peer)

    async def send_to_self(self, text: str) -> None:
        await self.send_message("me", text)

    async def edit_message(self, peer: Any, message_id: int, new_text: str, *,
                           parse_mode: str | None = None,
                           reply_markup=None,
                           no_webpage: bool = True) -> None:
        pm = self._resolve_pm(parse_mode)
        if pm in ("markdown", "md"):
            plain, entities = _tl.parse_markdown(new_text)
        elif pm == "html":
            plain, entities = _tl.parse_html(new_text)
        else:
            plain, entities = new_text, []
        input_peer = await self._resolve_peer(peer)
        req: dict = {
            "_": "messages.editMessage",
            "peer": input_peer,
            "id": message_id,
            "message": plain,
        }
        if no_webpage:
            req["no_webpage"] = True
        if entities:
            req["entities"] = entities
        if reply_markup is not None:
            req["reply_markup"] = _markup_to_dict(reply_markup)
        await self._rpc(req)

    async def delete_message(self, message_id: int, revoke: bool = True) -> None:
        await self.delete_messages([message_id], revoke)

    async def delete_messages(self, message_ids: list[int], revoke: bool = True) -> None:
        await self._rpc({
            "_": "messages.deleteMessages",
            "id": message_ids,
            "revoke": revoke,
        })

    async def delete_messages_in(self, peer: Any, message_ids: list[int], revoke: bool = True) -> None:
        """Delete messages in a specific chat, using channels.deleteMessages for channels/supergroups."""
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if t == "inputPeerChannel":
            await self._rpc({
                "_": "channels.deleteMessages",
                "channel": {
                    "_": "inputChannel",
                    "channel_id": input_peer["channel_id"],
                    "access_hash": input_peer.get("access_hash", 0),
                },
                "id": message_ids,
            })
        else:
            await self._rpc({
                "_": "messages.deleteMessages",
                "id": message_ids,
                "revoke": revoke,
            })

    async def forward_messages(self, destination: str, source: str, message_ids: list[int], *,
                               silent: bool = False,
                               drop_author: bool = False,
                               drop_media_captions: bool = False,
                               noforwards: bool = False,
                               background: bool = False,
                               schedule_date: int | None = None,
                               send_as: Any = None) -> None:
        from_peer = await self._resolve_peer(source)
        to_peer   = await self._resolve_peer(destination)
        req: dict = {
            "_": "messages.forwardMessages",
            "from_peer": from_peer,
            "to_peer": to_peer,
            "id": message_ids,
            "random_id": [random.randint(-(2**63), 2**63 - 1) for _ in message_ids],
        }
        if silent:
            req["silent"] = True
        if drop_author:
            req["drop_author"] = True
        if drop_media_captions:
            req["drop_media_captions"] = True
        if noforwards:
            req["noforwards"] = True
        if background:
            req["background"] = True
        if schedule_date is not None:
            req["schedule_date"] = schedule_date
        if send_as is not None:
            req["send_as"] = await self._resolve_peer(send_as)
        await self._rpc(req)

    async def pin_message(self, peer: Any, message_id: int, *, notify: bool = False) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.updatePinnedMessage",
            "peer": input_peer,
            "id": message_id,
            "silent": not notify,
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

    async def get_poll_results(self, peer: str, msg_id: int, poll_hash: int = 0) -> dict:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getPollResults", "peer": input_peer, "msg_id": msg_id})
        return result if isinstance(result, dict) else {}

    async def poll_results(self, peer: str, msg_id: int) -> dict:
        return await self.get_poll_results(peer, msg_id)

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

    async def delete_reaction(self, peer: str, msg_id: int) -> None:
        """Remove your own reaction from a message.

        MTProto has no method to remove another user's reaction.
        Sends messages.sendReaction with an empty reaction list, which
        clears the calling user's reaction on the given message.
        """
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.sendReaction",
            "peer": input_peer,
            "msg_id": msg_id,
            "reaction": [],
        })


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
        if not isinstance(result, dict):
            return []
        self._populate_cache(result)
        dialogs = result.get("dialogs", []) or []
        chat_map = {c.get("id"): c for c in (result.get("chats") or []) if isinstance(c, dict) and c.get("id") is not None}
        for d in dialogs:
            if not isinstance(d, dict):
                continue
            # dialogCommunity has no `peer` field - it's addressed by
            # `community_id` instead, since there is no Peer::Community on
            # the wire. Attach the resolved chat under "chat" either way so
            # callers don't need to branch on the dialog's `_` type.
            if d.get("_") == "dialogCommunity":
                d["chat"] = chat_map.get(d.get("community_id"))
            else:
                peer = d.get("peer") or {}
                cid = peer.get("user_id") or peer.get("chat_id") or peer.get("channel_id")
                d["chat"] = chat_map.get(cid)
        return dialogs

    async def get_pinned_dialogs(self, folder_id: int = 0) -> list[int]:
        result = await self._rpc({"_": "messages.getPinnedDialogs", "folder_id": folder_id})
        dialogs = result.get("dialogs", []) if isinstance(result, dict) else []
        out = []
        for d in dialogs:
            if not isinstance(d, dict):
                continue
            if d.get("_") == "dialogCommunity":
                cid = d.get("community_id")
                if cid:
                    out.append(-(1_000_000_000 + cid))
                continue
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
        await self.delete_chat_history(peer, max_id=0, revoke=False)

    async def delete_chat_history(self, peer: str, max_id: int = 0, revoke: bool = False) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.deleteHistory", "peer": input_peer, "max_id": max_id, "revoke": revoke})


    def _resolve_chat_invite_join_result(self, result: Any) -> dict | None:
        """Normalize a `messages.ChatInviteJoinResult` into a resolved InputPeer.

        `messages.importChatInvite` and `channels.joinChannel` no longer
        return a bare `Updates` object (layer 228) - they return this union:

          - `chatInviteJoinResultOk` wraps `updates: Updates`. The joined
            chat/channel/community is pulled out of the embedded
            users/chats and cached.
          - `chatInviteJoinResultWebView` carries only `bot_id`/`query_id`/
            `users`, with no Updates at all. Telegram hasn't actually
            completed the join here - the client needs to drive an
            interactive bot webview flow to finish it. That flow isn't
            implemented, so this returns None instead of pretending the
            join succeeded.
        """
        if not isinstance(result, dict):
            return None
        t = result.get("_", "")
        if t == "messages.chatInviteJoinResultWebView":
            return None
        if t != "messages.chatInviteJoinResultOk":
            return None
        updates = result.get("updates") or {}
        if not isinstance(updates, dict):
            return None
        self._populate_cache(updates)
        for ch in updates.get("chats") or []:
            if not isinstance(ch, dict) or ch.get("min"):
                continue
            ctype = ch.get("_", "")
            if ctype in ("channel", "community"):
                return {"_": "inputPeerChannel", "channel_id": ch.get("id"), "access_hash": ch.get("access_hash", 0)}
            if ctype == "chat":
                return {"_": "inputPeerChat", "chat_id": ch.get("id")}
        return None

    async def join_chat(self, peer: str) -> dict | None:
        """Join a chat, channel, or community by username/link.

        Returns the joined chat's InputPeer on success, or None if Telegram
        responded with a WebView join result - meaning the join requires an
        interactive bot flow that hasn't completed yet (see
        `_resolve_chat_invite_join_result`).
        """
        if peer.startswith("+") or "/+" in peer:
            link = peer.split("/+")[-1] if "/+" in peer else peer[1:]
            result = await self._rpc({"_": "messages.importChatInvite", "hash": link})
            return self._resolve_chat_invite_join_result(result)
        else:
            channel = await self._resolve_peer(peer)
            result = await self._rpc({"_": "channels.joinChannel", "channel": channel})
            if isinstance(result, dict) and result.get("_") == "messages.chatInviteJoinResultWebView":
                return None
            if isinstance(result, dict) and result.get("_") == "messages.chatInviteJoinResultOk":
                self._populate_cache(result.get("updates") or {})
            return channel

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
        # Kick = temporary ban then immediate unban so the user can rejoin.
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
        await self._rpc({
            "_": "channels.editBanned",
            "channel": channel,
            "participant": user_peer,
            "banned_rights": {"_": "chatBannedRights", "until_date": 0},
        })

    async def ban_participant(self, peer: str, user: str) -> None:
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

    _DEFAULT_ADMIN_RIGHTS = (
        "change_info", "post_messages", "edit_messages", "delete_messages",
        "ban_users", "invite_users", "pin_messages", "manage_call", "manage_topics",
    )

    async def promote_participant(self, peer: str, user: str, rights: list[str] | None = None, *, title: str = "") -> None:
        """Promote a user to admin.

        `rights` is now exact, not additive: pass e.g. `["delete_messages"]`
        for a limited admin with only that permission. Omit it for the
        previous default (full admin) behavior. Valid right names: change_info,
        post_messages, edit_messages, delete_messages, ban_users, invite_users,
        pin_messages, add_admins, anonymous, manage_call, other, manage_topics,
        post_stories, edit_stories, delete_stories, manage_direct_messages,
        manage_ranks, manage_linked_peers.
        """
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        chosen = rights if rights is not None else self._DEFAULT_ADMIN_RIGHTS
        admin_rights: dict = {"_": "chatAdminRights", **{r: True for r in chosen}}
        await self._rpc({
            "_": "channels.editAdmin",
            "channel": channel,
            "user_id": user_peer,
            "admin_rights": admin_rights,
            "rank": title,
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


    async def send_photo(self, peer: Any, path: str, caption: str = "", *,
                         parse_mode: str | None = None,
                         reply_to: int | None = None) -> Message:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        pm = self._resolve_pm(parse_mode)
        if pm in ("markdown", "md"):
            plain_cap, cap_entities = _tl.parse_markdown(caption)
        elif pm == "html":
            plain_cap, cap_entities = _tl.parse_html(caption)
        else:
            plain_cap, cap_entities = caption, []
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        req: dict = {
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": {"_": "inputMediaUploadedPhoto", "file": file_input},
            "message": plain_cap,
            "random_id": random.randint(-(2**63), 2**63 - 1),
        }
        if cap_entities:
            req["entities"] = cap_entities
        if reply_to is not None:
            req["reply_to"] = {"_": "inputReplyToMessage", "reply_to_msg_id": reply_to}
        resp = await self._rpc(req)
        return self._extract_sent_message(resp, text=plain_cap, peer_id=input_peer)

    async def send_file(self, peer: str, path: str, caption: str = "", mime_type: str | None = None, *,
                        parse_mode: str | None = None) -> dict:
        return await self.send_document(peer, path, caption, mime_type, parse_mode=parse_mode)

    async def send_document(self, peer: Any, path: str, caption: str = "", mime_type: str | None = None, *,
                             parse_mode: str | None = None,
                             reply_to: int | None = None) -> Message:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        pm = self._resolve_pm(parse_mode)
        if pm in ("markdown", "md"):
            plain_cap, cap_entities = _tl.parse_markdown(caption)
        elif pm == "html":
            plain_cap, cap_entities = _tl.parse_html(caption)
        else:
            plain_cap, cap_entities = caption, []
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        if mime_type is None:
            mime_type = "application/octet-stream"
        req: dict = {
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": {
                "_": "inputMediaUploadedDocument",
                "file": file_input,
                "mime_type": mime_type,
                "attributes": [{"_": "documentAttributeFilename", "file_name": os.path.basename(path)}],
            },
            "message": plain_cap,
            "random_id": random.randint(-(2**63), 2**63 - 1),
        }
        if cap_entities:
            req["entities"] = cap_entities
        if reply_to is not None:
            req["reply_to"] = {"_": "inputReplyToMessage", "reply_to_msg_id": reply_to}
        resp = await self._rpc(req)
        return self._extract_sent_message(resp, text=plain_cap, peer_id=input_peer)

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

    # Transfer helpers (mirrors ferogram Rust: part sizes, workers, progress)

    @staticmethod
    def _upload_part_size(file_size: int) -> tuple[int, int]:
        """Choose part size and total parts matching ferogram's
        upload_part_size() (media.rs). Three-tier table:

        | File size    | Part size |
        |--------------|-----------|
        | < 1 MB       | 128 KB    |
        | 1 MB - 50 MB | 256 KB    |
        | >= 50 MB     | 512 KB    |
        """
        if file_size < 1024 * 1024:
            ps = 128 * 1024
        elif file_size < 50 * 1024 * 1024:
            ps = 256 * 1024
        else:
            ps = 512 * 1024
        total_parts = (file_size + ps - 1) // ps
        if total_parts > 4000:
            ps = (file_size + 3999) // 4000
            ps = ((ps + 511) // 512) * 512
            total_parts = (file_size + ps - 1) // ps
        return ps, total_parts

    def _upload_worker_count(self, file_size: int) -> int:
        """Mirrors ferogram upload_worker_count(), capped by
        `TransferLimits.upload_tcp_connections`. With
        `bypass_tcp_allotments` set, skips the size table entirely and
        always returns the configured ceiling."""
        limits = self._transfer_limits
        if limits.bypass_tcp_allotments:
            return limits.upload_tcp_connections
        if file_size < 10 * 1024 * 1024:
            table = 1
        elif file_size < 100 * 1024 * 1024:
            table = 2
        elif file_size < 500 * 1024 * 1024:
            table = 3
        else:
            table = 4
        return max(1, min(table, limits.upload_tcp_connections))

    @staticmethod
    def _download_chunk_size(file_size: int) -> int:
        """Mirrors ferogram download_chunk_size()."""
        if file_size < 50 * 1024 * 1024:
            return 256 * 1024
        if file_size < 500 * 1024 * 1024:
            return 512 * 1024
        return 1024 * 1024

    def _download_worker_count(self, file_size: int) -> int:
        """Mirrors ferogram download_worker_count(), capped by
        `TransferLimits.download_tcp_connections`. With
        `bypass_tcp_allotments` set, skips the size table entirely and
        always returns the configured ceiling."""
        limits = self._transfer_limits
        if limits.bypass_tcp_allotments:
            return limits.download_tcp_connections
        if file_size < 10 * 1024 * 1024:
            table = 1
        elif file_size < 50 * 1024 * 1024:
            table = 2
        elif file_size < 300 * 1024 * 1024:
            table = 3
        else:
            table = 4
        return max(1, min(table, limits.download_tcp_connections))

    @staticmethod
    def _detect_mime(path: str) -> str:
        """Detect MIME from magic bytes (first 64 bytes) then fall back to extension."""
        import mimetypes
        header = b""
        try:
            with open(path, "rb") as fh:
                header = fh.read(64)
        except OSError:
            pass
        # Magic byte detection for common types
        sigs: list[tuple[bytes, str]] = [
            (b"\x89PNG",           "image/png"),
            (b"\xff\xd8\xff",      "image/jpeg"),
            (b"GIF8",              "image/gif"),
            (b"RIFF",              "video/webm"),    # may also be WAV; refined below
            (b"\x1aE\xdf\xa3",    "video/webm"),
            (b"ftyp",              "video/mp4"),     # at offset 4
            (b"\x00\x00\x00\x18ftyp", "video/mp4"),
            (b"\x00\x00\x00\x1cftyp", "video/mp4"),
            (b"OggS",              "video/ogg"),
            (b"ID3",               "audio/mpeg"),
            (b"\xff\xfb",         "audio/mpeg"),
            (b"\xff\xf3",         "audio/mpeg"),
            (b"OggS",              "audio/ogg"),
            (b"fLaC",             "audio/flac"),
            (b"WAVE",              "audio/wav"),     # RIFF....WAVE
            (b"%PDF",              "application/pdf"),
            (b"PK\x03\x04",       "application/zip"),
            (b"\x1f\x8b",         "application/gzip"),
            (b"BZh",               "application/x-bzip2"),
            (b"\xfd7zXZ",         "application/x-xz"),
            (b"7z\xbc\xaf'\x1c", "application/x-7z-compressed"),
            (b"Rar!",              "application/x-rar-compressed"),
            (b"\x89PNG",          "image/png"),
            (b"WEBP",              "image/webp"),    # RIFF....WEBP at offset 8
        ]
        for sig, mime in sigs:
            if header.startswith(sig):
                # Distinguish RIFF WAV vs WebM/WebP
                if sig == b"RIFF" and len(header) >= 12:
                    sub = header[8:12]
                    if sub == b"WEBP":
                        return "image/webp"
                    if sub == b"WAVE":
                        return "audio/wav"
                return mime
            if sig == b"ftyp" and len(header) >= 8 and header[4:8] == b"ftyp":
                return "video/mp4"
        # RIFF with unknown sub-type - check extension
        if header[8:12] == b"WAVE":
            return "audio/wav"
        # Extension fallback
        guessed, _ = mimetypes.guess_type(path)
        return guessed or "application/octet-stream"

    async def upload_file(self, path: str, *, handle: "TransferHandle | None" = None) -> dict:
        """Upload a file using independent parallel worker connections.

        Each worker opens its own authorized DcConnection (see
        `_open_worker_conn`) so concurrent parts genuinely pipeline on
        separate sockets instead of all contending for one connection's
        internal lock the way a single shared connection would. Part sizes
        and worker counts match ferogram's Rust core. Supports pause,
        resume, and cancel via a TransferHandle. Small files (<10 MB) use a
        single worker; large files use up to 4 concurrent workers.

        Note: unlike ferogram's Rust `upload_file_concurrent`, a FILE_MIGRATE
        mid-upload is not handled here -- it would require redirecting every
        worker to the new DC in lockstep, which adds real complexity for an
        edge case that's rare on `upload.saveFilePart`/`saveBigFilePart`. If
        you hit it in practice, open an issue and we can add it.

        Returns an inputFile or inputFileBig dict ready to pass to sendMedia.
        """
        BIG_THRESHOLD = 10 * 1024 * 1024

        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")

        file_name = os.path.basename(path)
        file_size = os.path.getsize(path)
        is_big    = file_size >= BIG_THRESHOLD
        part_size, total_parts = self._upload_part_size(file_size)
        n_workers  = max(1, min(self._upload_worker_count(file_size), total_parts))
        file_id    = random.randint(-(2**63), 2**63 - 1)
        md5        = hashlib.md5() if not is_big else None

        if handle is not None:
            handle._set_total(file_size)
            handle._reset_start()

        # Read all chunks up front into a slot list so workers can index directly.
        # For very large files this would be memory-heavy; in that case the Rust
        # side streams from disk. Here we chunk lazily but hold references so
        # parallel workers can re-read on retry without reopening the file.
        chunks: list[bytes] = []
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(part_size)
                if not chunk:
                    break
                chunks.append(chunk)
                if md5 is not None:
                    md5.update(chunk)

        # Open independent worker connections (sequentially -- see
        # _open_worker_conn for why), each holding a `max_tcp_connections`
        # permit for the life of this upload. Falls back to the home
        # connection alone if no extra workers could be opened at all.
        conns: list[DcConnection] = []
        stack = AsyncExitStack()
        for _ in range(n_workers):
            try:
                conns.append(await stack.enter_async_context(self._worker_slot(self._dc_id)))
            except Exception as e:
                _log.warning(
                    "upload_file: worker connection failed, continuing with %d worker(s): %s",
                    max(len(conns), 1), e,
                )
                break
        # Each conn above is a dedicated socket opened just for this
        # transfer  - safe to consume into a PipelinedSender. The fallback
        # below reuses the client's shared session connection instead, which
        # must keep working for everything else the client does, so it can
        # never be handed off to into_pipelined_sender().
        dedicated = bool(conns)
        if not conns:
            conns = [self._require_conn()]

        next_part = 0
        next_part_lock = asyncio.Lock()

        async def upload_part_on(conn: "DcConnection", part_idx: int, chunk: bytes) -> None:
            MAX_ATTEMPTS = 5
            delay = 1.0
            for attempt in range(MAX_ATTEMPTS):
                if handle is not None:
                    await handle._poll_pause_cancel()
                try:
                    if is_big:
                        req = {
                            "_": "upload.saveBigFilePart",
                            "file_id": file_id,
                            "file_part": part_idx,
                            "file_total_parts": total_parts,
                            "bytes": chunk,
                        }
                    else:
                        req = {
                            "_": "upload.saveFilePart",
                            "file_id": file_id,
                            "file_part": part_idx,
                            "bytes": chunk,
                        }
                    req_bytes  = _tl.serialize(req, _SCHEMA)
                    resp_bytes = await conn.rpc_call(req_bytes)
                    ok = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                    if not ok:
                        raise RuntimeError(f"upload_file: part {part_idx} rejected by server")
                    if handle is not None:
                        handle._add_bytes(len(chunk))
                    return
                except Exception as e:
                    if attempt == MAX_ATTEMPTS - 1:
                        raise
                    _log.warning(
                        "upload_file: part %d failed (attempt %d/%d): %s — retrying in %.1fs",
                        part_idx, attempt + 1, MAX_ATTEMPTS, e, delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)

        def _build_upload_req(part_idx: int, chunk: bytes) -> bytes:
            if is_big:
                req = {
                    "_": "upload.saveBigFilePart",
                    "file_id": file_id,
                    "file_part": part_idx,
                    "file_total_parts": total_parts,
                    "bytes": chunk,
                }
            else:
                req = {
                    "_": "upload.saveFilePart",
                    "file_id": file_id,
                    "file_part": part_idx,
                    "bytes": chunk,
                }
            return _tl.serialize(req, _SCHEMA)

        async def worker(conn: "DcConnection") -> None:
            nonlocal next_part
            while True:
                async with next_part_lock:
                    if next_part >= total_parts:
                        return
                    idx = next_part
                    next_part += 1
                await upload_part_on(conn, idx, chunks[idx])

        async def worker_pipelined(conn: "DcConnection") -> None:
            """X > 1 worker: keeps `upload_pipeline_depth` chunk requests in
            flight on one socket at once instead of one-at-a-time. Mirrors
            the sliding-window loop in ferogram's Rust `media.rs`."""
            nonlocal next_part
            depth = max(1, self._transfer_limits.upload_pipeline_depth)
            sender = await conn.into_pipelined_sender()
            # Sliding window of (part_idx, chunk, in-flight PipelinedRequest).
            window: deque[tuple[int, bytes, Any]] = deque()

            async def submit_next() -> bool:
                nonlocal next_part
                async with next_part_lock:
                    if next_part >= total_parts:
                        return False
                    idx = next_part
                    next_part += 1
                chunk = chunks[idx]
                request = await sender.enqueue(_build_upload_req(idx, chunk))
                window.append((idx, chunk, request))
                return True

            while True:
                if handle is not None:
                    await handle._poll_pause_cancel()
                while len(window) < depth:
                    if not await submit_next():
                        break
                if not window:
                    return
                idx, chunk, request = window.popleft()
                try:
                    resp_bytes = await request.wait()
                except Exception as e:
                    if not sender.is_alive():
                        raise
                    # Transient failure on an otherwise-live connection:
                    # retry this one part directly, out of band from the
                    # window, rather than tearing down the whole worker.
                    _log.warning(
                        "upload_file: pipelined part %d failed, retrying directly: %s",
                        idx, e,
                    )
                    resp_bytes = await sender.call(_build_upload_req(idx, chunk))
                ok = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                if not ok:
                    raise RuntimeError(f"upload_file: part {idx} rejected by server")
                if handle is not None:
                    handle._add_bytes(len(chunk))

        try:
            if dedicated:
                await asyncio.gather(*[worker_pipelined(c) for c in conns])
            else:
                await asyncio.gather(*[worker(c) for c in conns])
        finally:
            await stack.aclose()

        if is_big:
            return {"_": "inputFileBig", "id": file_id, "parts": total_parts, "name": file_name}
        return {
            "_": "inputFile",
            "id": file_id,
            "parts": total_parts,
            "name": file_name,
            "md5_checksum": md5.hexdigest() if md5 else "",  # type: ignore[union-attr]
        }

    async def upload_media(self, peer: str, path: str) -> int | None:
        result = await self.send_document(peer, path)
        msg = result.get("updates", [{}])[0] if isinstance(result.get("updates"), list) else {}
        return msg.get("id")

    async def download_media(self, peer: str, msg_id: int, path: str, *,
                             handle: "TransferHandle | None" = None,
                             quality: str = "original") -> str:
        """Download media from a message to a local file.

        Uses independent parallel worker connections opened directly on the
        DC the media actually lives on (its `dc_id` field, which is often
        not the home DC) and adaptive chunk sizes matching ferogram's Rust
        download implementation. Supports pause, resume, and cancel via
        handle.

        `quality` picks a variant from the media's `alt_documents` (e.g. a
        video with a quality picker in official clients): one of
        `"original"` (default), `"highest"`, or `"lowest"`. Media with no
        alternates only ever has `"original"` to pick from; every other
        value falls back to it automatically. Use `available_qualities()`
        to see what's actually on offer before choosing.
        """
        msg = await self.get_message(peer, msg_id)
        if not msg:
            raise ValueError(f"Message {msg_id} not found")
        media = msg.get("media", {})
        return await self._download_media_object(media, path, handle=handle, quality=quality)

    async def _download_media_object(self, media: dict, path: str, *,
                                      handle: "TransferHandle | None" = None,
                                      quality: str = "original") -> str:
        if not isinstance(media, dict):
            raise ValueError("No media in message")
        if quality not in ("original", "highest", "lowest"):
            raise ValueError(
                f'unknown quality {quality!r}, use: "original" | "highest" | "lowest"'
            )
        t = media.get("_", "")
        file_size = 0
        media_dc_id = self._dc_id

        if t == "messageMediaPhoto":
            photo = media.get("photo", {})
            sizes = photo.get("sizes", [])
            if not sizes:
                raise ValueError("Photo has no sizes")
            best = max(
                (s for s in sizes if isinstance(s, dict)),
                key=lambda s: s.get("size", 0),
                default=None,
            )
            if best is None:
                raise ValueError("Photo has no valid size entry")
            file_size = best.get("size", 0)
            media_dc_id = photo.get("dc_id") or self._dc_id
            location = {
                "_": "inputPhotoFileLocation",
                "id": photo.get("id", 0),
                "access_hash": photo.get("access_hash", 0),
                "file_reference": photo.get("file_reference", b""),
                "thumb_size": best.get("type", "s"),
            }

        elif t == "messageMediaDocument":
            doc = _resolve_quality_document(media, quality)
            if not isinstance(doc, dict):
                raise ValueError("media has no downloadable document for the requested quality")
            file_size = doc.get("size", 0)
            media_dc_id = doc.get("dc_id") or self._dc_id
            location = {
                "_": "inputDocumentFileLocation",
                "id": doc.get("id", 0),
                "access_hash": doc.get("access_hash", 0),
                "file_reference": doc.get("file_reference", b""),
                "thumb_size": "",
            }

        else:
            raise ValueError(f"Unsupported media type: {t!r}")

        chunk_size = self._download_chunk_size(file_size)
        n_workers  = self._download_worker_count(file_size)
        total_parts = max(1, (file_size + chunk_size - 1) // chunk_size) if file_size > 0 else None

        if handle is not None:
            handle._set_total(file_size)
            handle._reset_start()

        async def open_conn_for(dc_id: int) -> "DcConnection":
            if dc_id == self._dc_id:
                return self._require_conn()
            return await self._open_worker_conn(dc_id)

        if total_parts is not None and total_parts > 1 and n_workers > 1:
            n_workers = min(n_workers, total_parts)

            # Open independent worker connections directly on the DC the
            # media lives on (sequentially -- see _open_worker_conn), each
            # holding a `max_tcp_connections` permit for the life of this
            # download.
            conns: list[DcConnection] = []
            dl_stack = AsyncExitStack()
            for _ in range(n_workers):
                try:
                    conns.append(await dl_stack.enter_async_context(self._worker_slot(media_dc_id)))
                except Exception as e:
                    _log.warning(
                        "download: worker connection to DC%d failed, continuing with %d worker(s): %s",
                        media_dc_id, max(len(conns), 1), e,
                    )
                    break
            # Same reasoning as upload_file: only conns opened here are
            # dedicated sockets safe to hand off to a PipelinedSender. The
            # fallback reuses the shared home connection and must stay on
            # the one-at-a-time path.
            dl_dedicated = bool(conns)
            if not conns:
                conns = [await open_conn_for(media_dc_id)]

            parts_buf: list[bytes | None] = [None] * total_parts
            next_part = 0
            next_part_lock = asyncio.Lock()

            async def fetch_part_on(conn: "DcConnection", part_idx: int) -> "DcConnection":
                offset = part_idx * chunk_size
                MAX_ATTEMPTS = 5
                delay = 1.0
                attempt = 0
                while True:
                    if handle is not None:
                        await handle._poll_pause_cancel()
                    try:
                        req_bytes = _tl.serialize({
                            "_": "upload.getFile",
                            "location": location,
                            "offset": offset,
                            "limit": chunk_size,
                        }, _SCHEMA)
                        resp_bytes = await conn.rpc_call(req_bytes)
                        result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                        data = result.get("bytes", b"") if isinstance(result, dict) else b""
                        parts_buf[part_idx] = data
                        if handle is not None:
                            handle._add_bytes(len(data))
                        return conn
                    except Exception as e:
                        new_dc = _parse_migrate(str(e)) if isinstance(e, RuntimeError) else None
                        if new_dc is not None:
                            _log.info(
                                "download: FILE_MIGRATE_%d for part %d, reopening worker on new DC",
                                new_dc, part_idx,
                            )
                            conn = await self._open_worker_conn(new_dc)
                            continue  # migrate redirects don't consume a retry attempt
                        attempt += 1
                        if attempt >= MAX_ATTEMPTS:
                            raise
                        _log.warning(
                            "download: part %d failed (attempt %d/%d): %s — retrying in %.1fs",
                            part_idx, attempt, MAX_ATTEMPTS, e, delay,
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 30.0)

            async def worker(conn: "DcConnection") -> None:
                nonlocal next_part
                cur_conn = conn
                while True:
                    async with next_part_lock:
                        if next_part >= total_parts:
                            return
                        idx = next_part
                        next_part += 1
                    cur_conn = await fetch_part_on(cur_conn, idx)

            def _build_download_req(offset: int) -> bytes:
                return _tl.serialize({
                    "_": "upload.getFile",
                    "location": location,
                    "offset": offset,
                    "limit": chunk_size,
                }, _SCHEMA)

            async def worker_pipelined(conn: "DcConnection") -> None:
                """X > 1 worker: keeps `download_pipeline_depth` chunk
                requests in flight on one socket at once. Mirrors the
                sliding-window loop in ferogram's Rust `media.rs`."""
                nonlocal next_part
                depth = max(1, self._transfer_limits.download_pipeline_depth)
                sender = await conn.into_pipelined_sender()
                # Sliding window of (part_idx, in-flight PipelinedRequest).
                window: deque[tuple[int, Any]] = deque()

                async def submit_next() -> bool:
                    nonlocal next_part
                    async with next_part_lock:
                        if next_part >= total_parts:
                            return False
                        idx = next_part
                        next_part += 1
                    request = await sender.enqueue(_build_download_req(idx * chunk_size))
                    window.append((idx, request))
                    return True

                while True:
                    if handle is not None:
                        await handle._poll_pause_cancel()
                    while len(window) < depth:
                        if not await submit_next():
                            break
                    if not window:
                        return
                    idx, request = window.popleft()
                    try:
                        resp_bytes = await request.wait()
                    except Exception as e:
                        new_dc = _parse_migrate(str(e)) if isinstance(e, RuntimeError) else None
                        if new_dc is not None:
                            # A redirect invalidates every part still in
                            # flight from the old DC/session, not just this
                            # one -- reopen fresh and resubmit the lot.
                            _log.info(
                                "download: FILE_MIGRATE_%d mid-pipeline, reopening on new DC (part %d)",
                                new_dc, idx,
                            )
                            pending = [idx] + [w[0] for w in window]
                            window.clear()
                            new_conn = await self._open_worker_conn(new_dc)
                            sender = await new_conn.into_pipelined_sender()
                            for pidx in sorted(pending):
                                req = await sender.enqueue(_build_download_req(pidx * chunk_size))
                                window.append((pidx, req))
                            continue
                        if not sender.is_alive():
                            raise
                        _log.warning(
                            "download: pipelined part %d failed, retrying directly: %s",
                            idx, e,
                        )
                        resp_bytes = await sender.call(_build_download_req(idx * chunk_size))
                    result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                    data = result.get("bytes", b"") if isinstance(result, dict) else b""
                    parts_buf[idx] = data
                    if handle is not None:
                        handle._add_bytes(len(data))

            try:
                if dl_dedicated:
                    await asyncio.gather(*[worker_pipelined(c) for c in conns])
                else:
                    await asyncio.gather(*[worker(c) for c in conns])
            finally:
                await dl_stack.aclose()

            with open(path, "wb") as fh:
                for part in parts_buf:
                    if part:
                        fh.write(part)
        else:
            # Sequential path: unknown size or single worker. Still uses the
            # media's actual DC, not blindly the home connection.
            conn = await open_conn_for(media_dc_id)
            offset = 0
            with open(path, "wb") as fh:
                while True:
                    if handle is not None:
                        await handle._poll_pause_cancel()
                    req_bytes = _tl.serialize({
                        "_": "upload.getFile",
                        "location": location,
                        "offset": offset,
                        "limit": chunk_size,
                    }, _SCHEMA)
                    try:
                        resp_bytes = await conn.rpc_call(req_bytes)
                    except RuntimeError as e:
                        new_dc = _parse_migrate(str(e))
                        if new_dc is not None:
                            conn = await self._open_worker_conn(new_dc)
                            continue
                        raise
                    result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                    data = result.get("bytes", b"") if isinstance(result, dict) else b""
                    if not data:
                        break
                    fh.write(data)
                    if handle is not None:
                        handle._add_bytes(len(data))
                    offset += len(data)
                    if len(data) < chunk_size:
                        break

        return path

    async def download_with_progress(
        self,
        peer: str,
        msg_id: int,
        path: str,
        on_progress: "Callable[[int, int], None] | None" = None,
        *,
        handle: "TransferHandle | None" = None,
        quality: str = "original",
    ) -> str:
        """Download media with an optional per-second progress callback.

        on_progress(bytes_done, total_bytes) is called once per second while
        downloading. Pass a TransferHandle to pause, resume, or cancel.
        `quality` is the same `"original"|"highest"|"lowest"` picker as
        `download_media`.
        """
        if handle is None:
            handle = TransferHandle()
        stop_ticker = asyncio.Event()

        async def _ticker() -> None:
            while not stop_ticker.is_set():
                await asyncio.sleep(1)
                if on_progress is not None and not stop_ticker.is_set():
                    p = handle.progress()
                    on_progress(p["done"], p["total"])

        ticker_task = asyncio.ensure_future(_ticker())
        try:
            result = await self.download_media(peer, msg_id, path, handle=handle, quality=quality)
        finally:
            stop_ticker.set()
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass
        if on_progress is not None:
            p = handle.progress()
            on_progress(p["done"], p["total"])
        return result

    async def upload_with_progress(
        self,
        path: str,
        on_progress: "Callable[[int, int], None] | None" = None,
        *,
        handle: "TransferHandle | None" = None,
    ) -> dict:
        """Upload a file with an optional per-second progress callback.

        on_progress(bytes_done, total_bytes) is called once per second while
        uploading. Pass a TransferHandle to pause, resume, or cancel.
        Returns the inputFile dict (same as upload_file).
        """
        if handle is None:
            handle = TransferHandle()
        stop_ticker = asyncio.Event()

        async def _ticker() -> None:
            while not stop_ticker.is_set():
                await asyncio.sleep(1)
                if on_progress is not None and not stop_ticker.is_set():
                    p = handle.progress()
                    on_progress(p["done"], p["total"])

        ticker_task = asyncio.ensure_future(_ticker())
        try:
            result = await self.upload_file(path, handle=handle)
        finally:
            stop_ticker.set()
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass
        if on_progress is not None:
            p = handle.progress()
            on_progress(p["done"], p["total"])
        return result

    async def edit_chat_photo(self, peer: str, path: str) -> None:
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        t = input_peer.get("_", "")
        if "Channel" in t:
            await self._rpc({
                "_": "channels.editPhoto",
                "channel": input_peer,
                "photo": {"_": "inputChatUploadedPhoto", "file": file_input},
            })
        else:
            await self._rpc({
                "_": "messages.editChatPhoto",
                "chat_id": input_peer.get("chat_id", 0),
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

    async def get_chat_photos(self, peer: str, limit: int = 100) -> list[tuple[int, int, int]]:
        """Photo/avatar history for a group or channel (get_profile_photos only works for users).

        The current photo comes from the chat's full info, so it's returned
        even if every photo-change message has been deleted. Older photos
        come from `messageActionChatEditPhoto` service messages, so those
        are lost if the underlying messages were deleted; there's no other
        way to recover them.
        """
        input_peer = await self._resolve_peer(peer)
        photos: list[tuple[int, int, int]] = []
        seen_id: int | None = None

        t = input_peer.get("_", "")
        try:
            if "Channel" in t:
                full_result = await self._rpc({"_": "channels.getFullChannel", "channel": input_peer})
            else:
                full_result = await self._rpc({"_": "messages.getFullChat", "chat_id": input_peer.get("chat_id", 0)})
            full = full_result.get("full_chat", {}) if isinstance(full_result, dict) else {}
            current = full.get("chat_photo")
            if isinstance(current, dict) and current.get("_") == "photo":
                seen_id = current.get("id", 0)
                photos.append((current.get("id", 0), current.get("access_hash", 0), current.get("dc_id", 0)))
        except Exception:
            pass  # current photo is a nice-to-have; fall through to history regardless

        result = await self._rpc({
            "_": "messages.search",
            "peer": input_peer,
            "q": "",
            "filter": {"_": "inputMessagesFilterChatPhotos"},
            "min_date": 0,
            "max_date": 0,
            "offset_id": 0,
            "add_offset": 0,
            "limit": limit,
            "max_id": 0,
            "min_id": 0,
            "hash": 0,
        })
        messages = result.get("messages", []) if isinstance(result, dict) else []
        for m in messages:
            action = m.get("action", {}) if isinstance(m, dict) else {}
            if action.get("_") != "messageActionChatEditPhoto":
                continue
            photo = action.get("photo", {})
            if not isinstance(photo, dict) or photo.get("_") != "photo":
                continue
            pid = photo.get("id", 0)
            if pid == seen_id:
                continue
            photos.append((pid, photo.get("access_hash", 0), photo.get("dc_id", 0)))

        return photos


    async def block_user(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "contacts.block", "id": input_peer})

    async def unblock_user(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "contacts.unblock", "id": input_peer})

    async def get_blocked_users(self, limit: int = 100, my_stories_from: bool = False) -> list[int]:
        result = await self._rpc({"_": "contacts.getBlocked", "my_stories_from": my_stories_from, "offset": 0, "limit": limit})
        blocked = result.get("blocked", []) if isinstance(result, dict) else []
        return [b.get("peer_id", {}).get("user_id", 0) for b in blocked]

    async def add_contact(self, user_id: int, first_name: str, last_name: str = "", phone: str = "",
                          add_phone_privacy_exception: bool = False) -> None:
        ah = self._peer_cache.get_user(user_id) or 0
        await self._rpc({
            "_": "contacts.addContact",
            "add_phone_privacy_exception": add_phone_privacy_exception,
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
                                   new_text: str, reply_markup=None,
                                   no_webpage: bool = True) -> bool:
        if isinstance(msg_id, InlineMessageId):
            dc_id, id_bytes = msg_id.dc_id, msg_id.id_bytes
        else:
            dc_id, id_bytes = msg_id
        req: dict = {
            "_": "messages.editInlineBotMessage",
            "id": {"_": "inputBotInlineMessageID64", "dc_id": dc_id, "id": int.from_bytes(id_bytes[:8], "little")},
            "message": new_text,
        }
        if no_webpage:
            req["no_webpage"] = True
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
                           need_shipping_address: bool = False, is_flexible: bool = False,
                           test: bool = False) -> dict:
        input_peer = await self._resolve_peer(peer)
        invoice: dict = {
            "_": "invoice",
            "currency": currency,
            "prices": [{"_": "labeledPrice", "label": l, "amount": a} for l, a in prices],
            "test": test,
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

    async def join_invite_link(self, link: str) -> dict:
        """Import a chat invite link.

        Returns the raw `messages.ChatInviteJoinResult` dict as-is - either
        `messages.chatInviteJoinResultOk` (`{"updates": ...}`) or
        `messages.chatInviteJoinResultWebView` (`{"bot_id", "query_id",
        "users"}`, no Updates - join isn't complete without driving that bot
        flow). Use `join_chat()` for a version that resolves this down to an
        InputPeer or None.
        """
        result = await self._rpc({"_": "messages.importChatInvite", "hash": _extract_invite_hash(link)})
        if isinstance(result, dict) and result.get("_") == "messages.chatInviteJoinResultOk":
            self._populate_cache(result.get("updates") or {})
        return result

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
