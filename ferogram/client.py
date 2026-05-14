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
import inspect
import logging
import os
from typing import Any, Callable

from ._ferogram import Client as _RustClient, PasswordToken, User, Dialog, ChatMember, UserFull
from ._ferogram import Message, CallbackQuery
from ._ferogram import (
    MessageDeletion, InlineQuery, InlineSend, UserStatus,
    ParticipantUpdate, JoinRequest, MessageReaction,
    PollVote, BotStopped, RawUpdate,
    ShippingQuery, PreCheckoutQuery, ChatBoost, MiniAppSession,
)
from ._ferogram import Chat, Authorization, ForumTopic, BotInfo
from ._ferogram import InviteLinkMember, ReadParticipant, AdminLogEvent, StickerSetInfo
from ._ferogram import BroadcastStats, MegagroupStats, NotifySettings
from .raw import _tl
from .raw.generated._tl_schema import _SCHEMA, _SCHEMA_BY_CID
from .raw.proxy import RawProxy, PeerCache, resolve_peer as _resolve_peer_fn
from .types import (
    ChatAction, PrivacyKey, PrivacyRule,
    InlineMessageId, InlineArticle, InlinePhoto, InlineDocument,
    _inline_result_to_tuple,
)

__all__ = ["Client"]

_log = logging.getLogger("ferogram")

