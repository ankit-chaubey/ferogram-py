# ferogram-py

Python bindings for [ferogram](https://github.com/ankit-chaubey/ferogram), a Telegram MTProto client written in Rust.

ferogram-py keeps the Telegram-specific work in a Rust core and exposes a small async Python layer on top. That gives you a Python-friendly API for bots, userbots, and automation, while the heavy lifting stays in Rust.

## Highlights

- Rust-powered MTProto transport, encryption, sessions, and update handling
- Async Python API with decorators and raw TL access
- Session backends for files, SQLite, memory, StringSession, libSQL, and custom stores
- High-level helpers for messages, media, chats, polls, inline bots, privacy, and bot management
- Prebuilt wheels for Linux, macOS, Windows, and Android/Termux

## Install

```bash
pip install ferogram
```

Prebuilt wheels are available for:

| Platform | Arch |
|---|---|
| Linux (manylinux) | x86_64, aarch64 |
| macOS | x86_64, arm64 |
| Windows | x86_64 |
| Android / Termux | aarch64, x86_64 |

If you need a local build:

```bash
pip install ferogram --no-binary ferogram
```

On Termux:

```bash
pkg install rust clang python
pip install ferogram --no-binary ferogram
```

## Quick start

```python
from ferogram import Client, filters

app = Client("mybot", api_id=0, api_hash="", bot_token="123:TOKEN")

@app.on_message(filters.command("start"))
async def start(client, message):
    await client.send_message(message.chat_id, "Hello!")

app.run()
```

Credentials can also come from environment variables:

- `API_ID`
- `API_HASH`
- `BOT_TOKEN`

## Client setup

```python
from ferogram import Client

app = Client(
    session="mybot",       # session file name, or a session object
    api_id=123456,
    api_hash="abc...",
    bot_token="123:TOKEN", # omit for userbot
)

app.run()
# or
await app.start()
await app.run_until_disconnected()
# or
async with app as client:
    ...
```

## Raw API

Use `client.raw` when you want a convenient proxy for TL methods.

```python
result = await client.raw.messages.GetHistory(peer="@durov", limit=5)
result = await client.raw.messages.SendMessage(peer="@user", message="hi")
```

For explicit control, import generated classes directly:

```python
from ferogram.raw.generated.functions.messages import GetHistory

result = await client.invoke(GetHistory(
    peer=await client.resolve_peer("@durov"),
    offset_id=0,
    offset_date=0,
    add_offset=0,
    limit=5,
    max_id=0,
    min_id=0,
    hash=0,
))
```

## Architecture

```text
Python caller
   ↓ await
ferogram-py (PyO3 extension)
   ↓ FFI
ferogram (Rust / tokio)
   ↓ TCP / TLS
Telegram MTProto
```

## License

Dual-licensed under MIT or Apache 2.0.

Developed by [Ankit Chaubey](https://github.com/ankit-chaubey)

