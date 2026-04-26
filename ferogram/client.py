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

from ._ferogram import Client as _RustClient, PasswordToken, User, Dialog
from ._ferogram import Message, CallbackQuery
from ._ferogram import (
    MessageDeletion, InlineQuery, InlineSend, UserStatus,
    ChatAction, ParticipantUpdate, JoinRequest, MessageReaction,
    PollVote, BotStopped, RawUpdate,
)
from .raw import _tl
from .raw.generated._tl_schema import _SCHEMA_BY_CID

__all__ = ["Client"]

_log = logging.getLogger("ferogram")

_Handler = tuple[Callable, list[Callable]]  # (func, filters)

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
)


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
    ) -> None:
        self.session   = session
        self.api_id    = api_id or int(os.environ.get("API_ID", 0)) or None
        self.api_hash  = api_hash or os.environ.get("API_HASH")
        self.bot_token = bot_token or os.environ.get("BOT_TOKEN")
        self._phone    = phone
        self._password = password
        self._raw: _RustClient | None = None

        self._handlers: dict[str, list[_Handler]] = {e: [] for e in _ALL_EVENTS}

    def _require_creds(self) -> tuple[int, str]:
        if not self.api_id or not self.api_hash:
            raise ValueError("api_id and api_hash required.")
        return self.api_id, self.api_hash

    @property
    def _client(self) -> _RustClient:
        if self._raw is None:
            raise RuntimeError("Call await app.start() first.")
        return self._raw

    # handler decorators

    def on_message(self, *filters: Callable) -> Callable:
        """Decorator: handle incoming messages."""
        def decorator(func: Callable) -> Callable:
            self._handlers["message"].append((func, list(filters)))
            return func
        return decorator

    def on_edited_message(self, *filters: Callable) -> Callable:
        """Decorator: handle edited messages."""
        def decorator(func: Callable) -> Callable:
            self._handlers["edited_message"].append((func, list(filters)))
            return func
        return decorator

    def on_message_deleted(self, *filters: Callable) -> Callable:
        """Decorator: handle message deletions."""
        def decorator(func: Callable) -> Callable:
            self._handlers["message_deleted"].append((func, list(filters)))
            return func
        return decorator

    def on_callback_query(self, *filters: Callable) -> Callable:
        """Decorator: handle inline button presses."""
        def decorator(func: Callable) -> Callable:
            self._handlers["callback_query"].append((func, list(filters)))
            return func
        return decorator

    def on_inline_query(self, *filters: Callable) -> Callable:
        """Decorator: handle @bot inline queries (bots only)."""
        def decorator(func: Callable) -> Callable:
            self._handlers["inline_query"].append((func, list(filters)))
            return func
        return decorator

    def on_inline_send(self, *filters: Callable) -> Callable:
        """Decorator: user chose an inline result (bots only)."""
        def decorator(func: Callable) -> Callable:
            self._handlers["inline_send"].append((func, list(filters)))
            return func
        return decorator

    def on_user_status(self, *filters: Callable) -> Callable:
        """Decorator: user came online or went offline."""
        def decorator(func: Callable) -> Callable:
            self._handlers["user_status"].append((func, list(filters)))
            return func
        return decorator

    def on_chat_action(self, *filters: Callable) -> Callable:
        """Decorator: user is typing / uploading / recording."""
        def decorator(func: Callable) -> Callable:
            self._handlers["chat_action"].append((func, list(filters)))
            return func
        return decorator

    def on_participant_update(self, *filters: Callable) -> Callable:
        """Decorator: member joined, left, was promoted, banned, etc."""
        def decorator(func: Callable) -> Callable:
            self._handlers["participant_update"].append((func, list(filters)))
            return func
        return decorator

    def on_join_request(self, *filters: Callable) -> Callable:
        """Decorator: user requested to join via invite link (bots only)."""
        def decorator(func: Callable) -> Callable:
            self._handlers["join_request"].append((func, list(filters)))
            return func
        return decorator

    def on_message_reaction(self, *filters: Callable) -> Callable:
        """Decorator: reaction added/removed on a bot message (bots only)."""
        def decorator(func: Callable) -> Callable:
            self._handlers["message_reaction"].append((func, list(filters)))
            return func
        return decorator

    def on_poll_vote(self, *filters: Callable) -> Callable:
        """Decorator: user voted in a poll sent by the bot (bots only)."""
        def decorator(func: Callable) -> Callable:
            self._handlers["poll_vote"].append((func, list(filters)))
            return func
        return decorator

    def on_bot_stopped(self, *filters: Callable) -> Callable:
        """Decorator: user stopped or restarted the bot."""
        def decorator(func: Callable) -> Callable:
            self._handlers["bot_stopped"].append((func, list(filters)))
            return func
        return decorator

    def on_raw_update(self, *filters: Callable) -> Callable:
        """Decorator: receive RawUpdate for any TL update not mapped to a typed event.

        Useful for handling obscure update types not yet covered by dedicated
        handlers. The update object has .constructor_id (u32) and .type_name (str).
        """
        def decorator(func: Callable) -> Callable:
            self._handlers["raw_update"].append((func, list(filters)))
            return func
        return decorator

    # dispatch

    async def _dispatch(self, event_type: str, update: Any) -> None:
        for func, fltrs in self._handlers.get(event_type, []):
            if all(f(update) for f in fltrs):
                try:
                    result = func(self, update)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    _log.error("handler error in %s: %s", event_type, exc, exc_info=True)

    # update loop

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

    # lifecycle

    async def start(self) -> "Client":
        if self._raw is not None:
            return self
        api_id, api_hash = self._require_creds()
        _log.info("connecting (session=%r)", self.session + (".session" if not self.session.endswith(".session") else ""))
        session_path = self.session if self.session.endswith(".session") else self.session + ".session"
        self._raw = await _RustClient.builder(api_id, api_hash, session_path).connect()
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
        phone   = self._phone or input("Phone (+countrycode): ")
        token   = await self._client.request_login_code(phone)
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
        """Blocking run: start, dispatch updates, stop on Ctrl-C."""
        try:
            asyncio.run(self.run_until_disconnected())
        except KeyboardInterrupt:
            pass

    async def __aenter__(self) -> "Client":
        return await self.start()

    async def __aexit__(self, *_: Any) -> None:
        pass

    # messaging

    async def send_message(self, peer: str, text: str) -> Message:
        return await self._client.send_message(peer, text)

    async def send_html(self, peer: str, html: str) -> Message:
        return await self._client.send_html(peer, html)

    async def send_markdown(self, peer: str, md: str) -> Message:
        return await self._client.send_markdown(peer, md)

    async def edit_message(self, peer: str, message_id: int, new_text: str) -> None:
        await self._client.edit_message(peer, message_id, new_text)

    async def delete_message(self, message_id: int, revoke: bool = True) -> None:
        await self._client.delete_messages([message_id], revoke)

    async def delete_messages(self, message_ids: list[int], revoke: bool = True) -> None:
        await self._client.delete_messages(message_ids, revoke)

    async def forward_messages(self, destination: str, source: str, message_ids: list[int]) -> None:
        await self._client.forward_messages(destination, source, message_ids)

    async def pin_message(self, peer: str, message_id: int) -> None:
        await self._client.pin_message(peer, message_id)

    async def unpin_message(self, peer: str, message_id: int) -> None:
        await self._client.unpin_message(peer, message_id)

    async def mark_as_read(self, peer: str) -> None:
        await self._client.mark_as_read(peer)

    async def send_reaction(self, peer: str, message_id: int, emoji: str) -> None:
        """Send a reaction emoji to a message."""
        await self._client.send_reaction(peer, message_id, emoji)

    # media

    async def send_photo(self, peer: str, path: str, caption: str = "") -> Message:
        import os
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_photo(peer, path, caption)

    async def send_document(self, peer: str, path: str, caption: str = "", mime_type: str | None = None) -> Message:
        import os
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_document(peer, path, caption, mime_type)

    async def send_file(self, peer: str, path: str, caption: str = "", mime_type: str | None = None) -> Message:
        import os
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self._client.send_file(peer, path, caption, mime_type)

    # account

    async def get_me(self) -> User:
        return await self._client.get_me()

    async def get_dialogs(self, limit: int = 100) -> list[Dialog]:
        return await self._client.get_dialogs(limit)

    async def export_session_string(self) -> str:
        return await self._client.export_session_string()

    # raw invoke

    async def invoke(self, func: Any) -> dict:
        """Invoke a raw TL function object. Returns a deserialized dict."""
        tl_bytes  = func.to_bytes()
        resp_bytes = await self._client.invoke_raw(tl_bytes)
        return _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)

    def __repr__(self) -> str:
        state = "connected" if self._raw else "disconnected"
        return f"Client(session={self.session!r}, {state})"
