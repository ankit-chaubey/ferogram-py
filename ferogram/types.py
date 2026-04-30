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

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "ChatAction",
    "PrivacyKey",
    "PrivacyRule",
    "InlineMessageId",
    "InlineArticle",
    "InlinePhoto",
    "InlineDocument",
]


# Chat actions

class ChatAction(str, Enum):
    """Constants for send_chat_action()."""

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


# Privacy

class PrivacyKey(str, Enum):
    """Key constants for get_privacy() / set_privacy()."""

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
    """Rule constants for set_privacy()."""

    ALLOW_ALL          = "allow_all"
    ALLOW_CONTACTS     = "allow_contacts"
    DISALLOW_ALL       = "disallow_all"
    DISALLOW_CONTACTS  = "disallow_contacts"


# Inline message identity

@dataclass
class InlineMessageId:
    """Identifies an inline bot message for edit_inline_message()."""

    dc_id: int
    id_bytes: bytes

    def __repr__(self) -> str:
        return f"InlineMessageId(dc_id={self.dc_id}, len={len(self.id_bytes)})"


# Inline query result wrappers

@dataclass
class InlineArticle:
    """Article result for answer_inline_query()."""

    id: str
    title: str
    message_text: str
    thumb_url: str | None = None

    def _to_tuple(self) -> tuple:
        return ("article", self.id, self.title, self.message_text, self.thumb_url)


@dataclass
class InlinePhoto:
    """Photo result for answer_inline_query()."""

    id: str
    title: str
    message_text: str
    thumb_url: str | None = None

    def _to_tuple(self) -> tuple:
        return ("photo", self.id, self.title, self.message_text, self.thumb_url)


@dataclass
class InlineDocument:
    """Document result for answer_inline_query()."""

    id: str
    title: str
    message_text: str
    thumb_url: str | None = None

    def _to_tuple(self) -> tuple:
        return ("document", self.id, self.title, self.message_text, self.thumb_url)


# Internal helper

def _inline_result_to_tuple(r: object) -> tuple:
    """Coerce an inline result to the raw tuple the Rust layer expects."""
    if isinstance(r, (InlineArticle, InlinePhoto, InlineDocument)):
        return r._to_tuple()
    # Legacy tuple passthrough
    return r  # type: ignore[return-value]