_Handler = tuple[Callable, list[Callable]]

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
        session: str = "ferogram",
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
        self.device                   = device
        self.system_version           = system_version
        self.app_version              = app_version
        self.lang_code                = lang_code
        self.system_lang_code         = system_lang_code
        self.lang_pack                = lang_pack
        self.session_string           = session_string
        self.in_memory                = in_memory
        self.update_queue_capacity    = update_queue_capacity
        self.update_overflow          = update_overflow
        self.low_memory_mode          = low_memory_mode
        self.allow_missing_channel_hash = allow_missing_channel_hash
        self.auto_resolve_peers       = auto_resolve_peers
        self._raw: _RustClient | None = None
        self._handlers: dict[str, list[_Handler]] = {e: [] for e in _ALL_EVENTS}
        self._peer_cache = PeerCache()
        self.raw         = RawProxy(self)

    def _require_creds(self) -> tuple[int, str]:
        if not self.api_id or not self.api_hash:
            raise ValueError("api_id and api_hash required.")
        return self.api_id, self.api_hash

    @property
    def _client(self) -> _RustClient:
        if self._raw is None:
            raise RuntimeError("Call await app.start() first.")
        return self._raw


    def on_message(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["message"].append((func, list(filters)))
            return func
        return decorator

    def on_edited_message(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["edited_message"].append((func, list(filters)))
            return func
        return decorator

    def on_message_deleted(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["message_deleted"].append((func, list(filters)))
            return func
        return decorator

    def on_callback_query(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["callback_query"].append((func, list(filters)))
            return func
        return decorator

    def on_inline_query(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["inline_query"].append((func, list(filters)))
            return func
        return decorator

    def on_inline_send(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["inline_send"].append((func, list(filters)))
            return func
        return decorator

    def on_user_status(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["user_status"].append((func, list(filters)))
            return func
        return decorator

    def on_chat_action(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["chat_action"].append((func, list(filters)))
            return func
        return decorator

    def on_participant_update(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["participant_update"].append((func, list(filters)))
            return func
        return decorator

    def on_join_request(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["join_request"].append((func, list(filters)))
            return func
        return decorator

    def on_message_reaction(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["message_reaction"].append((func, list(filters)))
            return func
        return decorator

    def on_poll_vote(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["poll_vote"].append((func, list(filters)))
            return func
        return decorator

    def on_bot_stopped(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["bot_stopped"].append((func, list(filters)))
            return func
        return decorator

    def on_shipping_query(self, *filters: Callable) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._handlers["shipping_query"].append((fn, list(filters)))
            return fn
        return decorator

    def on_pre_checkout_query(self, *filters: Callable) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._handlers["pre_checkout_query"].append((fn, list(filters)))
            return fn
        return decorator

    def on_chat_boost(self, *filters: Callable) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._handlers["chat_boost"].append((fn, list(filters)))
            return fn
        return decorator

    def on_raw_update(self, *filters: Callable) -> Callable:
        def decorator(func: Callable) -> Callable:
            self._handlers["raw_update"].append((func, list(filters)))
            return func
        return decorator


    async def _dispatch(self, event_type: str, update: Any) -> None:
        for func, fltrs in self._handlers.get(event_type, []):
            if all(f(update) for f in fltrs):
                try:
                    result = func(self, update)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    _log.error("handler error in %s: %s", event_type, exc, exc_info=True)

    async def _run_updates(self) -> None:
        _log.debug("update loop started")
        while True:
            result = await self._client.next_update()
            if result is None:
                _log.debug("update stream closed")
                break
            event_type, update = result
            _log.debug("dispatching %s", event_type)
            asyncio.create_task(self._dispatch(event_type, update))


    async def start(self) -> "Client":
        if self._raw is not None:
            return self
        api_id, api_hash = self._require_creds()
        session_path = self.session if self.session.endswith(".session") else self.session + ".session"
        _log.info("connecting (session=%r)", session_path)
        builder = _RustClient.builder(api_id, api_hash, session_path)
        builder.proxy                      = self.proxy
        builder.allow_ipv6                 = self.allow_ipv6
        builder.dc_addr                    = self.dc_addr
        builder.probe_transport            = self.probe_transport
        builder.resilient_connect          = self.resilient_connect
        builder.catch_up                   = self.catch_up
        builder.pfs                        = self.pfs
        builder.device_model               = self.device
        builder.system_version             = self.system_version
        builder.app_version                = self.app_version
        builder.lang_code                  = self.lang_code
        builder.system_lang_code           = self.system_lang_code
        builder.lang_pack                  = self.lang_pack
        builder.session_string             = self.session_string
        builder.in_memory                  = self.in_memory
        builder.update_queue_capacity      = self.update_queue_capacity
        builder.update_overflow            = self.update_overflow
        builder.low_memory_mode            = self.low_memory_mode
        builder.allow_missing_channel_hash = self.allow_missing_channel_hash
        builder.auto_resolve_peers         = self.auto_resolve_peers
        self._raw = await builder.connect()
        if not await self._raw.is_authorized():
            if self.bot_token:
                await self._raw.bot_sign_in(self.bot_token)
                _log.info("signed in as bot")
            else:
                await self._interactive_login()
            await self._raw.save_session()
        else:
            _log.info("reusing existing session")
        return self

    async def _interactive_login(self) -> None:
        phone    = self._phone or input("Phone (+countrycode): ")
        token    = await self._client.request_login_code(phone)
        pw_token = await self._client.sign_in(token, input("Code: "))
        if pw_token is not None:
            hint = pw_token.hint
            pwd  = self._password or input(f"2FA password (hint: {hint}): " if hint else "2FA password: ")
            await self._client.check_password(pw_token, pwd)
        _log.info("signed in as user")

    async def stop(self) -> None:
        if self._raw:
            await self._raw.sign_out()
            self._raw = None
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


    async def send_message(
        self,
        peer: str,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup=None,
    ) -> Message:
        """Send a text message.

        parse_mode: None (plain), 'html', or 'markdown'/'md'.
        reply_markup: InlineKeyboard, ReplyKeyboard, RemoveKeyboard, or ForceReply.
        """
        if parse_mode == "html":
            return await self._client.send_html(peer, text, reply_markup)
        if parse_mode in ("markdown", "md"):
            return await self._client.send_markdown(peer, text, reply_markup)
        return await self._client.send_message(peer, text, reply_markup)

    async def send_to_self(self, text: str) -> None:
        """Send a plain-text message to Saved Messages (yourself)."""
        await self._client.send_to_self(text)

    async def edit_message(self, peer: str, message_id: int, new_text: str) -> None:
        await self._client.edit_message(peer, message_id, new_text)

    async def delete_message(self, message_id: int, revoke: bool = True) -> None:
        """Delete a single message. Alias for delete_messages([message_id])."""
        await self._client.delete_messages([message_id], revoke)

    async def delete_messages(self, message_ids: list[int], revoke: bool = True) -> None:
        await self._client.delete_messages(message_ids, revoke)

    async def forward_messages(self, destination: str, source: str, message_ids: list[int]) -> None:
        await self._client.forward_messages(destination, source, message_ids)

    async def pin_message(self, peer: str, message_id: int) -> None:
        await self._client.pin_message(peer, message_id)

    async def unpin_message(self, peer: str, message_id: int) -> None:
        await self._client.unpin_message(peer, message_id)

    async def unpin_all_messages(self, peer: str) -> None:
        await self._client.unpin_all_messages(peer)

    async def mark_as_read(self, peer: str) -> None:
        await self._client.mark_as_read(peer)

    async def clear_mentions(self, peer: str) -> None:
        await self._client.clear_mentions(peer)

    async def send_reaction(self, peer: str, message_id: int, emoji: str) -> None:
        await self._client.send_reaction(peer, message_id, emoji)

    async def send_chat_action(self, peer: str, action: "ChatAction | str") -> None:
        """Send a chat action. Accepts ChatAction enum or plain string."""
        await self._client.send_chat_action(peer, str(action))

    async def get_messages_by_id(self, peer: str, message_ids: list[int]) -> list[Message]:
        return await self._client.get_messages_by_id(peer, message_ids)

    async def get_message(self, peer: str, msg_id: int) -> Message | None:
        msgs = await self._client.get_messages_by_id(peer, [msg_id])
        return msgs[0] if msgs else None

    async def send_dice(self, peer: str, emoticon: str = "🎲") -> None:
        """Send an animated dice/game emoji.

        Common values: 🎲 (dice)  🎯 (dart)  🏀 (basketball)  ⚽ (football)  🎳 (bowling)  🎰 (slot)
        """
        await self._client.send_dice(peer, emoticon)

    async def delete_dialog(self, peer: str) -> None:
        await self._client.delete_dialog(peer)


    async def join_chat(self, peer: str) -> None:
        await self._client.join_chat(peer)

    async def leave_chat(self, peer: str) -> None:
        await self._client.leave_chat(peer)

    async def get_online_count(self, peer: str) -> int:
        return await self._client.get_online_count(peer)

    async def get_chat_administrators(self, peer: str) -> list[ChatMember]:
        return await self._client.get_chat_administrators(peer)

    async def get_participants(
        self, peer: str, limit: int = 200
    ) -> list[ChatMember]:
        return await self._client.get_participants(peer, limit)

    async def get_participants_filtered(
        self,
        peer: str,
        filter: str = "recent",
        limit: int = 200,
    ) -> list[ChatMember]:
        return await self._client.get_participants_filtered(peer, filter, limit)

    async def kick_participant(self, peer: str, user: str) -> None:
        await self._client.kick_participant(peer, user)

    async def ban_participant(self, peer: str, user: str) -> None:
        await self._client.ban_participant(peer, user)

    async def ban_participant_until(
        self, peer: str, user: str, until_date: int
    ) -> None:
        await self._client.ban_participant_until(peer, user, until_date)

    async def promote_participant(
        self, peer: str, user: str,
        rights: list[str] | None = None,
    ) -> None:
        await self._client.promote_participant(peer, user, rights or [])

    async def demote_participant(self, peer: str, user: str) -> None:
        await self._client.demote_participant(peer, user)

    async def get_profile_photos(
        self, peer: str, limit: int = 100
    ) -> list[tuple[int, int, int]]:
        """Returns list of (file_id, access_hash, dc_id)."""
        return await self._client.get_profile_photos(peer, limit)

    async def search_peer(self, query: str) -> list[str]:
        """Search among locally cached contacts and peers."""
        return await self._client.search_peer(query)

    def signal_network_restored(self) -> None:
        """Tell the client network is back. Triggers immediate reconnect."""
        self._client.signal_network_restored()

    async def archive_chat(self, peer: str) -> None:
        await self._client.archive_chat(peer)

    async def unarchive_chat(self, peer: str) -> None:
        await self._client.unarchive_chat(peer)

    async def pin_dialog(self, peer: str) -> None:
        await self._client.pin_dialog(peer)

    async def unpin_dialog(self, peer: str) -> None:
        await self._client.unpin_dialog(peer)


    async def block_user(self, peer: str) -> None:
        await self._client.block_user(peer)

    async def unblock_user(self, peer: str) -> None:
        await self._client.unblock_user(peer)

    async def get_contacts(self) -> list[User]:
        return await self._client.get_contacts()


    async def get_users_by_id(self, user_ids: list[int]) -> list[User | None]:
        return await self._client.get_users_by_id(user_ids)

    async def get_user_full(self, user_id: int) -> UserFull:
        return await self._client.get_user_full(user_id)

    async def get_me(self) -> User:
        return await self._client.get_me()

    async def get_dialogs(self, limit: int = 100) -> list[Dialog]:
        return await self._client.get_dialogs(limit)

    async def export_session_string(self) -> str:
        return await self._client.export_session_string()


    async def send_photo(self, peer: str, path: str, caption: str = "") -> Message:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_photo(peer, path, caption)

    async def send_file(self, peer: str, path: str, caption: str = "", mime_type: str | None = None) -> Message:
        """Send any file. mime_type controls how Telegram displays it."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_file(peer, path, caption, mime_type)

    async def send_document(self, peer: str, path: str, caption: str = "", mime_type: str | None = None) -> Message:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_document(peer, path, caption, mime_type)

    async def send_audio(self, peer: str, path: str, caption: str = "") -> Message:
        """Send an audio file (audio/mpeg). Alias for send_file(..., mime_type='audio/mpeg')."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_document(peer, path, caption, _AUDIO_MIME)

    async def send_video(self, peer: str, path: str, caption: str = "") -> Message:
        """Send a video file (video/mp4). Alias for send_file(..., mime_type='video/mp4')."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_document(peer, path, caption, _VIDEO_MIME)

    async def send_voice(self, peer: str, path: str, caption: str = "") -> Message:
        """Send a voice message (audio/ogg). Alias for send_file(..., mime_type='audio/ogg')."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_document(peer, path, caption, _VOICE_MIME)

    async def send_sticker(self, peer: str, path: str) -> Message:
        """Send a WebP sticker. Alias for send_file(..., mime_type='image/webp')."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_document(peer, path, "", _STICKER_MIME)


    async def search_messages(self, peer: str, query: str, limit: int = 100) -> list[Message]:
        return await self._client.search_messages(peer, query, limit)

    async def search_global(self, query: str, limit: int = 100) -> list[Message]:
        return await self._client.search_global(query, limit)


    async def iter_dialogs(self, *, limit: int | None = None):
        """Async generator over all dialogs, most recent first.

        Fetches up to `limit` dialogs. Without a limit, fetches up to 5000.
        True server-side pagination requires raw GetDialogs offsets; add that
        if you need to walk truly massive dialog lists.
        """
        fetch_limit = limit if limit is not None else 5000
        dialogs = await self._client.get_dialogs(fetch_limit)
        for d in dialogs:
            yield d

    async def iter_messages(self, peer: str, *, limit: int | None = None, offset_id: int = 0):
        """Async generator over message history, newest first."""
        remaining = limit
        cur_offset = offset_id
        batch = 100
        while True:
            chunk_size = batch if remaining is None else min(batch, remaining)
            if chunk_size <= 0:
                return
            msgs = await self._client.get_message_history(peer, chunk_size, cur_offset)
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
            cur_offset = msgs[-1].id

    async def iter_reaction_users(self, peer: str, msg_id: int, *, reaction: str | None = None):
        """Async generator over users who reacted to a message."""
        offset: str | None = None
        batch = 100
        while True:
            page = await self._client.iter_reaction_users(peer, msg_id, reaction, batch, offset)
            for r in page.reactions:
                yield r
            if not getattr(page, "next_offset", None):
                return
            offset = page.next_offset


    async def create_group(self, title: str, user_ids: list[int]) -> Chat:
        return await self._client.create_group(title, user_ids)

    async def create_channel(self, title: str, about: str = "", broadcast: bool = True) -> Chat:
        """Create a broadcast channel (broadcast=True) or supergroup (broadcast=False)."""
        return await self._client.create_channel(title, about, broadcast)

    async def delete_channel(self, peer: str) -> None:
        await self._client.delete_channel(peer)

    async def delete_chat(self, chat_id: int) -> None:
        await self._client.delete_chat(chat_id)

    async def edit_chat_title(self, peer: str, title: str) -> None:
        await self._client.edit_chat_title(peer, title)

    async def edit_chat_about(self, peer: str, about: str) -> None:
        await self._client.edit_chat_about(peer, about)

    async def invite_users(self, peer: str, user_ids: list[int]) -> None:
        await self._client.invite_users(peer, user_ids)

    async def set_history_ttl(self, peer: str, period: int) -> None:
        """period in seconds. 0 = disable. common: 86400, 604800, 2678400"""
        await self._client.set_history_ttl(peer, period)

    async def delete_chat_history(self, peer: str, max_id: int = 0, revoke: bool = False) -> None:
        await self._client.delete_chat_history(peer, max_id, revoke)

    async def migrate_chat(self, chat_id: int) -> Chat:
        return await self._client.migrate_chat(chat_id)



    async def add_contact(self, user_id: int, first_name: str, last_name: str = "", phone: str = "") -> None:
        await self._client.add_contact(user_id, first_name, last_name, phone)

    async def delete_contacts(self, user_ids: list[int]) -> None:
        await self._client.delete_contacts(user_ids)

    async def get_blocked_users(self, limit: int = 100) -> list[int]:
        """Returns list of blocked peer IDs."""
        return await self._client.get_blocked_users(limit)

    async def get_common_chats(self, user_id: int, limit: int = 100) -> list[Chat]:
        return await self._client.get_common_chats(user_id, limit)


    async def get_authorizations(self) -> list[Authorization]:
        return await self._client.get_authorizations()

    async def terminate_session(self, hash: int) -> None:
        await self._client.terminate_session(hash)


    async def get_scheduled_messages(self, peer: str) -> list[Message]:
        return await self._client.get_scheduled_messages(peer)

    async def get_pinned_message(self, peer: str) -> Message | None:
        return await self._client.get_pinned_message(peer)

    async def translate_messages(self, peer: str, msg_ids: list[int], to_lang: str) -> list[str]:
        return await self._client.translate_messages(peer, msg_ids, to_lang)

    async def get_reply_to_message(self, peer: str, msg_id: int) -> Message | None:
        return await self._client.get_reply_to_message(peer, msg_id)

    async def get_discussion_message(self, peer: str, msg_id: int) -> tuple[list[Message], int, int, int]:
        """Returns (messages, unread_count, max_id, read_max_id)"""
        return await self._client.get_discussion_message(peer, msg_id)


    async def save_draft(self, peer: str, text: str) -> None:
        await self._client.save_draft(peer, text)

    async def clear_all_drafts(self) -> None:
        await self._client.clear_all_drafts()


    async def send_poll(
        self,
        peer: str,
        question: str,
        answers: list[str],
        *,
        quiz: bool = False,
        correct_index: int | None = None,
        multiple_choice: bool = False,
    ) -> None:
        await self._client.send_poll(peer, question, answers, quiz, correct_index, multiple_choice)

    async def send_vote(self, peer: str, msg_id: int, options: list[bytes]) -> None:
        """options: list of raw option bytes from the poll answer (e.g. [b'\\x00'])"""
        await self._client.send_vote(peer, msg_id, options)

    async def get_poll_votes(self, peer: str, msg_id: int, limit: int = 100) -> list[tuple[int, bytes]]:
        """Returns list of (user_id, option_bytes)."""
        return await self._client.get_poll_votes(peer, msg_id, limit)

    async def get_poll_results(self, peer: str, msg_id: int, poll_hash: int) -> None:
        """Fetch and cache the latest poll results from Telegram."""
        await self._client.get_poll_results(peer, msg_id, poll_hash)

    async def read_reactions(self, peer: str) -> None:
        await self._client.read_reactions(peer)

    async def clear_recent_reactions(self) -> None:
        await self._client.clear_recent_reactions()

    async def get_reaction_list(self, peer: str, msg_id: int, limit: int = 100) -> list[tuple[int, str]]:
        """Returns list of (peer_id, reaction) pairs."""
        return await self._client.get_reaction_list(peer, msg_id, limit)

    async def delete_reaction(self, peer: str, msg_id: int, participant: str) -> None:
        """Remove a specific user's reaction from a message. Admin only."""
        await self._client.delete_reaction(peer, msg_id, participant)


    async def set_bot_commands(self, commands: list[tuple[str, str]], lang_code: str = "") -> None:
        """commands: list of (command, description) pairs"""
        await self._client.set_bot_commands(commands, lang_code)

    async def delete_bot_commands(self, lang_code: str = "") -> None:
        await self._client.delete_bot_commands(lang_code)

    async def set_bot_info(
        self,
        name: str | None = None,
        about: str | None = None,
        description: str | None = None,
        lang_code: str = "",
    ) -> None:
        await self._client.set_bot_info(name, about, description, lang_code)

    async def get_bot_info(self, lang_code: str = "") -> BotInfo:
        return await self._client.get_bot_info(lang_code)

    async def answer_callback_query(self, query_id: int, text: str | None = None, alert: bool = False) -> None:
        await self._client.answer_callback_query(query_id, text, alert)


    async def answer_inline_query(
        self,
        query_id: int,
        results: "list[InlineArticle | InlinePhoto | InlineDocument | tuple]",
        cache_time: int = 300,
        is_personal: bool = False,
        next_offset: str | None = None,
        switch_pm: "tuple[str, str] | None" = None,
    ) -> None:
        """Answer an inline query. Accepts InlineArticle/InlinePhoto/InlineDocument or raw tuples."""
        raw = [_inline_result_to_tuple(r) for r in results]
        await self._client.answer_inline_query(
            query_id, raw, cache_time, is_personal, next_offset, switch_pm, None
        )

    async def answer_inline_query_articles(
        self,
        query_id: int,
        articles: "list[tuple[str, str, str]]",
        cache_time: int = 300,
        is_personal: bool = False,
        next_offset: str | None = None,
    ) -> None:
        await self._client.answer_inline_query_articles(
            query_id, articles, cache_time, is_personal, next_offset
        )


    async def get_forum_topics(self, peer: str, limit: int = 100) -> list[ForumTopic]:
        return await self._client.get_forum_topics(peer, limit)

    async def create_forum_topic(
        self,
        peer: str,
        title: str,
        icon_color: int | None = None,
        icon_emoji_id: int | None = None,
    ) -> None:
        await self._client.create_forum_topic(peer, title, icon_color, icon_emoji_id)

    async def edit_forum_topic(
        self,
        peer: str,
        topic_id: int,
        title: str | None = None,
        closed: bool | None = None,
        hidden: bool | None = None,
    ) -> None:
        await self._client.edit_forum_topic(peer, topic_id, title, closed, hidden)

    async def delete_forum_topic_history(self, peer: str, top_msg_id: int) -> None:
        await self._client.delete_forum_topic_history(peer, top_msg_id)

    async def toggle_forum(self, peer: str, enabled: bool) -> None:
        await self._client.toggle_forum(peer, enabled)


    async def mute_chat(self, peer: str, mute_until: int) -> None:
        """Mute notifications until unix timestamp. 2**31-1 to mute forever, 0 to unmute."""
        await self._client.mute_chat(peer, mute_until)

    async def unmute_chat(self, peer: str) -> None:
        """Unmute notifications. Alias for mute_chat(peer, 0)."""
        await self._client.mute_chat(peer, 0)

    async def get_notify_settings(self, peer: str) -> NotifySettings:
        return await self._client.get_notify_settings(peer)

    async def update_notify_settings(
        self,
        peer: str,
        mute_until: int | None = None,
        silent: bool | None = None,
        show_previews: bool | None = None,
    ) -> None:
        await self._client.update_notify_settings(peer, mute_until, silent, show_previews)


    async def get_privacy(self, key: "PrivacyKey | str") -> list[str]:
        """Get privacy rules for a setting. Accepts PrivacyKey enum or string."""
        return await self._client.get_privacy(str(key))

    async def set_privacy(self, key: "PrivacyKey | str", rule: "PrivacyRule | str") -> None:
        """Set a privacy rule. Accepts PrivacyKey/PrivacyRule enums or strings."""
        await self._client.set_privacy(str(key), str(rule))


    async def upload_media(self, peer: str, path: str) -> int | None:
        """Upload a file to Telegram servers. Returns document ID for reuse, or None."""
        return await self._client.upload_media(peer, path)

    async def download_media(self, peer: str, msg_id: int, path: str) -> str:
        """Download media from a message to disk. Returns the final path."""
        return await self._client.download_media(peer, msg_id, path)

    async def edit_chat_photo(self, peer: str, path: str) -> None:
        await self._client.edit_chat_photo(peer, path)

    async def delete_profile_photos(self) -> None:
        await self._client.delete_profile_photos()


    async def edit_inline_message(
        self,
        msg_id: "InlineMessageId | tuple[int, bytes]",
        new_text: str,
        reply_markup=None,
    ) -> bool:
        """Edit an inline bot message. Accepts InlineMessageId or (dc_id, id_bytes) tuple."""
        if isinstance(msg_id, InlineMessageId):
            dc_id, id_bytes = msg_id.dc_id, msg_id.id_bytes
        else:
            dc_id, id_bytes = msg_id
        return await self._client.edit_inline_message(dc_id, list(id_bytes), new_text, reply_markup)


    async def edit_chat_default_banned_rights(self, peer: str, restrictions: dict[str, bool]) -> None:
        """restrictions keys: send_messages, send_media, send_stickers, send_gifs,
        send_games, send_inline, embed_links, send_polls, change_info, invite_users, pin_messages.
        True = allowed, False = restricted."""
        await self._client.edit_chat_default_banned_rights(peer, restrictions)

    async def set_chat_reactions(self, peer: str, reactions: str) -> None:
        """reactions: 'all' | 'none' | comma-separated emoji e.g. '👍,👎,❤'"""
        await self._client.set_chat_reactions(peer, reactions)

    async def transfer_chat_ownership(self, peer: str, new_owner_id: int) -> None:
        """Transfer ownership. Account must NOT have 2FA enabled for this to work."""
        await self._client.transfer_chat_ownership(peer, new_owner_id)


    async def get_broadcast_stats(self, peer: str, dark: bool = False) -> BroadcastStats:
        return await self._client.get_broadcast_stats(peer, dark)

    async def get_megagroup_stats(self, peer: str, dark: bool = False) -> MegagroupStats:
        return await self._client.get_megagroup_stats(peer, dark)


    async def get_chat_full(self, peer: str) -> tuple[int, str, int | None]:
        """Returns (id, about, members_count)."""
        return await self._client.get_chat_full_raw(peer)

    async def get_admins_with_invites(self, peer: str) -> list[tuple[int, int]]:
        """Returns list of (admin_id, invite_count)."""
        return await self._client.get_admins_with_invites(peer)

    async def get_pinned_dialogs(self, folder_id: int = 0) -> list[int]:
        """Returns list of peer IDs. folder_id=0=main, 1=archive."""
        return await self._client.get_pinned_dialogs(folder_id)

    async def get_custom_emoji_documents(self, document_ids: list[int]) -> list[int]:
        """Returns document IDs that resolved successfully."""
        return await self._client.get_custom_emoji_documents(document_ids)

    async def get_game_high_scores(self, peer: str, msg_id: int, user_id: int) -> list[tuple[int, int, int]]:
        """Returns list of (position, user_id, score)."""
        return await self._client.get_game_high_scores(peer, msg_id, user_id)

    async def get_web_page_preview(self, text: str) -> str | None:
        """Returns the webpage URL if a preview exists, else None."""
        return await self._client.get_web_page_preview(text)

    async def send_invoice(
        self,
        peer: str,
        title: str,
        description: str,
        payload: str,
        currency: str,
        prices: list[tuple[str, int]],
        photo_url: str | None = None,
        need_name: bool = False,
        need_phone: bool = False,
        need_email: bool = False,
        need_shipping_address: bool = False,
        is_flexible: bool = False,
    ) -> Message:
        """prices: list of (label, amount_in_smallest_currency_unit)"""
        return await self._client.send_invoice(
            peer, title, description, payload, currency, prices,
            photo_url, need_name, need_phone, need_email, need_shipping_address, is_flexible,
        )


    async def set_profile(self, first_name: str | None = None, last_name: str | None = None, about: str | None = None) -> None:
        await self._client.set_profile(first_name, last_name, about)

    async def set_username(self, username: str) -> None:
        await self._client.set_username(username)

    async def set_online(self) -> None:
        await self._client.set_online()

    async def set_offline(self) -> None:
        await self._client.set_offline()

    async def mark_dialog_read(self, peer: str) -> None:
        await self._client.mark_dialog_read(peer)

    async def sync_drafts(self) -> None:
        """Push all drafts as update events (0.3.6 name for get_all_drafts)."""
        await self._client.sync_drafts()

    async def get_message_history(self, peer: str, limit: int = 100, offset_id: int = 0) -> list[Message]:
        """Stable public name for get_history."""
        return await self._client.get_message_history(peer, limit, offset_id)

    async def join_request(self, peer: str, user_id: int, approve: bool) -> None:
        """Approve or reject a join request. Replaces approve_join_request / reject_join_request."""
        await self._client.join_request(peer, user_id, approve)

    async def all_join_requests(self, peer: str, approve: bool, link: str | None = None) -> None:
        """Bulk approve/reject. Replaces approve_all_join_requests / reject_all_join_requests."""
        await self._client.all_join_requests(peer, approve, link)

    async def open_mini_app(self, peer: str, app_type: str = "main", app_value: str = "") -> MiniAppSession:
        """Open a bot mini-app. app_type: main|url|simple. Returns MiniAppSession."""
        return await self._client.open_mini_app(peer, app_type, app_value)

    async def warm_peer_cache_from_dialogs(self) -> None:
        """Warm the Rust peer cache via GetDialogs. Call once on fresh sessions when integer peer resolution is needed before any update arrives."""
        await self._raw.warm_peer_cache_from_dialogs()

    async def resolve_peer(self, peer: str) -> int:
        """Resolve username/@handle/id string → peer ID."""
        return await self._client.resolve_peer(peer)

    async def resolve_username(self, username: str) -> int:
        """Resolve a username (with or without @) → peer ID."""
        return await self._client.resolve_username(username)

    async def export_login_token(self) -> tuple[bytes, int]:
        """QR login step 1. Returns (token_bytes, expires_unix). Show token as QR."""
        token, expires = await self._client.export_login_token()
        return bytes(token), expires

    async def check_qr_login(self, token: bytes) -> str | None:
        """QR login step 2. Returns username if scanned, None if still pending."""
        return await self._client.check_qr_login(list(token))

    async def is_authorized(self) -> bool:
        """Return True if the current session is authenticated."""
        return await self._client.is_authorized()

    async def login_bot(self, token: str) -> None:
        """Sign in as a bot after start(). Saves session on success."""
        await self._client.bot_sign_in(token)
        await self._client.save_session()


    async def _resolve_peer(self, peer: Any) -> dict:
        """Resolve any peer representation to a TL InputPeer dict."""
        return await _resolve_peer_fn(self, peer)

    def _populate_cache(self, obj: Any) -> None:
        """Scan a deserialized TL response and store user/channel access_hashes.

        Called automatically by invoke() so the PeerCache stays warm.
        Min-flagged entries are skipped (access_hash invalid outside message context).
        """
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


    async def invite_links(
        self,
        peer: str,
        *,
        primary_only: bool = False,
        revoked: bool = False,
        limit: int = 100,
    ):
        """Return invite links for a chat.

        primary_only=True: export/get the permanent primary link (single object).
        primary_only=False: return all links created by the current admin (list).
        """
        if primary_only:
            return await self._client.export_invite_link(peer, None, None, False, None)
        me = await self._client.get_me()
        return await self._client.get_invite_links(peer, me.id, revoked, limit, None, None)

    async def iter_invite_links(self, peer: str, *, revoked: bool = False):
        """Async generator over all invite links created by the current admin."""
        me = await self._client.get_me()
        offset_date: int | None = None
        offset_link: str | None = None
        batch = 100
        while True:
            links = await self._client.get_invite_links(
                peer, me.id, revoked, batch, offset_date, offset_link
            )
            if not links:
                return
            for link in links:
                yield link
            if len(links) < batch:
                return
            last = links[-1]
            offset_date = getattr(last, "date", None)
            offset_link = getattr(last, "link", None)
            if not offset_link:
                return

    async def iter_invite_link_members(self, peer: str, link: str, *, requested: bool = False):
        """Async generator over users who joined via an invite link."""
        offset_date = 0
        offset_user_id = 0
        batch = 100
        while True:
            members = await self._client.get_invite_link_members(
                peer, link, requested, batch, offset_date, offset_user_id
            )
            if not members:
                return
            for m in members:
                yield m
            if len(members) < batch:
                return
            last = members[-1]
            offset_date = getattr(last, "date", 0)
            offset_user_id = getattr(last, "user_id", 0)

    async def edit_invite_link(
        self,
        peer: str,
        link: str,
        *,
        expire_date: int | None = None,
        usage_limit: int | None = None,
        request_needed: bool | None = None,
        title: str | None = None,
    ):
        """Edit an existing invite link. Returns the updated link object."""
        return await self._client.edit_invite_link(
            peer, link, expire_date, usage_limit, request_needed, title
        )

    async def revoke_invite_link(self, peer: str, link: str):
        """Revoke an invite link. Returns the revoked link object."""
        return await self._client.revoke_invite_link(peer, link)

    async def delete_invite_link(self, peer: str, link: str) -> None:
        """Permanently delete a (previously revoked) invite link."""
        await self._client.delete_invite_link(peer, link)

    async def clear_revoked_invite_links(self, peer: str) -> None:
        """Delete all revoked invite links created by the current admin."""
        me = await self._client.get_me()
        await self._client.delete_revoked_invite_links(peer, me.id)

    async def resolve_invite_link(self, link: str):
        """Peek at an invite link without joining. Returns chat info."""
        return await self._client.check_invite(link)

    async def join_invite_link(self, link: str):
        """Join a chat by invite link. Returns the InputPeer of the joined chat."""
        return await self._client.join_by_invite(link)


    async def invoke(self, func: Any) -> dict:
        """Invoke a raw TL function object. Returns a deserialized dict."""
        tl_bytes   = func.to_bytes() if hasattr(func, "to_bytes") else _tl.serialize_object(func.to_dict(), _SCHEMA)
        resp_bytes = await self._client.invoke_raw(tl_bytes)
        result     = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
        self._populate_cache(result)
        return result

    async def __call__(self, func: Any) -> dict:
        """Callable shorthand for invoke()."""
        return await self.invoke(func)

    def __repr__(self) -> str:
        state = "connected" if self._raw else "disconnected"
        return f"Client(session={self.session!r}, {state})"
