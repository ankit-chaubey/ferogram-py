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
    #[pyo3(get, set)]
    pub api_id: i32,
    #[pyo3(get, set)]
    pub api_hash: String,
    #[pyo3(get, set)]
    pub session: String,
    #[pyo3(get, set)]
    pub allow_zero_hash: bool,
    #[pyo3(get, set)]
    pub proxy: Option<String>,
    #[pyo3(get, set)]
    pub allow_ipv6: bool,
    #[pyo3(get, set)]
    pub dc_addr: Option<String>,
    #[pyo3(get, set)]
    pub probe_transport: bool,
    #[pyo3(get, set)]
    pub resilient_connect: bool,
    #[pyo3(get, set)]
    pub catch_up: bool,
    #[pyo3(get, set)]
    pub pfs: bool,
    #[pyo3(get, set)]
    pub device_model: Option<String>,
    #[pyo3(get, set)]
    pub system_version: Option<String>,
    #[pyo3(get, set)]
    pub app_version: Option<String>,
    #[pyo3(get, set)]
    pub lang_code: Option<String>,
    #[pyo3(get, set)]
    pub system_lang_code: Option<String>,
    #[pyo3(get, set)]
    pub lang_pack: Option<String>,
    #[pyo3(get, set)]
    pub session_string: Option<String>,
    #[pyo3(get, set)]
    pub in_memory: bool,
    #[pyo3(get, set)]
    pub update_queue_capacity: Option<usize>,
    #[pyo3(get, set)]
    pub update_overflow: Option<String>,
    #[pyo3(get, set)]
    pub low_memory_mode: bool,
    #[pyo3(get, set)]
    pub allow_missing_channel_hash: bool,
    #[pyo3(get, set)]
    pub auto_resolve_peers: bool,
}

#[pymethods]
impl ClientBuilder {
    fn experimental_allow_zero_hash(mut slf: PyRefMut<'_, Self>) -> PyRefMut<'_, Self> {
        slf.allow_zero_hash = true;
        slf
    }

    fn connect<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let api_id = self.api_id;
        let api_hash = self.api_hash.clone();
        let session_path = self.session.clone();
        let allow_zero_hash = self.allow_zero_hash;
        let proxy = self.proxy.clone();
        let allow_ipv6 = self.allow_ipv6;
        let dc_addr = self.dc_addr.clone();
        let probe_transport = self.probe_transport;
        let resilient_connect = self.resilient_connect;
        let catch_up = self.catch_up;
        let pfs = self.pfs;
        let device_model = self.device_model.clone();
        let system_version = self.system_version.clone();
        let app_version = self.app_version.clone();
        let lang_code = self.lang_code.clone();
        let system_lang_code = self.system_lang_code.clone();
        let lang_pack = self.lang_pack.clone();
        let session_string = self.session_string.clone();
        let in_memory = self.in_memory;
        let update_queue_capacity = self.update_queue_capacity;
        let update_overflow = self.update_overflow.clone();
        let low_memory_mode = self.low_memory_mode;
        let allow_missing_channel_hash = self.allow_missing_channel_hash;
        let auto_resolve_peers = self.auto_resolve_peers;

        future_into_py(py, async move {
            let mut builder = ferogram::Client::builder()
                .api_id(api_id)
                .api_hash(api_hash);

            if in_memory {
                builder = builder.in_memory();
            } else if let Some(s) = session_string {
                builder = builder.session_string(s);
            } else {
                builder = builder.session(session_path);
            }

            if let Some(p) = &proxy {
                if p.starts_with("socks5://") {
                    let addr = p.trim_start_matches("socks5://");
                    builder = builder.socks5(addr);
                } else if p.starts_with("https://t.me/proxy") || p.starts_with("tg://proxy") {
                    builder = builder.proxy_link(p);
                } else {
                    return Err(py_err(
                        "proxy must start with socks5://, https://t.me/proxy, or tg://proxy",
                    ));
                }
            }

            if allow_ipv6 {
                builder = builder.allow_ipv6(true);
            }
            if let Some(a) = dc_addr {
                builder = builder.dc_addr(a);
            }
            if probe_transport {
                builder = builder.probe_transport(true);
            }
            if resilient_connect {
                builder = builder.resilient_connect(true);
            }
            if catch_up {
                builder = builder.catch_up(true);
            }
            if pfs {
                builder = builder.pfs(true);
            }

            if let Some(v) = device_model {
                builder = builder.device_model(v);
            }
            if let Some(v) = system_version {
                builder = builder.system_version(v);
            }
            if let Some(v) = app_version {
                builder = builder.app_version(v);
            }
            if let Some(v) = lang_code {
                builder = builder.lang_code(v);
            }
            if let Some(v) = system_lang_code {
                builder = builder.system_lang_code(v);
            }
            if let Some(v) = lang_pack {
                builder = builder.lang_pack(v);
            }

            if low_memory_mode {
                builder = builder.low_memory_mode(true);
            } else {
                if let Some(cap) = update_queue_capacity {
                    builder = builder.update_queue_capacity(cap);
                }
                if let Some(ref s) = update_overflow {
                    let strategy = match s.as_str() {
                        "drop_oldest" => ferogram::OverflowStrategy::DropOldest,
                        "drop_newest" => ferogram::OverflowStrategy::DropNewest,
                        other => {
                            return Err(py_err(format!(
                                "update_overflow must be 'drop_oldest' or 'drop_newest', got {other:?}"
                            )));
                        }
                    };
                    builder = builder.update_overflow_strategy(strategy);
                }
            }

            builder = builder.experimental_features(ferogram::ExperimentalFeatures {
                allow_zero_hash,
                allow_missing_channel_hash,
                auto_resolve_peers,
            });

            let (client, shutdown) = builder.connect().await.map_err(py_err)?;
            Ok(crate::client::make_client(client, shutdown))
        })
    }
}
