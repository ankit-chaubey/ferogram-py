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


"""Method groups that make up `ferogram.Client`."""

from .auth import AuthMethods
from .users import UserMethods
from .messages import MessageMethods
from .dialogs import DialogMethods
from .chats import ChatMethods
from .participants import ParticipantMethods
from .invites import InviteMethods
from .media import MediaMethods
from .bots import BotMethods

__all__ = [
    "AuthMethods",
    "UserMethods",
    "MessageMethods",
    "DialogMethods",
    "ChatMethods",
    "ParticipantMethods",
    "InviteMethods",
    "MediaMethods",
    "BotMethods",
]
