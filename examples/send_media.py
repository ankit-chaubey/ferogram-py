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
from ferogram import Client

app = Client("fero", api_id=, api_hash="")


async def main():
    await app.start()

    photo_path = "photo.jpg"
    doc_path = "report.pdf"

    if os.path.isfile(photo_path):
        msg = await app.send_photo("me", photo_path, caption="my photo")
        print(f"photo sent, msg id={msg.id}")
    else:
        print(f"skipping photo: {photo_path!r} not found")

    if os.path.isfile(doc_path):
        msg = await app.send_document("me", doc_path, caption="report")
        print(f"doc sent, msg id={msg.id}")
    else:
        print(f"skipping doc: {doc_path!r} not found")


asyncio.run(main())
