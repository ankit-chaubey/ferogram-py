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
from enum import Enum
from typing import Any

__all__ = [
    "ChatAction", "PrivacyKey", "PrivacyRule",
    "InlineMessageId", "InlineArticle", "InlinePhoto", "InlineDocument",
    "User", "UserFull", "Chat", "Message", "Dialog", "ChatMember",
    "Authorization", "ForumTopic", "BotInfo",
    "InviteLinkMember", "ReadParticipant", "AdminLogEvent", "StickerSetInfo",
    "BroadcastStats", "MegagroupStats", "NotifySettings",
]


def _peer_to_id(peer: Any) -> int | None:
    if peer is None:
        return None
    if isinstance(peer, dict):
        t = peer.get("_", "")
        if t == "peerUser" or "user_id" in peer:
            uid = peer.get("user_id")
            return uid if uid else None
        if t == "peerChannel" or "channel_id" in peer:
            cid = peer.get("channel_id")
            return -(1_000_000_000 + cid) if cid else None
        if t == "peerChat" or "chat_id" in peer:
            cid = peer.get("chat_id")
            return -cid if cid else None
    return None


def _int(d: dict, key: str, default: int = 0) -> int:
    return int(d.get(key) or default)


def _str(d: dict, key: str, default: str = "") -> str:
    return str(d.get(key) or default)


def _bool(d: dict, key: str) -> bool:
    return bool(d.get(key))


class ChatAction(str, Enum):
    TYPING          = "typing"
    UPLOAD_PHOTO    = "upload_photo"
    RECORD_VIDEO    = "record_video"
    UPLOAD_VIDEO    = "upload_video"
    RECORD_AUDIO    = "record_audio"
    UPLOAD_AUDIO    = "upload_audio"
    UPLOAD_DOCUMENT = "upload_document"
    CHOOSE_STICKER  = "choose_sticker"
    RECORD_ROUND    = "record_round"
    UPLOAD_ROUND    = "upload_round"
    CANCEL          = "cancel"


class PrivacyKey(str, Enum):
    STATUS_TIMESTAMP = "status_timestamp"
    CHAT_INVITE      = "chat_invite"
    CALL             = "call"
    FORWARDS         = "forwards"
    PROFILE_PHOTO    = "profile_photo"
    PHONE_NUMBER     = "phone_number"
    VOICE_MESSAGES   = "voice_messages"
    BIO              = "bio"
    BIRTHDAY         = "birthday"


class PrivacyRule(str, Enum):
    ALLOW_ALL         = "allow_all"
    ALLOW_CONTACTS    = "allow_contacts"
    DISALLOW_ALL      = "disallow_all"
    DISALLOW_CONTACTS = "disallow_contacts"


@dataclass
class InlineMessageId:
    dc_id: int
    id_bytes: bytes

    def __repr__(self) -> str:
        return f"InlineMessageId(dc_id={self.dc_id}, len={len(self.id_bytes)})"


@dataclass
class InlineArticle:
    id: str
    title: str
    message_text: str
    description: str | None = None
    url: str | None = None
    thumb_url: str | None = None
    reply_markup: object = None

    def _to_tuple(self) -> tuple:
        return ("article", self.id, self.title, self.message_text,
                self.description, self.url, self.thumb_url,
                None, None, None, None, self.reply_markup)


@dataclass
class InlinePhoto:
    id: str
    title: str
    message_text: str
    photo_url: str
    photo_width: int = 0
    photo_height: int = 0
    description: str | None = None
    thumb_url: str | None = None
    mime_type: str = "image/jpeg"
    reply_markup: object = None

    def _to_tuple(self) -> tuple:
        return ("photo", self.id, self.title, self.message_text,
                self.description, None, self.thumb_url,
                self.photo_url, self.photo_width, self.photo_height,
                self.mime_type, self.reply_markup)


@dataclass
class InlineDocument:
    id: str
    title: str
    message_text: str
    document_url: str
    mime_type: str
    description: str | None = None
    thumb_url: str | None = None
    reply_markup: object = None

    def _to_tuple(self) -> tuple:
        return ("document", self.id, self.title, self.message_text,
                self.description, self.document_url, self.thumb_url,
                None, 0, 0, self.mime_type, self.reply_markup)


def _inline_result_to_tuple(r: object) -> tuple:
    if isinstance(r, (InlineArticle, InlinePhoto, InlineDocument)):
        return r._to_tuple()
    return r  # type: ignore[return-value]


