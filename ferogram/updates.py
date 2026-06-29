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

from dataclasses import dataclass, field
from typing import Any

from .types import Message, _peer_to_id, _int, _str, _bool

__all__ = [
    "NewMessage", "EditedMessage", "MessageDeletion",
    "CallbackQuery", "InlineQuery", "InlineSend",
    "UserStatus", "ChatAction", "ParticipantUpdate",
    "JoinRequest", "MessageReaction", "PollVote",
    "BotStopped", "ShippingQuery", "PreCheckoutQuery",
    "ChatBoost", "RawUpdate",
]


@dataclass
class NewMessage:
    message: Message
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "NewMessage":
        msg_tl = d.get("message") or d
        return cls(message=Message.from_tl(msg_tl if isinstance(msg_tl, dict) else d), _raw=d)

    def __repr__(self) -> str:
        return f"NewMessage(id={self.message.id})"


@dataclass
class EditedMessage:
    message: Message
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "EditedMessage":
        msg_tl = d.get("message") or d
        return cls(message=Message.from_tl(msg_tl if isinstance(msg_tl, dict) else d), _raw=d)

    def __repr__(self) -> str:
        return f"EditedMessage(id={self.message.id})"


@dataclass
class MessageDeletion:
    message_ids: list[int]
    channel_id: int | None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "MessageDeletion":
        return cls(
            message_ids=d.get("messages") or [],
            channel_id=d.get("channel_id"),
            _raw=d,
        )

    def __repr__(self) -> str:
        return f"MessageDeletion(ids={self.message_ids})"


@dataclass
class CallbackQuery:
    query_id: int
    sender_id: int
    peer: dict
    message_id: int
    chat_instance: int
    data: bytes
    game_short_name: str
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "CallbackQuery":
        return cls(
            query_id=_int(d, "query_id"),
            sender_id=_int(d, "user_id"),
            peer=d.get("peer") or {},
            message_id=_int(d, "msg_id"),
            chat_instance=_int(d, "chat_instance"),
            data=d.get("data") or b"",
            game_short_name=_str(d, "game_short_name"),
            _raw=d,
        )

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError(
                "This CallbackQuery isn't bound to a client. "
                "Methods only work on queries received from a dispatcher handler."
            )
        return self._client

    @property
    def chat_id(self) -> int:
        return _peer_to_id(self.peer) or self.sender_id

    async def answer(self, text: str | None = None, *, alert: bool = False) -> None:
        await self._require_client().answer_callback_query(self.query_id, text=text, alert=alert)

    async def respond(self, text: str, *, parse_mode: str | None = None,
                      reply_markup: Any = None) -> Message:
        """Send a new message to the chat this button came from."""
        return await self._require_client().send_message(
            self.chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup,
        )

    async def reply(self, text: str, *, parse_mode: str | None = None,
                    reply_markup: Any = None) -> Message:
        """Send a message quoting the original button message."""
        return await self._require_client().send_message(
            self.chat_id, text, reply_to=self.message_id,
            parse_mode=parse_mode, reply_markup=reply_markup,
        )

    async def edit_message_text(self, new_text: str, *,
                                parse_mode: str | None = None,
                                reply_markup: Any = None) -> None:
        """Edit the message that contained the inline button."""
        client = self._require_client()
        await client.edit_message(
            self.chat_id, self.message_id, new_text,
            parse_mode=parse_mode, reply_markup=reply_markup,
        )

    async def get_sender(self) -> Any:
        return await self._require_client().get_user(self.sender_id)

    def __repr__(self) -> str:
        return f"CallbackQuery(id={self.query_id}, data={self.data!r})"


@dataclass
class InlineQuery:
    query_id: int
    sender_id: int
    query: str
    offset: str
    peer_type: dict | None
    geo: dict | None
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "InlineQuery":
        return cls(
            query_id=_int(d, "query_id"),
            sender_id=_int(d, "user_id"),
            query=_str(d, "query"),
            offset=_str(d, "offset"),
            peer_type=d.get("peer_type"),
            geo=d.get("geo"),
            _raw=d,
        )

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError(
                "This InlineQuery isn't bound to a client. "
                "Methods only work on queries received from a dispatcher handler."
            )
        return self._client

    async def answer(self, results: list, *, cache_time: int = 300,
                     is_personal: bool = False, next_offset: str | None = None,
                     switch_pm: "tuple[str, str] | None" = None) -> None:
        await self._require_client().answer_inline_query(
            self.query_id, results, cache_time=cache_time,
            is_personal=is_personal, next_offset=next_offset, switch_pm=switch_pm,
        )

    async def get_sender(self) -> Any:
        return await self._require_client().get_user(self.sender_id)

    def __repr__(self) -> str:
        return f"InlineQuery(id={self.query_id}, query={self.query!r})"


