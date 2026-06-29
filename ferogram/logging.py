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

from __future__ import annotations

import logging
import sys

_LOG = logging.getLogger("ferogram")


def setup(level: int = logging.INFO, fmt: str | None = None) -> None:
    """Configure ferogram's logger to write to stderr.

    Call once at startup, before app.run(), if you want log output.

    Parameters
    ----------
    level : logging level constant, e.g. logging.DEBUG / logging.INFO
    fmt   : optional format string; defaults to a sensible one-line format
    """
    if _LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt or "%(asctime)s [%(levelname)s] ferogram: %(message)s",
        datefmt="%H:%M:%S",
    ))
    _LOG.addHandler(handler)
    _LOG.setLevel(level)


def get_logger() -> logging.Logger:
    return _LOG


# module-level shortcuts
debug   = _LOG.debug
info    = _LOG.info
warning = _LOG.warning
error   = _LOG.error
