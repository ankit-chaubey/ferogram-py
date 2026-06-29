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

# Simple userbot that echoes messages in private chats.

from ferogram import Client, filters

app = Client("userbot", api_id=12345, api_hash="0123456789abcdef0123456789abcdef")
# replace api_id / api_hash with your own values from https://my.telegram.org


@app.on_message(filters.private, filters.incoming)
async def on_private(client, message):
    if message.text:
        await message.reply(f"you said: {message.text}")


app.run()