@dataclass
class InlineSend:
    query_id: str
    sender_id: int
    result_id: str
    inline_message_id: dict | None
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "InlineSend":
        return cls(
            query_id=_str(d, "query_id"),
            sender_id=_int(d, "user_id"),
            result_id=_str(d, "id"),
            inline_message_id=d.get("msg_id"),
            _raw=d,
        )

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError(
                "This InlineSend isn't bound to a client. "
                "Methods only work on events received from a dispatcher handler."
            )
        return self._client

    async def get_sender(self) -> Any:
        return await self._require_client().get_user(self.sender_id)


@dataclass
class UserStatus:
    user_id: int
    status: dict
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "UserStatus":
        return cls(user_id=_int(d, "user_id"), status=d.get("status") or {}, _raw=d)

    @property
    def online(self) -> bool:
        return (self.status.get("_") or "") == "userStatusOnline"

    async def get_sender(self) -> Any:
        if self._client is None:
            raise RuntimeError("UserStatus isn't bound to a client.")
        return await self._client.get_user(self.user_id)

    def __repr__(self) -> str:
        return f"UserStatus(user_id={self.user_id}, online={self.online})"


@dataclass
class ChatAction:
    peer_id: int | None
    from_id: int | None
    action: dict
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "ChatAction":
        return cls(
            peer_id=d.get("chat_id") or d.get("channel_id"),
            from_id=_peer_to_id(d.get("from_id")),
            action=d.get("action") or {},
            _raw=d,
        )

    async def get_sender(self) -> Any:
        if self._client is None:
            raise RuntimeError("ChatAction isn't bound to a client.")
        if self.from_id is None:
            return None
        return await self._client.get_user(self.from_id)

    def __repr__(self) -> str:
        return f"ChatAction(action={self.action.get('_')})"


@dataclass
class ParticipantUpdate:
    channel_id: int
    actor_id: int
    user_id: int
    date: int
    prev_participant: dict | None
    new_participant: dict | None
    invite: dict | None
    via_chatlist: bool
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "ParticipantUpdate":
        return cls(
            channel_id=_int(d, "channel_id"),
            actor_id=_int(d, "actor_id"),
            user_id=_int(d, "user_id"),
            date=_int(d, "date"),
            prev_participant=d.get("prev_participant"),
            new_participant=d.get("new_participant"),
            invite=d.get("invite"),
            via_chatlist=_bool(d, "via_chatlist"),
            _raw=d,
        )

    async def get_user(self) -> Any:
        if self._client is None:
            raise RuntimeError("ParticipantUpdate isn't bound to a client.")
        return await self._client.get_user(self.user_id)

    async def get_actor(self) -> Any:
        if self._client is None:
            raise RuntimeError("ParticipantUpdate isn't bound to a client.")
        return await self._client.get_user(self.actor_id)

    def __repr__(self) -> str:
        return f"ParticipantUpdate(channel={self.channel_id}, user={self.user_id})"


@dataclass
class JoinRequest:
    channel_id: int | None
    user_id: int
    date: int
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "JoinRequest":
        return cls(
            channel_id=d.get("channel_id"),
            user_id=_int(d, "user_id"),
            date=_int(d, "date"),
            _raw=d,
        )

    async def get_sender(self) -> Any:
        if self._client is None:
            raise RuntimeError("JoinRequest isn't bound to a client.")
        return await self._client.get_user(self.user_id)

    def __repr__(self) -> str:
        return f"JoinRequest(channel={self.channel_id}, user={self.user_id})"


