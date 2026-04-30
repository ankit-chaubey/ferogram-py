# ferogram-py

Python bindings for [ferogram](https://github.com/ankit-chaubey/ferogram), a Telegram MTProto client written in Rust.

Built with [PyO3](https://pyo3.rs) and [maturin](https://maturin.rs). Works on Linux, macOS, Windows, and Android (Termux).

---

## What is ferogram-py?

ferogram-py is a Python interface for the ferogram MTProto client.

It uses a Rust core for networking, encryption, session handling, and updates, while exposing a simple async Python API on top.

You can use it to build userbots, bots, or automation tools with access to both high-level methods and raw Telegram APIs.

---

The Rust core handles crypto, transport, session management, and update processing. The Python layer provides async/await methods and decorator-based event handlers with minimal overhead.

> Full API reference: [FEATURES.md](./FEATURES.md)

---

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

---

## Quick start

```python
from ferogram import Client, filters

app = Client("mybot", api_id=0, api_hash="", bot_token="123:TOKEN")

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("Hello!")

app.run()
```

Credentials can also come from env vars: `API_ID`, `API_HASH`, `BOT_TOKEN`.

---

## Client setup

```python
from ferogram import Client

app = Client(
    session="mybot",       # session file name (no extension)
    api_id=123456,
    api_hash="abc...",
    bot_token="123:TOKEN", # omit for userbot
)

app.run()                          # blocking; starts and loops forever
# or
await app.start()
await app.run_until_disconnected()
# or as context manager
async with app as client:
    ...
```

Session is created on first run and reused automatically.

---

## Raw API

Use `client.raw` for convenience. Use class-based calls only when you need full control.

Preferred (namespace proxy, peer strings auto-resolve):

```python
result = await client.raw.messages.GetHistory(peer="@durov", limit=5)
result = await client.raw.messages.SendMessage(peer="@user", message="hi")
```

Class-based (full control):

```python
from ferogram.raw.generated.functions.messages import GetHistory

result = await client.invoke(GetHistory(
    peer=await client.resolve_peer("@durov"),
    offset_id=0, offset_date=0, add_offset=0,
    limit=5, max_id=0, min_id=0, hash=0,
))
# shorthand
result = await client(GetHistory(...))
```

Results are low-level TL objects (or dict-like structures) matching the Telegram schema. The `generated/` directory is internal codegen output. Direct imports from it are considered advanced usage and may change.

All functions and types are available. See [FEATURES.md](./FEATURES.md#raw-api) for all import styles.

---

## Userbot

```python
from ferogram import Client, filters

app = Client("session", api_id=123456, api_hash="abc123")

@app.on_message(filters.private, filters.incoming, filters.text)
async def echo(client, message):
    await message.reply(message.text)

app.run()
```

---

## Logging

```python
import ferogram.logging as fero_log

fero_log.setup()           # INFO to stderr
fero_log.setup(level=10)   # DEBUG
```

---

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

---

## License

This project is dual-licensed under:

- MIT License
- Apache License 2.0

You may choose either license.

You are free to use, modify, and distribute this software (including commercial use), provided that the original license and copyright notice are included.

See `LICENSE-MIT` and `LICENSE-APACHE` for full details.

Developed by [Ankit Chaubey](https://github.com/ankit-chaubey)

---

⭐ Star this repo if you find it useful
