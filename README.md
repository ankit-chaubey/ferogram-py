<div align="center">
  
# ferogram-py

![PyPI](https://img.shields.io/pypi/v/ferogram?style=flat-square&logo=pypi&logoColor=white&color=7C3AED)
![Python](https://img.shields.io/pypi/pyversions/ferogram?style=flat-square&logo=python&logoColor=FFD43B&color=3B82F6)
![Downloads](https://img.shields.io/pepy/dt/ferogram?style=flat-square&color=14B8A6)
![License](https://img.shields.io/badge/License-MIT%20%7C%20Apache--2.0-64748B?style=flat-square)
![Telegram](https://img.shields.io/badge/Telegram-FerogramChat-06B6D4?style=flat-square&logo=telegram&logoColor=white)

**A modern, elegant, asynchronous MTProto framework for building Telegram clients and bots in Python.**

</div>

Powered by a high-performance [Rust core](https://github.com/ankit-chaubey/ferogram) that takes care of networking, encryption, TL parsing, and session management so you can focus on writing clean, idiomatic Python.

---

## Why ferogram-py?

Most of the heavy lifting in an MTProto client happens behind the scenes; networking, encryption, TL parsing, and keeping up with updates. ferogram-py lets a Rust core handle all of that, while exposing a clean, Pythonic API.

For most applications, the high-level API is all you'll need. But if you want to use a brand-new Telegram feature or need something more advanced, you can always drop down to the raw MTProto API and invoke requests directly.

The goal is to stay out of your way: simple things should be simple, and advanced things should still be possible.

> Quick API reference: [FEATURES.md](./FEATURES.md)

---

## Install

```bash
pip install ferogram
```

<details>
<summary>Building from source</summary>

```bash
make dev      # editable install into .venv (builds the Rust extension)
make build    # release wheel for this machine
make codegen  # regenerate TL code without a Rust rebuild
make test     # run tests
make clean    # wipe .venv, target, dist, generated/
```

On Termux: `pkg install rust clang python` first.
Rust-only change, don't want to wait on codegen: `FEROGRAM_SKIP_CODEGEN=1 maturin develop`

</details>

---

## Quick start

**Bot:**

```python
from ferogram import Client, filters

app = Client("mybot", api_id=0, api_hash="", bot_token="123:TOKEN")

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("Hello!")

app.run()
```

**User:**

```python
import asyncio
from ferogram import Client

app = Client("myaccount", api_id=0, api_hash="", phone="+1234567890")

async def main():
    async with app as client:
        await client.send_message("me", "logged in")

asyncio.run(main())
```

Credentials also work from env vars: `API_ID`, `API_HASH`, `BOT_TOKEN`.

## Logging

```python
import ferogram.logging as fero_log

fero_log.setup()           # INFO to stderr
fero_log.setup(level=10)   # DEBUG
```

## Architecture

![architecture](https://github.com/ankit-chaubey/ferogram-py/blob/main/assets/architecture.svg)

The compiled extension (`_ferogram.so`) stays deliberately small: networking, encryption, session storage, and MTProto internals live in Rust. Everything you touch day to day, the client, handlers, filters, is plain Python and can change without a recompile.

<details>
<summary>Prebuilt Wheels for your platform</summary>

Wheels ship prebuilt for Linux (x86_64, aarch64), macOS (x86_64, arm64), Windows (x86_64), and Android/Termux (aarch64, x86_64). `pip install ferogram` grabs the right one on its own.

</details>

---

## License

This project is dual-licensed under:

- MIT License
- Apache License 2.0

You may choose either license.

You are free to use, modify, and distribute this software, including for commercial use, provided the original license and copyright notice are included.

See [`LICENSE-MIT`](https://github.com/ankit-chaubey/ferogram-py/blob/main/LICENSE-MIT) and [`LICENSE-APACHE`](https://github.com/ankit-chaubey/ferogram-py/blob/main/LICENSE-APACHE) for full details.

---

## Developer

Developed by [Ankit Chaubey](https://github.com/ankit-chaubey)

Don't forget to explore the Rust engine powering ferogram-py: [`ferogram`](https://github.com/ankit-chaubey/ferogram). Thanks for being part of the journey.

Join the ferogram community! Questions, discussions, bugs report and feedback are always welcome. As the project grows, we'll eventually split Python and Rust discussions into dedicated spaces.

 - Channel (releases & announcements):  [@Ferogram](https://t.me/Ferogram)

 - (questions & discussion): [@FerogramChat](https://t.me/FerogramChat)