@dataclass
class User:
    id: int
    first_name: str
    last_name: str
    username: str | None
    phone: str | None
    is_bot: bool
    is_verified: bool
    is_restricted: bool
    is_scam: bool
    is_fake: bool
    is_premium: bool
    access_hash: int
    lang_code: str
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "User":
        return cls(
            id=_int(d, "id"),
            first_name=_str(d, "first_name"),
            last_name=_str(d, "last_name"),
            username=d.get("username") or (d.get("usernames") or [{}])[0].get("username"),
            phone=d.get("phone"),
            is_bot=_bool(d, "bot"),
            is_verified=_bool(d, "verified"),
            is_restricted=_bool(d, "restricted"),
            is_scam=_bool(d, "scam"),
            is_fake=_bool(d, "fake"),
            is_premium=_bool(d, "premium"),
            access_hash=_int(d, "access_hash"),
            lang_code=_str(d, "lang_code"),
            _raw=d,
        )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self) -> str:
        return f"User(id={self.id}, name={self.full_name!r})"


@dataclass
class UserFull:
    id: int
    about: str
    common_chats_count: int
    blocked: bool
    phone_calls_available: bool
    video_calls_available: bool
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "UserFull":
        full = d.get("full_user", d)
        return cls(
            id=_int(full, "id"),
            about=_str(full, "about"),
            common_chats_count=_int(full, "common_chats_count"),
            blocked=_bool(full, "blocked"),
            phone_calls_available=_bool(full, "phone_calls_available"),
            video_calls_available=_bool(full, "video_calls_available"),
            _raw=d,
        )


@dataclass
class Chat:
    id: int
    title: str
    username: str | None
    is_channel: bool
    is_megagroup: bool
    is_gigagroup: bool
    is_broadcast: bool
    members_count: int | None
    access_hash: int
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "Chat":
        t = d.get("_", "")
        return cls(
            id=_int(d, "id"),
            title=_str(d, "title"),
            username=d.get("username") or (d.get("usernames") or [{}])[0].get("username"),
            is_channel="channel" in t.lower(),
            is_megagroup=_bool(d, "megagroup"),
            is_gigagroup=_bool(d, "gigagroup"),
            is_broadcast=_bool(d, "broadcast"),
            members_count=d.get("participants_count"),
            access_hash=_int(d, "access_hash"),
            _raw=d,
        )

    def __repr__(self) -> str:
        return f"Chat(id={self.id}, title={self.title!r})"


