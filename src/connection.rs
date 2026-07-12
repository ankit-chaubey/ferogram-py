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

use base64::Engine as _;
use ferogram_connect::TransportKind;
use ferogram_mtsender::DcConnection as RustConn;
use ferogram_session::{DcEntry, PersistedSession, SessionBackend, default_dc_addresses};
use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use std::sync::Arc;
use tokio::sync::Mutex;

use crate::py_err;
use crate::session::resolve_session;

/// Decode a hex-encoded 16-byte MTProxy secret. No `hex` crate dependency
/// pulled in just for this; it's eight lines of arithmetic.
fn decode_secret16(hex: &str) -> PyResult<[u8; 16]> {
    if hex.len() != 32 {
        return Err(py_err("proxy_secret must be 32 hex chars (16 bytes)"));
    }
    let mut out = [0u8; 16];
    for i in 0..16 {
        out[i] = u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16)
            .map_err(|_| py_err("proxy_secret must be valid hex"))?;
    }
    Ok(out)
}

/// Resolve the wire transport from the name the caller asked for.
///
/// `full` (the Rust core's own default) is used when no transport is
/// given. `proxy_secret` is only consulted for the obfuscated variants.
fn parse_transport(name: Option<&str>, proxy_secret: Option<&str>) -> PyResult<TransportKind> {
    let secret = proxy_secret.map(decode_secret16).transpose()?;
    match name.unwrap_or("full").to_ascii_lowercase().as_str() {
        "full" => Ok(TransportKind::Full),
        "abridged" => Ok(TransportKind::Abridged),
        "intermediate" => Ok(TransportKind::Intermediate),
        "http" => Ok(TransportKind::Http),
        "obfuscated" => Ok(TransportKind::Obfuscated { secret }),
        "padded_intermediate" => Ok(TransportKind::PaddedIntermediate { secret }),
        other => Err(py_err(format!(
            "unknown transport '{other}'; expected one of: full, abridged, intermediate, http, obfuscated, padded_intermediate"
        ))),
    }
}

#[pyclass]
pub struct DcConnection {
    inner: Arc<Mutex<Option<RustConn>>>,
    session: Arc<dyn SessionBackend>,
    persisted: Arc<Mutex<PersistedSession>>,
    #[pyo3(get)]
    dc_id: i32,
}

