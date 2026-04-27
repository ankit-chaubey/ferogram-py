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


# Userbot example: profile updates, contacts, blocking, status.

import asyncio
from ferogram import Client

app = Client("userbot")


async def main():
    async with app:
        me = await app.get_me()
        print(f"Logged in as {me.full_name} (@{me.username})")

        # set online
        await app.update_status(offline=False)

        # show contacts
        contacts = await app.get_contacts()
        for c in contacts[:5]:
            print(f"Contact: {c.full_name} {c.mention}")

        # fetch full profile of first contact
        if contacts:
            full = await app.get_user_full(contacts[0].id)
            print(f"Bio: {full.about or 'no bio'}")

        # update our own profile
        await app.update_profile(about="Built with ferogram.")


asyncio.run(main())
