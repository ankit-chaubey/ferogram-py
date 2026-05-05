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

use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use std::sync::{Arc, Mutex};

use crate::py_err;

#[pyclass(frozen)]
pub struct LoginToken(pub Arc<Mutex<Option<ferogram::LoginToken>>>);

#[pyclass(frozen)]
pub struct PasswordToken {
    pub inner: Arc<Mutex<Option<ferogram::PasswordToken>>>,
    pub hint: Option<String>,
}

#[pymethods]
impl PasswordToken {
    #[getter]
    fn hint(&self) -> Option<&str> {
        self.hint.as_deref()
    }
    fn __repr__(&self) -> String {
        match &self.hint {
            Some(h) => format!("PasswordToken(hint={h:?})"),
            None => "PasswordToken(hint=None)".into(),
        }
    }
}

#[pyclass]
pub struct ClientBuilder {
    pub api_id: i32,
    pub api_hash: String,
    pub session: String,
    pub allow_zero_hash: bool,
}

#[pymethods]
impl ClientBuilder {
    /// For bots only: skip needing a cached access hash.
    /// Do NOT enable on user accounts.
    fn experimental_allow_zero_hash(mut slf: PyRefMut<'_, Self>) -> PyRefMut<'_, Self> {
        slf.allow_zero_hash = true;
        slf
    }

    fn connect<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let (api_id, api_hash, session, allow_zero_hash) = (
            self.api_id,
            self.api_hash.clone(),
            self.session.clone(),
            self.allow_zero_hash,
        );
        future_into_py(py, async move {
            let mut builder = ferogram::Client::builder()
                .api_id(api_id)
                .api_hash(api_hash)
                .session(session);
            if allow_zero_hash {
                builder = builder.experimental_features(ferogram::ExperimentalFeatures {
                    allow_zero_hash: true,
                    ..Default::default()
                });
            }
            let (client, shutdown) = builder.connect().await.map_err(py_err)?;
            Ok(crate::client::make_client(client, shutdown))
        })
    }
}
