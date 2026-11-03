VENV = .venv

$(VENV):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -U pip maturin

# Regen python/ferogram/raw/generated/ from schema/api.tl, no Rust build needed.
# build.rs runs this same script automatically on dev/build below.
codegen:
	python3 tools/codegen.py schema/api.tl python/ferogram/raw/generated

# Round-trip test for every generated constructor (no Rust extension needed).
test-tl: codegen
	python3 tests/unit/test_tl_roundtrip.py

# All unit tests. No Rust extension needed (a stub is used when it is not built).
test-unit:
	python3 -m pytest

lint:
	ruff check python tools tests examples

# Editable install: builds the Rust extension (runs build.rs/codegen), installs into $(VENV).
dev: $(VENV)
	$(VENV)/bin/maturin develop

# Release wheel for this machine. CI handles multi-platform builds.
build: $(VENV)
	$(VENV)/bin/maturin build --release

test: dev
	$(VENV)/bin/pip install -e .[dev]
	$(VENV)/bin/pytest

clean:
	rm -rf $(VENV) target dist
	find . -name __pycache__ -exec rm -rf {} +

.PHONY: codegen test-tl test-unit lint dev build test clean
