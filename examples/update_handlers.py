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

"""Demonstrates all update handler types and the logging module."""
import ferogram
import ferogram.logging as fero_log
from ferogram import filters

fero_log.setup()  # optional: enables debug/info output to stderr

app = ferogram.Client(session="demo")  # set API_ID / API_HASH / BOT_TOKEN env vars


@app.on_message(filters.command("start"))
async def start(client, msg):
    await msg.reply("Hello!")


@app.on_message(filters.command("react"))
async def react_demo(client, msg):
    await client.send_reaction(str(msg.chat_id), msg.id, "👍")


@app.on_edited_message(filters.text)
async def on_edit(client, msg):
    print(f"message {msg.id} was edited: {msg.text!r}")


@app.on_message_deleted()
async def on_delete(client, event):
    # event: MessageDeletion
    print(f"deleted: {event.message_ids} (channel={event.channel_id})")


@app.on_callback_query(filters.data_regex(r"^action:"))
async def on_button(client, q):
    await q.answer(f"You pressed: {q.data}", alert=False)


@app.on_inline_query(filters.inline(r"\w+"))
async def on_inline(client, q):
    print(f"inline from {q.user_id}: {q.query!r}")


@app.on_user_status(filters.online)
async def went_online(client, s):
    print(f"user {s.user_id} came online (expires={s.expires})")


@app.on_user_status(filters.offline)
async def went_offline(client, s):
    print(f"user {s.user_id} went offline (last seen={s.was_online})")


@app.on_chat_action(filters.typing)
async def on_typing(client, a):
    print(f"user {a.user_id} is typing in {a.peer_id}")


@app.on_participant_update()
async def on_member(client, p):
    verb = "joined" if not p.is_channel else "channel update"
    print(f"chat {p.chat_id}: user {p.user_id} - {verb}")


@app.on_message_reaction(filters.reaction("👍", "❤"))
async def on_reaction(client, r):
    print(f"msg {r.msg_id} got reactions: {r.new_reactions}")


@app.on_poll_vote()
async def on_vote(client, v):
    print(f"poll {v.poll_id}: vote from {v.peer_id} at positions {v.positions}")


@app.on_bot_stopped()
async def on_stop(client, b):
    action = "stopped" if b.stopped else "restarted"
    print(f"user {b.user_id} {action} the bot")


@app.on_raw_update(filters.update_type("ReadHistoryInbox"))
async def on_read(client, r):
    print(f"raw: {r.type_name} (cid=0x{r.constructor_id:08x})")


if __name__ == "__main__":
    app.run()
