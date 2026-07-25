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
import os
import sys

_LOG = logging.getLogger("ferogram")

# ANSI codes matching tracing-subscriber's default terminal theme:
# dim timestamp, bold+colored level, dim target, plain message.
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
_LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",     # cyan
    logging.INFO: "\033[32m",      # green
    logging.WARNING: "\033[33m",   # yellow
    logging.ERROR: "\033[31m",     # red
    logging.CRITICAL: "\033[35m",  # magenta
}

# Python's WARNING/CRITICAL don't fit tracing's fixed 5-char column
# (TRACE/DEBUG/INFO_/WARN_/ERROR); shorten just for display.
_LEVEL_NAMES = {
    logging.WARNING: "WARN",
    logging.CRITICAL: "CRIT",
}


class ColorFormatter(logging.Formatter):
    """Formatter with the tracing-subscriber look: dim time, colored level,
    dim target, plain message. Falls back to plain output when stderr isn't
    a tty or NO_COLOR is set, same as tracing does.

    Works with plain `logging.basicConfig()` too, not just `setup()`:

        handler = logging.StreamHandler()
        handler.setFormatter(ColorFormatter())
        logging.basicConfig(handlers=[handler], level=logging.DEBUG)
    """

    def __init__(self, *, color: bool | None = None) -> None:
        super().__init__(datefmt="%H:%M:%S")
        if color is None:
            color = sys.stderr.isatty() and not os.environ.get("NO_COLOR")
        self._color = color

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, self.datefmt)
        name_str = _LEVEL_NAMES.get(record.levelno, record.levelname)
        level = f"{name_str:<5}"
        message = record.getMessage()

        if self._color:
            color = _LEVEL_COLORS.get(record.levelno, "")
            ts = f"{_DIM}{ts}{_RESET}"
            level = f"{_BOLD}{color}{level}{_RESET}"
            name = f"{_DIM}{record.name}:{_RESET}"
        else:
            name = f"{record.name}:"

        line = f"{ts} {level} {name} {message}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


# Rust crate namespaces bridged into Python logging via pyo3-log (see
# src/lib.rs's init_logging_bridge()). Each is a *root* for a whole tree of
# child loggers named after Rust modules (e.g. "ferogram_mtsender.sender",
# "ferogram_mtsender.pool", ...) - setting a level here is enough to affect
# all of them, the same way "ferogram.client" would inherit from "ferogram".
RUST_LOGGERS = (
    "ferogram_mtsender",  # connections, FLOOD_WAIT, bad_server_salt, retries
    "ferogram_msgbox",    # pts/qts gap detection, getDifference bookkeeping
    "ferogram_connect",   # transport framing, proxy, socket-level detail
    "ferogram_mtproto",   # MTProto message construction/parsing
    "ferogram_crypto",    # auth key exchange, PFS bind
    "ferogram_session",   # session file/backing-store I/O
)


def _reset_rust_cache() -> None:
    """Flush pyo3-log's cached "is this target enabled at level N" lookups.

    Rust caches each target's resolved Python level on first use so it
    doesn't have to take the GIL on every log call. That means a level
    change made *after* a target has already logged something - via
    `logging.getLogger("ferogram_mtsender").setLevel(...)`, this module's
    own `setup()`, or a fresh `logging.basicConfig(...)` - won't be picked
    up until this runs. Call it after any such change; `setup()` below
    already does.
    """
    try:
        from ._ferogram import reset_logging_cache
        reset_logging_cache()
    except ImportError:
        # Built against an older native extension that predates the
        # bridge - nothing to reset, and nothing to log through it either.
        pass


def setup(
    level: int = logging.INFO,
    fmt: str | None = None,
    *,
    rust_level: int | None = None,
    color: bool | None = None,
) -> None:
    """Configure ferogram's logger (Python and Rust sides) to write to stderr.

    Call once at startup, before app.run(), if you want log output.

    Parameters
    ----------
    level      : logging level for ferogram's own Python-side logger
                 (client.py), e.g. logging.DEBUG / logging.INFO
    fmt        : optional format string, used verbatim with a plain
                 logging.Formatter instead of the default ColorFormatter.
                 Pass this if you want the old one-line
                 "%(asctime)s [%(levelname)s] %(name)s: %(message)s" style
                 or your own layout.
    rust_level : level for the Rust-side loggers - protocol internals like
                 bad_server_salt handling, gap detection, transport framing.
                 Defaults to `level`. Pass e.g. logging.WARNING here to
                 keep that noisy but low-level detail quiet while still
                 seeing your own app's ferogram.* logs at DEBUG.
    color      : force-enable/disable ANSI colors. Defaults to auto-detect
                 (on for a real terminal, off when piped/redirected or
                 NO_COLOR is set) - same as ColorFormatter().
    """
    if _LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    if fmt is not None:
        handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
    else:
        handler.setFormatter(ColorFormatter(color=color))
    _LOG.addHandler(handler)
    _LOG.setLevel(level)

    for name in RUST_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(rust_level if rust_level is not None else level)
        # Each of these is its own tree, separate from "ferogram" - without
        # its own handler it just propagates up to Python's root logger,
        # which (with no handler of its own) silently drops anything below
        # WARNING. Give it the same handler "ferogram" got above instead.
        logger.addHandler(handler)

    _reset_rust_cache()


def get_logger() -> logging.Logger:
    return _LOG


# module-level shortcuts
debug   = _LOG.debug
info    = _LOG.info
warning = _LOG.warning
error   = _LOG.error
