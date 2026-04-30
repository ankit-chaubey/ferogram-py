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
from ferogram import Client

app = Client("ferogram")  # set API_ID / API_HASH / BOT_TOKEN env vars


async def main():
    await app.start()

    me = await app.get_me()
    print(f"Logged in as {me.first_name} (id={me.id})")

    # send plain text
    msg = await app.send_message("me", "hello from ferogram")
    print(f"sent message id={msg.id}")

    # edit it
    await app.edit_message("me", msg.id, "edited message")

    # send html
    await app.send_message("me", "<b>bold</b> and <i>italic</i>", parse_mode="html")

    # send markdown
    await app.send_message("me", "**bold** and _italic_", parse_mode="markdown")

    # delete the message
    await app.delete_message(msg.id)

    # get dialogs
    dialogs = await app.get_dialogs(limit=5)
    for d in dialogs:
        print(f"  {d.title!r} unread={d.unread_count}")


asyncio.run(main())
