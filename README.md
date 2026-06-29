# ferogram-py

Python bindings for [ferogram](https://github.com/ankit-chaubey/ferogram), a Telegram MTProto client written in Rust.

Built with [PyO3](https://pyo3.rs) and [maturin](https://maturin.rs). Works on Linux, macOS, Windows, and Android (Termux).

## What is ferogram-py?

ferogram-py is a Python interface for the ferogram MTProto client. It uses a Rust core for networking, encryption, session handling, and low-level MTProto, while the high-level API lives in Python.

You can use it to build userbots, bots, or automation tools with access to both high-level methods and raw Telegram APIs.

> Full API reference: [FEATURES.md](./FEATURES.md)

## Install

```bash
pip install ferogram
```

Pre-built wheels are available for Linux (x86_64, aarch64), macOS (x86_64, arm64), Windows (x86_64), and Android/Termux (aarch64, x86_64).

On Termux, `pip install ferogram` picks the correct wheel automatically.

### Build from source

Clone the repo, then use make:

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

The compiled extension (`_ferogram.so`) is intentionally thin. It exposes only `DcConnection`, six session backends, and `srp_calculate`. All high-level logic lives in Python and can be updated without recompiling.

```
          your code
              │
    ┌─────────▼──────────────────────────────┐
    │        ferogram-py  (Python)           │
    │                                        │
    │  client · filters · types · updates    │
    │  keyboards · rich · raw/               │
    └─────────┬──────────────────────────────┘
              │  FFI (PyO3)
    ┌─────────▼──────────────────────────────┐
    │       _ferogram.so  (Rust)             │
    │                                        │
    │  DcConnection ──► ferogram_mtsender    │
    │                   ferogram_connect     │
    │                   ferogram_crypto      │
    │                                        │
    │  *Session     ──► ferogram_session     │
    │  srp_calculate──► ferogram_crypto      │
    └─────────┬──────────────────────────────┘
              │  TCP / TLS
              ▼
        Telegram MTProto
```

## License

This project is dual-licensed under MIT or Apache 2.0. You may choose either.

You are free to use, modify, and distribute this software, including for commercial use, provided the original license and copyright notice are included.

See `LICENSE-MIT` and `LICENSE-APACHE` for full details.

Developed by [Ankit Chaubey](https://github.com/ankit-chaubey)

---

⭐ Star this repo if you find it useful