@dataclass
class Message:
    id: int
    text: str
    sender_id: int | None
    peer_id: dict
    date: int
    edit_date: int | None
    reply_to_msg_id: int | None
    forward_from_id: int | None
    media: dict | None
    entities: list
    views: int | None
    via_bot_id: int | None
    grouped_id: int | None
    out: bool
    mentioned: bool
    silent: bool
    pinned: bool
    _raw: dict = field(default_factory=dict, repr=False)
    _client: Any = field(default=None, repr=False, compare=False)

    @classmethod
    def from_tl(cls, d: dict) -> "Message":
        reply_to = d.get("reply_to") or {}
        fwd = d.get("fwd_from") or {}
        return cls(
            id=_int(d, "id"),
            text=_str(d, "message"),
            sender_id=_peer_to_id(d.get("from_id")),
            peer_id=d.get("peer_id") or {},
            date=_int(d, "date"),
            edit_date=d.get("edit_date"),
            reply_to_msg_id=reply_to.get("reply_to_msg_id") if isinstance(reply_to, dict) else None,
            forward_from_id=_peer_to_id(fwd.get("from_id")) if isinstance(fwd, dict) else None,
            media=d.get("media"),
            entities=d.get("entities") or [],
            views=d.get("views"),
            via_bot_id=d.get("via_bot_id"),
            grouped_id=d.get("grouped_id"),
            out=_bool(d, "out"),
            mentioned=_bool(d, "mentioned"),
            silent=_bool(d, "silent"),
            pinned=_bool(d, "pinned"),
            _raw=d,
        )

    @property
    def chat_id(self) -> int:
        return _peer_to_id(self.peer_id) or 0

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError(
                "This Message isn't bound to a client. "
                "Methods only work on messages received from a dispatcher handler."
            )
        return self._client

    async def respond(self, text: str, *, parse_mode: str | None = None,
                      reply_markup: Any = None) -> "Message":
        """Send a new message to the same chat, without quoting."""
        client = self._require_client()
        return await client.send_message(
            self.chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup,
        )

    async def reply(self, text: str, *, parse_mode: str | None = None,
                    reply_markup: Any = None) -> "Message":
        """Send a message that quotes this message."""
        client = self._require_client()
        return await client.send_message(
            self.chat_id, text, reply_to=self.id,
            parse_mode=parse_mode, reply_markup=reply_markup,
        )

    async def react(self, emoji: str) -> None:
        client = self._require_client()
        await client.send_reaction(self.chat_id, self.id, emoji)

    async def delete(self, revoke: bool = True) -> None:
        client = self._require_client()
        await client.delete_messages_in(self.chat_id, [self.id], revoke=revoke)

    async def edit(self, new_text: str, *, parse_mode: str | None = None) -> None:
        client = self._require_client()
        await client.edit_message(self.chat_id, self.id, new_text, parse_mode=parse_mode)

    async def pin(self, notify: bool = False) -> None:
        client = self._require_client()
        await client.pin_message(self.chat_id, self.id, notify=notify)

    async def forward_to(self, peer: Any) -> None:
        client = self._require_client()
        await client.forward_messages(peer, self.chat_id, [self.id])

    async def get_sender(self) -> "User | None":
        client = self._require_client()
        if self.sender_id is None:
            return None
        return await client.get_user(self.sender_id)

    async def get_chat(self) -> "Chat | None":
        client = self._require_client()
        return await client.get_chat(self.chat_id)

    async def get_reply_message(self) -> "Message | None":
        client = self._require_client()
        if self.reply_to_msg_id is None:
            return None
        raw = await client.get_message(self.chat_id, self.reply_to_msg_id)
        if raw is None:
            return None
        msg = Message.from_tl(raw)
        msg._client = client
        return msg

    async def reply_photo(self, path: str, caption: str = "", *,
                          parse_mode: str | None = None) -> "Message":
        client = self._require_client()
        return await client.send_photo(
            self.chat_id, path, caption, parse_mode=parse_mode, reply_to=self.id,
        )

    async def reply_document(self, path: str, caption: str = "",
                              mime_type: str | None = None, *,
                              parse_mode: str | None = None) -> "Message":
        client = self._require_client()
        return await client.send_document(
            self.chat_id, path, caption, mime_type, parse_mode=parse_mode, reply_to=self.id,
        )

    def __repr__(self) -> str:
        return f"Message(id={self.id}, text={self.text[:40]!r})"


@dataclass
class Dialog:
    peer: dict
    top_message: int
    unread_count: int
    unread_mentions_count: int
    unread_reactions_count: int
    pinned: bool
    folder_id: int | None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "Dialog":
        return cls(
            peer=d.get("peer") or {},
            top_message=_int(d, "top_message"),
            unread_count=_int(d, "unread_count"),
            unread_mentions_count=_int(d, "unread_mentions_count"),
            unread_reactions_count=_int(d, "unread_reactions_count"),
            pinned=_bool(d, "pinned"),
            folder_id=d.get("folder_id"),
            _raw=d,
        )

    @property
    def peer_id(self) -> int:
        return _peer_to_id(self.peer) or 0

    def __repr__(self) -> str:
        return f"Dialog(peer={self.peer}, unread={self.unread_count})"


@dataclass
class ChatMember:
    user_id: int
    rank: str
    is_admin: bool
    is_creator: bool
    is_banned: bool
    banned_until: int | None
    joined_date: int | None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "ChatMember":
        t = d.get("_", "")
        return cls(
            user_id=_int(d, "user_id"),
            rank=_str(d, "rank"),
            is_admin="Admin" in t or "Creator" in t,
            is_creator="Creator" in t,
            is_banned="Banned" in t,
            banned_until=d.get("banned_rights", {}).get("until_date") if isinstance(d.get("banned_rights"), dict) else None,
            joined_date=d.get("date"),
            _raw=d,
        )

    def __repr__(self) -> str:
        return f"ChatMember(user_id={self.user_id}, admin={self.is_admin})"


