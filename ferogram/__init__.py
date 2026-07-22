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

import os
import sys

_main_file = getattr(sys.modules.get("__main__"), "__file__", None)
if _main_file:
    _name = os.path.splitext(os.path.basename(_main_file))[0]
    if _name == "ferogram":
        raise ImportError(
            "\n\nYour script is named 'ferogram.py' which shadows the ferogram package "
            "and causes circular imports.\n"
            "Rename your file to something like 'bot.py', 'main.py', or 'app.py'."
        )

from .client import Client, StopPropagation, ContinuePropagation, TransferHandle, TransferCancelled
from .client import TransferLimits, available_qualities
from . import filters

# Session classes stay in Rust
from ._ferogram import (
    FileSession, MemorySession, StringSession,
    SqliteSession, LibSqlSession, CustomSession,
)

# All types now pure Python
from .types import User, Message, Chat, Dialog, ChatMember, UserFull
from .types import Authorization, ForumTopic, BotInfo
from .types import InviteLinkMember, ReadParticipant, AdminLogEvent
from .types import StickerSetInfo, BroadcastStats, MegagroupStats, NotifySettings
from .types import (
    ChatAction, PrivacyKey, PrivacyRule,
    InlineMessageId, InlineArticle, InlinePhoto, InlineDocument,
)

from .keyboards import InlineButton, InlineKeyboard, ReplyButton, ReplyKeyboard
from .keyboards import RemoveKeyboard, ForceReply
from .rich import _RichMixin as _RichMixin  # re-exported for type stubs

from .updates import (
    NewMessage, EditedMessage, MessageDeletion,
    CallbackQuery, InlineQuery, InlineSend,
    UserStatus, ParticipantUpdate, JoinRequest,
    MessageReaction, PollVote, BotStopped,
    ShippingQuery, PreCheckoutQuery, ChatBoost, RawUpdate,
)

__all__ = [
    # Core
    "Client", "filters", "StopPropagation", "ContinuePropagation",
    "TransferHandle", "TransferCancelled", "TransferLimits", "available_qualities",
    # Session (Rust)
    "FileSession", "MemorySession", "StringSession",
    "SqliteSession", "LibSqlSession", "CustomSession",
    # Entity types
    "User", "UserFull", "Message", "Chat", "Dialog", "ChatMember",
    "Authorization", "ForumTopic", "BotInfo",
    "InviteLinkMember", "ReadParticipant", "AdminLogEvent",
    "StickerSetInfo", "BroadcastStats", "MegagroupStats", "NotifySettings",
    # Value types
    "ChatAction", "PrivacyKey", "PrivacyRule",
    "InlineMessageId", "InlineArticle", "InlinePhoto", "InlineDocument",
    # Keyboards
    "InlineButton", "InlineKeyboard", "ReplyButton", "ReplyKeyboard",
    "RemoveKeyboard", "ForceReply",
    # Update events
    "NewMessage", "EditedMessage", "MessageDeletion",
    "CallbackQuery", "InlineQuery", "InlineSend",
    "UserStatus", "ParticipantUpdate", "JoinRequest",
    "MessageReaction", "PollVote", "BotStopped",
    "ShippingQuery", "PreCheckoutQuery", "ChatBoost", "RawUpdate",
]
