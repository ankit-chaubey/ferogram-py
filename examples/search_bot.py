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
from ferogram import Client, filters

app = Client(
    "search_bot",
    api_id=int(os.environ["API_ID"]),
    api_hash=os.environ["API_HASH"],
    bot_token=os.environ["BOT_TOKEN"],
)


@app.on_message(filters.command("search"))
async def search(client, msg):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("Usage: /search <query>")
        return
    query = parts[1]
    results = await client.search_messages(str(msg.chat_id), query, limit=5)
    if not results:
        await msg.reply("No results.")
        return
    lines = [f"• [{m.id}] {(m.text or '')[:80]}" for m in results]
    await msg.reply("\n".join(lines))


@app.on_message(filters.command("gsearch"))
async def global_search(client, msg):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("Usage: /gsearch <query>")
        return
    results = await client.search_global(parts[1], limit=5)
    if not results:
        await msg.reply("No results.")
        return
    lines = [f"• [{m.chat_id}/{m.id}] {(m.text or '')[:60]}" for m in results]
    await msg.reply("\n".join(lines))


if __name__ == "__main__":
    app.run()
