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

import asyncio
from ferogram import Client
from ferogram.raw.generated.functions import GetHistory
from ferogram.raw.generated.types import InputPeerUsername

app = Client("ferogram")


async def main():
    await app.start()

    result = await app.invoke(GetHistory(
        peer=InputPeerUsername(username="durov").to_dict(),
        offset_id=0,
        offset_date=0,
        add_offset=0,
        limit=5,
        max_id=0,
        min_id=0,
        hash=0,
    ))

    for msg in result.get("messages", []):
        print(msg.get("id"), msg.get("message", "")[:80])


asyncio.run(main())