@dataclass
class MessageReaction:
    peer: dict
    msg_id: int
    reactions: dict
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "MessageReaction":
        return cls(
            peer=d.get("peer") or {},
            msg_id=_int(d, "msg_id"),
            reactions=d.get("reactions") or {},
            _raw=d,
        )

    @property
    def chat_id(self) -> int:
        return _peer_to_id(self.peer) or 0

    async def get_message(self) -> Message | None:
        if self._client is None:
            raise RuntimeError("MessageReaction isn't bound to a client.")
        raw = await self._client.get_message(self.chat_id, self.msg_id)
        if raw is None:
            return None
        msg = Message.from_tl(raw)
        msg._client = self._client
        return msg

    def __repr__(self) -> str:
        return f"MessageReaction(msg_id={self.msg_id})"


@dataclass
class PollVote:
    poll_id: int
    peer: dict | None
    options: list[bytes]
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "PollVote":
        return cls(
            poll_id=_int(d, "poll_id"),
            peer=d.get("peer"),
            options=[],
            _raw=d,
        )

    def __repr__(self) -> str:
        return f"PollVote(poll_id={self.poll_id})"


@dataclass
class BotStopped:
    user_id: int
    date: int
    stopped: bool
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "BotStopped":
        return cls(user_id=_int(d, "user_id"), date=_int(d, "date"), stopped=_bool(d, "stopped"), _raw=d)

    async def get_sender(self) -> Any:
        if self._client is None:
            raise RuntimeError("BotStopped isn't bound to a client.")
        return await self._client.get_user(self.user_id)

    def __repr__(self) -> str:
        return f"BotStopped(user_id={self.user_id}, stopped={self.stopped})"


@dataclass
class ShippingQuery:
    query_id: int
    user_id: int
    payload: bytes
    shipping_address: dict
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "ShippingQuery":
        return cls(
            query_id=_int(d, "query_id"),
            user_id=_int(d, "user_id"),
            payload=d.get("payload") or b"",
            shipping_address=d.get("shipping_address") or {},
            _raw=d,
        )

    async def get_sender(self) -> Any:
        if self._client is None:
            raise RuntimeError("ShippingQuery isn't bound to a client.")
        return await self._client.get_user(self.user_id)

    def __repr__(self) -> str:
        return f"ShippingQuery(id={self.query_id})"


@dataclass
class PreCheckoutQuery:
    query_id: int
    user_id: int
    currency: str
    total_amount: int
    payload: bytes
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "PreCheckoutQuery":
        return cls(
            query_id=_int(d, "query_id"),
            user_id=_int(d, "user_id"),
            currency=_str(d, "currency"),
            total_amount=_int(d, "total_amount"),
            payload=d.get("payload") or b"",
            _raw=d,
        )

    async def get_sender(self) -> Any:
        if self._client is None:
            raise RuntimeError("PreCheckoutQuery isn't bound to a client.")
        return await self._client.get_user(self.user_id)

    def __repr__(self) -> str:
        return f"PreCheckoutQuery(id={self.query_id}, amount={self.total_amount})"


@dataclass
class ChatBoost:
    peer: dict
    boost: dict
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "ChatBoost":
        return cls(peer=d.get("peer") or {}, boost=d.get("boost") or {}, _raw=d)

    @property
    def chat_id(self) -> int:
        return _peer_to_id(self.peer) or 0

    def __repr__(self) -> str:
        return f"ChatBoost(peer={self.peer})"


@dataclass
class RawUpdate:
    type: str
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "RawUpdate":
        return cls(type=d.get("_", ""), _raw=d)

    def __repr__(self) -> str:
        return f"RawUpdate(type={self.type!r})"


_UPDATE_FACTORIES: dict[str, type] = {
    "message":              NewMessage,
    "edited_message":       EditedMessage,
    "message_deleted":      MessageDeletion,
    "callback_query":       CallbackQuery,
    "inline_query":         InlineQuery,
    "inline_send":          InlineSend,
    "user_status":          UserStatus,
    "chat_action":          ChatAction,
    "participant_update":   ParticipantUpdate,
    "join_request":         JoinRequest,
    "message_reaction":     MessageReaction,
    "poll_vote":            PollVote,
    "bot_stopped":          BotStopped,
    "shipping_query":       ShippingQuery,
    "pre_checkout_query":   PreCheckoutQuery,
    "chat_boost":           ChatBoost,
    "raw_update":           RawUpdate,
}


def wrap_update(event_type: str, raw: dict) -> Any:
    """Convert a raw TL dict to the appropriate update dataclass."""
    factory = _UPDATE_FACTORIES.get(event_type)
    if factory is None:
        return RawUpdate.from_tl(raw)
    return factory.from_tl(raw)
