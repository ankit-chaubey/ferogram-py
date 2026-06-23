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

pub mod connection;
pub mod raw;
pub mod session;
pub mod srp;

pub fn py_err(e: impl std::fmt::Display) -> PyErr {
    pyo3::exceptions::PyRuntimeError::new_err(e.to_string())
}

#[pymodule]
fn _ferogram(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<connection::DcConnection>()?;
    m.add_class::<session::FileSession>()?;
    m.add_class::<session::MemorySession>()?;
    m.add_class::<session::StringSession>()?;
    m.add_class::<session::SqliteSession>()?;
    m.add_class::<session::LibSqlSession>()?;
    m.add_class::<session::CustomSession>()?;
    m.add_function(wrap_pyfunction!(srp::srp_calculate, m)?)?;
    Ok(())
}
