// Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
//
// ferogram: async Telegram MTProto client in Rust
// https://github.com/ankit-chaubey/ferogram
//
// Licensed under either the MIT License or the Apache License 2.0.
// See the LICENSE-MIT or LICENSE-APACHE file in this repository:
// https://github.com/ankit-chaubey/ferogram
//
// Feel free to use, modify, and share this code.
// Please keep this notice when redistributing.

use pyo3::prelude::*;
use std::sync::OnceLock;

pub mod connection;
pub mod message_box;
pub mod pipelined;
pub mod raw;
pub mod session;
pub mod srp;

pub fn py_err(e: impl std::fmt::Display) -> PyErr {
    pyo3::exceptions::PyRuntimeError::new_err(e.to_string())
}

/// Handle to pyo3-log's internal cache, stashed away by `init_logging_bridge`
/// so `reset_logging_cache()` below can reach it. `OnceLock` rather than a
/// plain `Option` behind a mutex because it's write-once (set right after
/// `install()` succeeds) and read-often (every call to `reset_logging_cache`).
static LOG_RESET: OnceLock<pyo3_log::ResetHandle> = OnceLock::new();

/// Bridges Rust's `log`/`tracing` output into Python's `logging` module.
///
/// ferogram-mtsender, ferogram-msgbox, ferogram-connect, ferogram-mtproto,
/// ferogram-crypto, and ferogram-session all emit
/// `tracing::debug!/info!/warn!/trace!` events (FLOOD_WAIT sleeps,
/// bad_server_salt handling, reconnects, msgbox gap detection, PFS bind,
/// and so on). Those crates enable tracing's `log` feature, which makes
/// tracing forward every event through the `log` facade whenever no
/// `tracing::Subscriber` is installed - which is always true here, since
/// this module never sets one up. Without a `log::Log` implementation
/// registered, those forwarded records had nowhere to go and were
/// silently dropped.
///
/// `pyo3_log` supplies that `log::Log` implementation: it turns each
/// record's Rust target (e.g. "ferogram_mtsender::sender") into a Python
/// logger name (e.g. "ferogram_mtsender.sender") via dot-replacement, and
/// forwards it there at a matching level. Configure it the same way you'd
/// configure any Python logger, e.g.:
///
///     import logging
///     logging.getLogger("ferogram_mtsender").setLevel(logging.DEBUG)
///     logging.basicConfig(level=logging.DEBUG)
///
/// The Rust-side filter is set to Trace so nothing is dropped before it
/// reaches Python; Python's own per-logger level check (cheap, and already
/// happening for every stdlib log call) is what actually decides whether a
/// given record does any work. To keep that check cheap, pyo3-log *caches*
/// each target's resolved Python level instead of asking Python on every
/// single log call - see `reset_logging_cache()` below for the gotcha that
/// comes with that.
fn init_logging_bridge(py: Python<'_>) {
    match pyo3_log::Logger::new(py, pyo3_log::Caching::LoggersAndLevels) {
        Ok(logger) => match logger.filter(log::LevelFilter::Trace).install() {
            Ok(handle) => {
                // Only fails if the bridge was already installed earlier in
                // this process (e.g. the module was reloaded) - fine to
                // ignore, the existing handle is still live and usable.
                let _ = LOG_RESET.set(handle);
            }
            Err(e) => {
                // Only fails if a `log::Logger` is already installed - not
                // fatal, just means the bridge from an earlier import (or a
                // different native extension) is still active.
                eprintln!("ferogram: logging bridge already installed: {e}");
            }
        },
        Err(e) => eprintln!("ferogram: failed to initialize logging bridge: {e}"),
    }
}

/// Clears pyo3-log's cached "what Python level is this Rust target enabled
/// for" lookups.
///
/// Each Rust target's effective Python log level is resolved once (on its
/// first log call) and cached from then on, so that later calls don't have
/// to take the GIL and ask Python again. The downside: if you change a
/// logger's level *after* it has already logged something - e.g. calling
/// `logging.getLogger("ferogram_mtsender").setLevel(logging.DEBUG)` mid-run,
/// or reconfiguring logging entirely - the cached entry doesn't know that
/// happened, and log lines you just enabled can appear to stay silent.
/// Call this right after any such change to make it take effect
/// immediately. `ferogram.logging.setup()` already calls this for you.
#[pyfunction]
fn reset_logging_cache() {
    if let Some(handle) = LOG_RESET.get() {
        handle.reset();
    }
}

#[pymodule]
fn _ferogram(m: &Bound<'_, PyModule>) -> PyResult<()> {
    init_logging_bridge(m.py());
    m.add_class::<connection::DcConnection>()?;
    m.add_class::<message_box::PyMessageBox>()?;
    m.add_class::<pipelined::PyPipelinedSender>()?;
    m.add_class::<pipelined::PyPipelinedRequest>()?;
    m.add_class::<session::FileSession>()?;
    m.add_class::<session::MemorySession>()?;
    m.add_class::<session::StringSession>()?;
    m.add_class::<session::SqliteSession>()?;
    m.add_class::<session::LibSqlSession>()?;
    m.add_class::<session::CustomSession>()?;
    m.add_function(wrap_pyfunction!(srp::srp_calculate, m)?)?;
    m.add_function(wrap_pyfunction!(reset_logging_cache, m)?)?;
    Ok(())
}
