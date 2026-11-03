# Contributing

## Layout

```
python/ferogram/      the Python package
  client.py           Client: connection, updates, dispatch
  methods/            Client's public methods, grouped by domain
  raw/                TL serializer and the generated TL layer (generated/)
  types.py, updates.py, filters.py, keyboards.py, rich.py, logging.py
schema/api.tl         the Telegram TL schema (first line: // LAYER n)
tools/codegen.py      generates python/ferogram/raw/generated/ from the schema
src/                  Rust extension (PyO3), built by maturin
build.rs              runs tools/codegen.py during builds
tests/unit/           tests that run without the compiled extension
examples/             runnable scripts, see examples/README.md
```

## Setup

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"      # builds the Rust extension, needs a Rust toolchain
```

The unit tests do not need the extension. Without it a stub is used, so this is enough
for most Python work:

```sh
pip install pytest ruff
pytest
ruff check python tools tests examples
```

Set `FEROGRAM_TEST_STUB=1` to force the stub even when the extension is built.

## Bumping the TL layer

1. Replace `schema/api.tl` with the new schema.
2. `make codegen` to regenerate `python/ferogram/raw/generated/`, and commit the result.
3. Update the Rust dependencies in `Cargo.toml` to a ferogram release built on the same layer.
   The Rust side parses updates with its own copy of the layer, so both sides must match.
4. Run `pytest`. `test_schema_usage.py` points at any hand-built request that no longer matches
   the schema, and `test_codegen_up_to_date.py` fails if the generated code is stale.
5. Add a `CHANGELOG.md` entry.

## Tests

- New behaviour needs a test in `tests/unit/`.
- `tests/unit/test_schema_usage.py` keeps a list of known mismatches (`KNOWN_ISSUES`). It can only
  shrink: remove an entry when you fix it.