#[pymethods]
impl DcConnection {
    /// Connect to Telegram. Full DH if no saved key, resume if key exists.
    ///
    /// `dc_id=0` (the default) means "use the session's persisted home DC if
    /// known, otherwise DC2". Pass an explicit `dc_id` to force a specific DC
    /// (e.g. during PHONE_MIGRATE handling).
    ///
    /// `transport` selects the MTProto wire framing: one of "full" (default,
    /// matches the Rust core), "abridged", "intermediate", "http",
    /// "obfuscated", or "padded_intermediate". The last two accept an
    /// optional `proxy_secret` (32 hex chars / 16 bytes) for MTProxy use.
    #[staticmethod]
    #[pyo3(signature = (session, api_id, api_hash, dc_id=0, test_mode=false, transport=None, proxy_secret=None))]
    fn connect<'py>(
        py: Python<'py>,
        session: PyObject,
        api_id: i32,
        api_hash: String,
        dc_id: i16,
        test_mode: bool,
        transport: Option<String>,
        proxy_secret: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let _ = api_id;
        let _ = api_hash;
        let backend = resolve_session(py, &session)?;
        let transport_kind = parse_transport(transport.as_deref(), proxy_secret.as_deref())?;
        future_into_py(py, async move {
            let persisted = backend.load().map_err(py_err)?.unwrap_or_default();

            let dc_id: i16 = if dc_id == 0 {
                if persisted.home_dc_id != 0 {
                    persisted.home_dc_id as i16
                } else {
                    2
                }
            } else {
                dc_id
            };

            let addrs = if test_mode {
                [
                    (1, "149.154.167.40:443"),
                    (2, "149.154.167.41:443"),
                    (3, "149.154.175.117:443"),
                ]
                .iter()
                .map(|(id, a)| (*id as i32, a.to_string()))
                .collect::<std::collections::HashMap<_, _>>()
            } else {
                default_dc_addresses()
            };

            let dc_addr = persisted
                .dcs
                .iter()
                .find(|d| d.dc_id == dc_id as i32)
                .map(|d| d.addr.clone())
                .unwrap_or_else(|| {
                    addrs
                        .get(&(dc_id as i32))
                        .cloned()
                        .unwrap_or_else(|| "149.154.167.51:443".to_string())
                });

            let existing_key = persisted
                .dcs
                .iter()
                .find(|d| d.dc_id == dc_id as i32)
                .and_then(|d| d.auth_key);

            let (conn, new_key, first_salt, time_offset) = match existing_key {
                Some(key) => {
                    let entry = persisted
                        .dcs
                        .iter()
                        .find(|d| d.dc_id == dc_id as i32)
                        .unwrap();
                    let c = RustConn::connect_with_key(
                        &dc_addr,
                        key,
                        entry.first_salt,
                        entry.time_offset,
                        None,
                        None,
                        &transport_kind,
                        dc_id,
                        false,
                    )
                    .await
                    .map_err(py_err)?;
                    (c, key, entry.first_salt, entry.time_offset)
                }
                None => {
                    let c = tokio::time::timeout(
                        std::time::Duration::from_secs(30),
                        RustConn::connect_raw(&dc_addr, None, &transport_kind, dc_id),
                    )
                    .await
                    .map_err(|_| py_err("connect timed out after 30s"))?
                    .map_err(py_err)?;
                    let key = c.auth_key_bytes();
                    let salt = c.first_salt();
                    let toff = c.time_offset();
                    (c, key, salt, toff)
                }
            };

            let mut updated = persisted;
            {
                let dc_id_i32 = dc_id as i32;
                if let Some(entry) = updated.dcs.iter_mut().find(|d| d.dc_id == dc_id_i32) {
                    entry.auth_key = Some(new_key);
                    entry.first_salt = first_salt;
                    entry.time_offset = time_offset;
                    entry.addr = dc_addr;
                } else {
                    updated.dcs.push(DcEntry {
                        dc_id: dc_id_i32,
                        addr: dc_addr,
                        auth_key: Some(new_key),
                        first_salt,
                        time_offset,
                        flags: Default::default(),
                    });
                }
            }
            if updated.home_dc_id == 0 {
                updated.home_dc_id = dc_id as i32;
            }
            backend.save(&updated).map_err(py_err)?;

            Ok(DcConnection {
                inner: Arc::new(Mutex::new(Some(conn))),
                session: backend,
                persisted: Arc::new(Mutex::new(updated)),
                dc_id: dc_id as i32,
            })
        })
    }

    /// Send pre-serialized TL bytes through the encrypted MTProto channel.
    fn rpc_call<'py>(&self, py: Python<'py>, tl_bytes: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut guard = inner.lock().await;
            let conn = guard.as_mut().ok_or_else(|| {
                py_err("connection was consumed by into_pipelined_sender()")
            })?;
            let result = conn
                .rpc_call(&crate::raw::RawCall(tl_bytes))
                .await
                .map_err(py_err)?;
            Ok(result)
        })
    }

    /// Consume this connection and graduate it into a pipelined transfer
    /// sender: X > 1 chunk requests can be enqueued and in flight on the
    /// same socket at once, instead of `rpc_call`'s one-at-a-time blocking
    /// model. Mirrors ferogram's Rust `Client::open_worker_sender`.
    ///
    /// After this call, `rpc_call`/`auth_key_bytes` on this `DcConnection`
    /// will raise  - the socket now belongs to the returned
    /// `PipelinedSender`. Only call this on a connection you opened
    /// specifically for a transfer worker (e.g. via `_open_worker_conn`),
    /// never on the main session connection.
    fn into_pipelined_sender<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut guard = inner.lock().await;
            let conn = guard
                .take()
                .ok_or_else(|| py_err("connection already consumed"))?;
            drop(guard);
            let (stream, frame_kind, enc) = conn.into_parts();
            let sender = ferogram_mtsender::spawn_pipelined(stream, enc, frame_kind, None);
            Ok(crate::pipelined::PyPipelinedSender::new(sender))
        })
    }

    /// Persist current session state.
    fn save_session<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let session = Arc::clone(&self.session);
        let persisted = Arc::clone(&self.persisted);
        future_into_py(py, async move {
            let p = persisted.lock().await;
            session.save(&p).map_err(py_err)
        })
    }

    /// Export session as a base64 string.
    fn export_string<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let persisted = Arc::clone(&self.persisted);
        future_into_py(py, async move {
            let p = persisted.lock().await;
            Ok(base64::engine::general_purpose::STANDARD.encode(p.to_bytes()))
        })
    }

    /// Update the auth key stored in the persisted session (used after DC migration).
    fn update_auth_key<'py>(
        &self,
        py: Python<'py>,
        dc_id: i32,
        auth_key: Vec<u8>,
        first_salt: i64,
        time_offset: i32,
        addr: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let persisted = Arc::clone(&self.persisted);
        let session = Arc::clone(&self.session);
        future_into_py(py, async move {
            let key_arr: [u8; 256] = auth_key
                .try_into()
                .map_err(|_| py_err("auth_key must be exactly 256 bytes"))?;
            let mut p = persisted.lock().await;
            if let Some(entry) = p.dcs.iter_mut().find(|d| d.dc_id == dc_id) {
                entry.auth_key = Some(key_arr);
                entry.first_salt = first_salt;
                entry.time_offset = time_offset;
                entry.addr = addr;
            } else {
                p.dcs.push(DcEntry {
                    dc_id,
                    addr,
                    auth_key: Some(key_arr),
                    first_salt,
                    time_offset,
                    flags: Default::default(),
                });
            }
            session.save(&*p).map_err(py_err)?;
            Ok(())
        })
    }

    /// Mark `dc_id` as the session's home DC and persist immediately.
    /// Call this after a successful sign-in: the DC the user authenticated
    /// on becomes authoritative for reconnects, regardless of which DC the
    /// initial connection happened to land on.
    fn set_home_dc<'py>(&self, py: Python<'py>, dc_id: i32) -> PyResult<Bound<'py, PyAny>> {
        let persisted = Arc::clone(&self.persisted);
        let session = Arc::clone(&self.session);
        future_into_py(py, async move {
            let mut p = persisted.lock().await;
            if p.home_dc_id != dc_id {
                p.home_dc_id = dc_id;
                session.save(&*p).map_err(py_err)?;
            }
            Ok(())
        })
    }

    /// Future auth token captured from a previous `sign_out()`, if any.
    /// Replay it in `auth.sendCode`'s `logout_tokens` to skip code entry on
    /// the next login. Persists across restarts (session format v7+).
    fn get_future_auth_token<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let persisted = Arc::clone(&self.persisted);
        future_into_py(py, async move {
            let p = persisted.lock().await;
            Ok(p.future_auth_token.clone())
        })
    }

    /// Store (or clear, with `None`) the future auth token and persist
    /// immediately. `sign_out()` calls this with the token Telegram returns;
    /// a successful fast re-auth via `sentCodeSuccess` calls it with `None`
    /// since a used token shouldn't be replayed again.
    fn set_future_auth_token<'py>(
        &self,
        py: Python<'py>,
        token: Option<Vec<u8>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let persisted = Arc::clone(&self.persisted);
        let session = Arc::clone(&self.session);
        future_into_py(py, async move {
            let mut p = persisted.lock().await;
            p.future_auth_token = token;
            session.save(&*p).map_err(py_err)?;
            Ok(())
        })
    }

    /// Current auth key bytes for this connection (256 bytes).
    fn auth_key_bytes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let guard = inner.lock().await;
            let conn = guard.as_ref().ok_or_else(|| {
                py_err("connection was consumed by into_pipelined_sender()")
            })?;
            Ok(conn.auth_key_bytes().to_vec())
        })
    }

    fn __repr__(&self) -> String {
        "DcConnection(...)".into()
    }
}
