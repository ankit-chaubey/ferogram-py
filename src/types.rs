// Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
// SPDX-License-Identifier: MIT OR Apache-2.0
//
// ferogram is a high-performance Telegram MTProto framework written in Rust.
// ferogram-py provides Python bindings built on top of the Rust core for
// building Telegram clients, bots, and applications with a simple API.
//
// Rust core: https://github.com/ankit-chaubey/ferogram
// Python bindings: https://github.com/ankit-chaubey/ferogram-py
//
// If you use or modify this code, keep this notice at the top of the file
// and include the LICENSE-MIT or LICENSE-APACHE file from this repository.

// Simple data types returned from account/dialog calls.

use pyo3::prelude::*;

#[pyclass]
pub struct User {
    #[pyo3(get)] pub id: i64,
    #[pyo3(get)] pub first_name: String,
    #[pyo3(get)] pub last_name: Option<String>,
    #[pyo3(get)] pub username: Option<String>,
    #[pyo3(get)] pub phone: Option<String>,
    #[pyo3(get)] pub bot: bool,
}

#[pymethods]
impl User {
    fn __repr__(&self) -> String {
        format!("User(id={}, username={:?}, first_name={:?})", self.id, self.username, self.first_name)
    }
}

#[pyclass]
pub struct Dialog {
    #[pyo3(get)] pub title: String,
    #[pyo3(get)] pub unread_count: i32,
    #[pyo3(get)] pub top_message: i32,
}

#[pymethods]
impl Dialog {
    fn __repr__(&self) -> String {
        format!("Dialog(title={:?}, unread={})", self.title, self.unread_count)
    }
}
