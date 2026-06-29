# ferogram-py

A Python MTProto library powered by the Rust-based [ferogram](https://github.com/ankit-chaubey/ferogram) engine, delivering near-native performance with minimal Python overhead.

Built with [PyO3](https://pyo3.rs) and [maturin](https://maturin.rs). Works on Linux, macOS, Windows, and Android (Termux).

---

## Why ferogram-py?

ferogram-py combines Python's simplicity with the speed and efficiency of a native Rust implementation.

Performance-critical components such as networking, encryption, session management, and MTProto internals run natively in Rust, reducing Python overhead while exposing a clean and Pythonic API.

Whether you're building userbots, bots, or automation tools, ferogram-py provides both high-level abstractions and direct access to raw Telegram APIs when needed.

> Quick API reference: [FEATURES.md](./FEATURES.md)

---

## Install

```bash
pip install ferogram
```

Pre-built wheels are available for Linux (x86_64, aarch64), macOS (x86_64, arm64), Windows (x86_64), and Android/Termux (aarch64, x86_64).

`pip install ferogram` picks the correct wheel automatically.

---

### Build from source

Clone the repository, then run:

```bash
make dev      # editable install into .venv (builds Rust extension)
make build    # release wheel for this machine
make codegen  # regen TL generated code without a Rust build
make test     # run tests
make clean    # remove .venv, target, dist, generated/
```

Termux prerequisites: `pkg install rust clang python`

To skip TL codegen on a Rust-only change: `FEROGRAM_SKIP_CODEGEN=1 maturin develop`

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

## Logging

```python
import ferogram.logging as fero_log

fero_log.setup()           # INFO to stderr
fero_log.setup(level=10)   # DEBUG
```

## Architecture

![architecture](assets/architecture.svg)

The compiled extension (`_ferogram.so`) is intentionally minimal. Networking, encryption, session management, and MTProto internals are implemented in Rust, while the high-level API remains entirely in Python and can be updated without recompiling rust core.
    
---

## License

This project is dual-licensed under:

- MIT License
- Apache License 2.0

You may choose either license.

You are free to use, modify, and distribute this software, including for commercial use, provided the original license and copyright notice are included.

See `LICENSE-MIT` and `LICENSE-APACHE` for full details.

---

## Developer

Developed by [Ankit Chaubey](https://github.com/ankit-chaubey)

Don't forget to explore the Rust engine powering ferogram-py: [ferogram](https://github.com/ankit-chaubey/ferogram). Thanks for being part of the journey.

Join the ferogram community! Questions, discussions, and feedback are always welcome. As the project grows, we'll eventually split Python and Rust discussions into dedicated spaces.

 - Channel (releases & announcements):  [@Ferogram](https://t.me/Ferogram)

 - (questions & discussion): [@FerogramChat](https://t.me/FerogramChat)
