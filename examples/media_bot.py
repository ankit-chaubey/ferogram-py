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


# Media bot: send typed files and react to forwarded messages.

from ferogram import Client, filters

app = Client("bot", bot_token="123:TOKEN")


@app.on_message(filters.command("dice"))
async def send_dice(client, message):
    await client.send_dice(str(message.chat_id))


@app.on_message(filters.forwarded)
async def on_forward(client, message):
    await message.reply("That message was forwarded!")


@app.on_message(filters.via_bot)
async def on_via_bot(client, message):
    await message.react("👍")


@app.on_message(filters.command("typing"))
async def show_typing(client, message):
    await client.send_chat_action(str(message.chat_id), "typing")
    import asyncio
    await asyncio.sleep(2)
    await message.reply("Done typing.")


app.run()
