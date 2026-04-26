# ferogram-py

Python bindings for [ferogram](https://github.com/ankit-chaubey/ferogram), a Telegram MTProto client written in Rust.

The Rust core handles crypto, transport, session management, and update processing. The Python layer gives you async/await methods and decorator-based event handlers with no boilerplate.

Built with [PyO3](https://pyo3.rs) and [maturin](https://maturin.rs). Works on Linux, macOS, Windows, and Android (Termux).

## Install

```bash
pip install ferogram
```

Pre-built wheels are available for:

| Platform | Arch |
|---|---|
| Linux (manylinux) | x86_64, aarch64 |
| macOS | x86_64, arm64 |
| Windows | x86_64 |
| Android / Termux | aarch64, x86_64 |

On Termux, `pip install ferogram` picks the correct Android wheel automatically.

### Force local build

If the pre-built wheel does not work, or you want to compile for your exact machine:

```bash
# from PyPI source
pip install ferogram --no-binary ferogram

# from cloned repo
git clone https://github.com/ankit-chaubey/ferogram-py
cd ferogram-py
pip install . --no-binary ferogram
```

Termux source build prerequisites:

```bash
pkg install rust clang python
pip install ferogram --no-binary ferogram
```

## Quick start

```python
from ferogram import Client, filters

app = Client("mybot", bot_token="123:TOKEN")

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("Hello!")

app.run()
```

## Handlers

ferogram uses decorator-based handlers. Each handler receives the `Client` and the update object.

```python
@app.on_message(filters.command("start"))
async def on_start(client, message):
    await message.reply("Hello!")

@app.on_message(filters.command("help"))
async def on_help(client, message):
    await message.reply("Commands: /start /help")

@app.on_edited_message(filters.text)
async def on_edit(client, message):
    await message.reply("you edited a message")

@app.on_callback_query(filters.data("btn_ok"))
async def on_btn(client, query):
    await query.answer(text="OK!")

@app.on_inline_query()
async def on_inline(client, query):
    pass  # handle inline queries

@app.on_user_status()
async def on_status(client, status):
    print(status.user_id, status.status)

@app.on_chat_action()
async def on_action(client, action):
    pass  # user joined, left, pinned, etc.

@app.on_message_deleted()
async def on_delete(client, event):
    pass

@app.on_participant_update()
async def on_participant(client, event):
    pass

@app.on_message_reaction()
async def on_reaction(client, event):
    pass

@app.on_poll_vote()
async def on_vote(client, event):
    pass

@app.on_raw_update()
async def on_raw(client, update):
    pass  # every raw TL update
```

## Filters

Combine filters by passing multiple to the decorator.

```python
filters.all             # every update
filters.text            # message has text
filters.photo           # message has a photo
filters.media           # message has any media
filters.private         # private chat
filters.group           # group or channel
filters.incoming        # not sent by you
filters.outgoing        # sent by you
filters.mentioned       # bot was mentioned
filters.album           # grouped media

filters.command("start")        # /start
filters.regex(r"hello|hi")      # text matches pattern
filters.user(123456)            # from a specific user
filters.chat(-100123456)        # in a specific chat
filters.data("btn_ok")          # callback query data

filters.and_(f1, f2)    # both must pass
filters.or_(f1, f2)     # either passes
filters.not_(f1)        # inverts a filter
```

## Messages

```python
# send
msg = await client.send_message("me", "hello")
await client.send_html("me", "<b>bold</b>")
await client.send_markdown("me", "**bold**")

# on the message object
await message.reply("got it")
await message.forward_to("me")
await message.pin()
await message.edit("updated text")
await message.delete()
```

## Media

```python
await client.send_photo("me", "photo.jpg", caption="look")
await client.send_document("me", "file.pdf", caption="report")
```

## Edit and delete

```python
msg = await client.send_message("me", "draft")
await client.edit_message("me", msg.id, "updated")
await client.delete_message(msg.id)
await client.delete_messages([1, 2, 3])
```

## Dialogs and account

```python
me = await client.get_me()
print(me.first_name, me.username)

dialogs = await client.get_dialogs(limit=20)
for d in dialogs:
    print(d.title, d.unread_count)
```

## Userbot

```python
from ferogram import Client, filters

app = Client("session", api_id=123456, api_hash="abc123")

@app.on_message(filters.private, filters.incoming, filters.text)
async def echo(client, message):
    await message.reply(message.text)

app.run()
```

## Raw API

Access any Telegram API method directly using the generated TL types.

```python
from ferogram.raw.api.functions import GetHistory
from ferogram.raw.api.types import InputPeerUsername

result = await app.invoke(GetHistory(
    peer=InputPeerUsername(username="durov").to_dict(),
    offset_id=0,
    offset_date=0,
    add_offset=0,
    limit=10,
    max_id=0,
    min_id=0,
    hash=0,
))
for msg in result.get("messages", []):
    print(msg.get("id"), msg.get("message", "")[:80])
```

758 functions and 1559 types are available under `ferogram.raw.api.functions` and `ferogram.raw.api.types`.

The `generated/` directory is internal codegen output. Always import from `ferogram.raw.api`.

## Context manager

```python
async with Client("session", api_id=..., api_hash=...) as app:
    await app.send_message("me", "hello")
```

## Architecture

```
Python caller
    |  asyncio await
    v
ferogram-py  (PyO3 .so extension)
    |  FFI, Rust holds GIL only at call boundary
    v
ferogram  (Rust, tokio async runtime)
    |  TCP / TLS
    v
Telegram MTProto
```

## License

MIT OR Apache-2.0

Developed by [Ankit Chaubey](https://github.com/ankit-chaubey)
