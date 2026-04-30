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

# Raw API usage example
# Use this for any method not covered by a high-level wrapper.
# Peer strings are resolved automatically by the raw proxy.

import asyncio
from ferogram import Client

app = Client("ferogram")


async def main():
    await app.start()

    result = await app.raw.messages.GetHistory(
        peer="@durov",
        limit=5,
    )

    for msg in result.get("messages", []):
        print(msg.get("id"), msg.get("message", "")[:80])


asyncio.run(main())
