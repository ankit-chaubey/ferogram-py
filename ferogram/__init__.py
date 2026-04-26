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

from .client import Client
from ._ferogram import (
    LoginToken, PasswordToken,
    Message, CallbackQuery, User, Dialog,
    MessageDeletion, InlineQuery, InlineSend,
    UserStatus, ChatAction, ParticipantUpdate,
    JoinRequest, MessageReaction, PollVote,
    BotStopped, RawUpdate,
)
from . import filters
from . import raw
from . import logging as log

__version__ = "0.1.0"
__author__  = "Ankit Chaubey"
__all__ = [
    "Client",
    "LoginToken", "PasswordToken",
    "Message", "CallbackQuery", "User", "Dialog",
    "MessageDeletion", "InlineQuery", "InlineSend",
    "UserStatus", "ChatAction", "ParticipantUpdate",
    "JoinRequest", "MessageReaction", "PollVote",
    "BotStopped", "RawUpdate",
    "filters", "raw", "log",
]
