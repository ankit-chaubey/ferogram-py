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


# ferogram.raw - direct Telegram API access
#
# Usage:
#   from ferogram import raw
#
#   # namespace style
#   await client.invoke(raw.functions.messages.GetHistory(
#       peer=raw.types.InputPeerChannel(channel_id=123, access_hash=456),
#       limit=10,
#   ))
#
#   # client callable style
#   await client(raw.functions.messages.GetHistory(
#       peer=raw.types.InputPeerChannel(channel_id=123, access_hash=456),
#       limit=10,
#   ))
#
#   # dict style (escape hatch)
#   await client.invoke({"_": "messages.getHistory", "peer": {...}, "limit": 10})

from . import tl
_tl = tl
from .generated import functions, types

__all__ = ["functions", "types", "tl", "_tl"]
