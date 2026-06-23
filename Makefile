VENV = .venv

$(VENV):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -U pip maturin

# Regen ferogram/raw/generated/ from ferogram/api.tl, no Rust build needed.
# build.rs runs this same script automatically on dev/build below.
codegen:
	python3 ferogram/raw/codegen.py ferogram/api.tl ferogram/raw/generated

# Round-trip test for every generated constructor (no Rust extension needed).
test-tl: codegen
	python3 tests/test_tl_roundtrip.py

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
	rm -rf $(VENV) target dist ferogram/raw/generated
	find . -name __pycache__ -exec rm -rf {} +

.PHONY: codegen test-tl dev build test clean
