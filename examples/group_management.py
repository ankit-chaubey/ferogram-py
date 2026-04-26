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

import asyncio
import os
from ferogram import Client, filters

app = Client(
    "group_mgmt",
    api_id=int(os.environ["API_ID"]),
    api_hash=os.environ["API_HASH"],
    bot_token=os.environ["BOT_TOKEN"],
)


@app.on_message(filters.command("newtopic"))
async def new_topic(client, msg):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("Usage: /newtopic <title>")
        return
    await client.create_forum_topic(str(msg.chat_id), parts[1])
    await msg.reply(f"Topic created: {parts[1]}")


@app.on_message(filters.command("translate"))
async def translate(client, msg):
    if not msg.reply_to_message_id:
        await msg.reply("Reply to a message with /translate <lang>")
        return
    parts = msg.text.split(maxsplit=1)
    lang = parts[1].strip() if len(parts) > 1 else "en"
    texts = await client.translate_messages(
        str(msg.chat_id), [msg.reply_to_message_id], lang
    )
    if texts:
        await msg.reply(texts[0])


@app.on_message(filters.command("poll"))
async def send_poll(client, msg):
    await client.send_poll(
        str(msg.chat_id),
        question="Best language?",
        answers=["Python", "Rust", "Go", "Other"],
    )


if __name__ == "__main__":
    app.run()
