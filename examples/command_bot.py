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

# Bot with /start and /help commands.

from ferogram import Client, filters

app = Client("bot", bot_token="123:TOKEN")


@app.on_message(filters.command("start"))
async def on_start(client, message):
    await message.reply("Hello! I am running on ferogram.")


@app.on_message(filters.command("help"))
async def on_help(client, message):
    await message.reply("Commands: /start /help")


@app.on_callback_query(filters.data("btn_ok"))
async def on_ok(client, query):
    await query.answer(text="OK clicked!")


app.run()
