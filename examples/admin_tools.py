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


# Admin tools example: admins list, online count, archive, pin/unpin.

from ferogram import Client, filters

app = Client("bot", bot_token="123:TOKEN")


@app.on_message(filters.command("admins"))
async def list_admins(client, message):
    admins = await client.get_chat_administrators(str(message.chat_id))
    lines = [f"{a.full_name} - {a.status}" + (f" ({a.admin_rank})" if a.admin_rank else "") for a in admins]
    await message.reply("\n".join(lines) or "No admins found.")


@app.on_message(filters.command("online"))
async def online_count(client, message):
    n = await client.get_online_count(str(message.chat_id))
    await message.reply(f"{n} members online right now.")


@app.on_message(filters.command("unpin_all"))
async def unpin_all(client, message):
    await client.unpin_all_messages(str(message.chat_id))
    await message.reply("All messages unpinned.")


app.run()
