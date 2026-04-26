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

# Simple userbot that echoes messages in private chats.

from ferogram import Client, filters

app = Client("userbot", api_id=123456, api_hash="abc123")


@app.on_message(filters.private, filters.incoming)
async def on_private(client, message):
    if message.text:
        await message.reply(f"you said: {message.text}")


app.run()