@dataclass
class Authorization:
    hash: int
    device_model: str
    platform: str
    system_version: str
    api_id: int
    app_name: str
    date_created: int
    date_active: int
    ip: str
    country: str
    region: str
    current: bool
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "Authorization":
        return cls(
            hash=_int(d, "hash"),
            device_model=_str(d, "device_model"),
            platform=_str(d, "platform"),
            system_version=_str(d, "system_version"),
            api_id=_int(d, "api_id"),
            app_name=_str(d, "app_name"),
            date_created=_int(d, "date_created"),
            date_active=_int(d, "date_active"),
            ip=_str(d, "ip"),
            country=_str(d, "country"),
            region=_str(d, "region"),
            current=_bool(d, "current"),
            _raw=d,
        )

    def __repr__(self) -> str:
        return f"Authorization(device={self.device_model!r}, ip={self.ip!r})"


@dataclass
class ForumTopic:
    id: int
    title: str
    icon_color: int
    icon_emoji_id: int | None
    top_message: int
    unread_count: int
    closed: bool
    pinned: bool
    hidden: bool
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "ForumTopic":
        return cls(
            id=_int(d, "id"),
            title=_str(d, "title"),
            icon_color=_int(d, "icon_color"),
            icon_emoji_id=d.get("icon_emoji_id"),
            top_message=_int(d, "top_message"),
            unread_count=_int(d, "unread_count"),
            closed=_bool(d, "closed"),
            pinned=_bool(d, "pinned"),
            hidden=_bool(d, "hidden"),
            _raw=d,
        )

    def __repr__(self) -> str:
        return f"ForumTopic(id={self.id}, title={self.title!r})"


@dataclass
class BotInfo:
    name: str
    about: str
    description: str
    commands: list[dict]
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "BotInfo":
        return cls(
            name=_str(d, "name"),
            about=_str(d, "about"),
            description=_str(d, "description"),
            commands=d.get("commands") or [],
            _raw=d,
        )


@dataclass
class InviteLinkMember:
    user_id: int
    date: int
    approved: bool
    requested: bool
    via_chatlist: bool
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "InviteLinkMember":
        return cls(
            user_id=_int(d, "user_id"),
            date=_int(d, "date"),
            approved=_bool(d, "approved"),
            requested=_bool(d, "requested"),
            via_chatlist=_bool(d, "via_chatlist"),
            _raw=d,
        )


@dataclass
class ReadParticipant:
    user_id: int
    date: int
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "ReadParticipant":
        return cls(user_id=_int(d, "user_id"), date=_int(d, "date"), _raw=d)


@dataclass
class AdminLogEvent:
    id: int
    date: int
    user_id: int
    action: dict
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "AdminLogEvent":
        return cls(
            id=_int(d, "id"),
            date=_int(d, "date"),
            user_id=_int(d, "user_id"),
            action=d.get("action") or {},
            _raw=d,
        )


@dataclass
class StickerSetInfo:
    id: int
    access_hash: int
    title: str
    short_name: str
    count: int
    animated: bool
    videos: bool
    emojis: bool
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "StickerSetInfo":
        s = d.get("set", d)
        return cls(
            id=_int(s, "id"),
            access_hash=_int(s, "access_hash"),
            title=_str(s, "title"),
            short_name=_str(s, "short_name"),
            count=_int(s, "count"),
            animated=_bool(s, "animated"),
            videos=_bool(s, "videos"),
            emojis=_bool(s, "emojis"),
            _raw=d,
        )


@dataclass
class BroadcastStats:
    period: dict
    followers: dict
    views_per_post: dict
    shares_per_post: dict
    reactions_per_post: dict
    enabled_notifications: dict
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "BroadcastStats":
        return cls(
            period=d.get("period") or {},
            followers=d.get("followers") or {},
            views_per_post=d.get("views_per_post") or {},
            shares_per_post=d.get("shares_per_post") or {},
            reactions_per_post=d.get("reactions_per_post") or {},
            enabled_notifications=d.get("enabled_notifications") or {},
            _raw=d,
        )


@dataclass
class MegagroupStats:
    period: dict
    members: dict
    messages: dict
    viewers: dict
    posters: dict
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "MegagroupStats":
        return cls(
            period=d.get("period") or {},
            members=d.get("members") or {},
            messages=d.get("messages") or {},
            viewers=d.get("viewers") or {},
            posters=d.get("posters") or {},
            _raw=d,
        )


@dataclass
class NotifySettings:
    mute_until: int
    silent: bool
    show_previews: bool | None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_tl(cls, d: dict) -> "NotifySettings":
        return cls(
            mute_until=_int(d, "mute_until"),
            silent=_bool(d, "silent"),
            show_previews=d.get("show_previews"),
            _raw=d,
        )
