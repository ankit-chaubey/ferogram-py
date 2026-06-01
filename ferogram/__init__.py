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

from .client import Client, StopPropagation, ContinuePropagation
from . import filters
from ._ferogram import FileSession, MemorySession, StringSession, SqliteSession, LibSqlSession, CustomSession
from ._ferogram import User, Dialog, ChatMember, UserFull, Message
from ._ferogram import Chat, Authorization, ForumTopic, BotInfo
from ._ferogram import InviteLinkMember, ReadParticipant, AdminLogEvent, StickerSetInfo
from ._ferogram import BroadcastStats, MegagroupStats, NotifySettings
from ._ferogram import InlineButton, InlineKeyboard, ReplyButton, ReplyKeyboard
from ._ferogram import RemoveKeyboard, ForceReply
from .types import (
    ChatAction,
    PrivacyKey,
    PrivacyRule,
    InlineMessageId,
    InlineArticle,
    InlinePhoto,
    InlineDocument,
)

__all__ = [
    # Core
    "Client", "filters",
    "StopPropagation", "ContinuePropagation",
    # Rust types
    "User", "Dialog", "ChatMember", "UserFull", "Message",
    "Chat", "Authorization", "ForumTopic", "BotInfo",
    "InviteLinkMember", "ReadParticipant", "AdminLogEvent", "StickerSetInfo",
    "BroadcastStats", "MegagroupStats", "NotifySettings",
    # Keyboard builders
    "InlineButton", "InlineKeyboard",
    "ReplyButton", "ReplyKeyboard",
    "RemoveKeyboard", "ForceReply",
    # Typed wrappers
    "ChatAction", "PrivacyKey", "PrivacyRule",
    "InlineMessageId", "InlineArticle", "InlinePhoto", "InlineDocument",
]
