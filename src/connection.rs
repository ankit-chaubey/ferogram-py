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
use ferogram_connect::{Socks5Config, TransportKind};
use ferogram_msgbox::MessageBoxes;
use ferogram_mtsender::{
    AutoSleep, DcConnection as RustConn, FrameEvent, RetryLoop, RpcEnqueue, spawn_sender_task,
};
use ferogram_session::{DcEntry, PersistedSession, SessionBackend, default_dc_addresses};
use ferogram_tl_types::Deserializable;
use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{Mutex, mpsc, oneshot};

use crate::message_box::PyMessageBox;
use crate::py_err;
use crate::session::resolve_session;

/// Parse a `"host:port"` / `"user:pass@host:port"` proxy string into a
/// [`Socks5Config`]. This is SOCKS5 routing only - separate from
/// `proxy_secret`, which just configures MTProxy wire obfuscation and
/// doesn't route through a relay at all.
fn parse_socks5(proxy: &str) -> PyResult<Socks5Config> {
    let proxy = proxy.strip_prefix("socks5://").unwrap_or(proxy);
    match proxy.split_once('@') {
        Some((creds, addr)) => {
            let (user, pass) = creds
                .split_once(':')
                .ok_or_else(|| py_err("proxy credentials must be 'user:pass@host:port'"))?;
            Ok(Socks5Config::with_auth(addr, user, pass))
        }
        None => Ok(Socks5Config::new(proxy)),
    }
}

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
/// given. `proxy_secret` is consulted for the obfuscated variants and is
/// mandatory (not just optional) for `faketls`, since
/// `TransportKind::FakeTls` has no keyless form. `domain` is only used (and
/// required) for `faketls` - it's the SNI hostname presented in the fake
/// TLS ClientHello, unrelated to `proxy_secret`.
/// `"fastest"` is handled by the caller before this function is reached -
/// it isn't a real `TransportKind`, it's a race between a couple of them.
fn parse_transport(
    name: Option<&str>,
    proxy_secret: Option<&str>,
    domain: Option<&str>,
) -> PyResult<TransportKind> {
    let secret = proxy_secret.map(decode_secret16).transpose()?;
    match name.unwrap_or("full").to_ascii_lowercase().as_str() {
        "full" => Ok(TransportKind::Full),
        "abridged" => Ok(TransportKind::Abridged),
        "intermediate" => Ok(TransportKind::Intermediate),
        "http" => Ok(TransportKind::Http),
        "obfuscated" => Ok(TransportKind::Obfuscated { secret }),
        "padded_intermediate" => Ok(TransportKind::PaddedIntermediate { secret }),
        "faketls" | "fake_tls" => {
            let secret = secret.ok_or_else(|| {
                py_err("transport 'faketls' requires proxy_secret (32 hex chars / 16 bytes)")
            })?;
            let domain = domain
                .filter(|d| !d.is_empty())
                .ok_or_else(|| {
                    py_err("transport 'faketls' requires domain (the SNI hostname to present)")
                })?
                .to_string();
            Ok(TransportKind::FakeTls { secret, domain })
        }
        other => Err(py_err(format!(
            "unknown transport '{other}'; expected one of: full, abridged, intermediate, http, obfuscated, padded_intermediate, faketls, fastest"
        ))),
    }
}

#[pyclass]
pub struct DcConnection {
    /// `Some` only when this connection is in the default "blocking" mode
    /// (see `connect(stream_updates=...)`): a raw connection that owns the
    /// socket directly and is read from only while `rpc_call` is awaiting
    /// its own response. `into_pipelined_sender()`/`auth_key_bytes()` only
    /// work in this mode.
    inner: Arc<Mutex<Option<RustConn>>>,
    /// `Some` only in "streaming" mode: RPCs are enqueued to the sender
    /// task's background loop instead of blocking this object's own socket
    /// read. This is what lets pushed (server-initiated) update frames get
    /// read at all, since the sender task's read loop runs continuously
    /// instead of only while an RPC is outstanding.
    rpc_tx: std::sync::Mutex<Option<mpsc::Sender<RpcEnqueue>>>,
    /// `Some` only in streaming mode: pushed frames (updates, reconnect
    /// signals, errors) land here. Drained via `recv_frame()`.
    frame_rx: Arc<Mutex<Option<mpsc::Receiver<FrameEvent>>>>,
    session: Arc<dyn SessionBackend>,
    persisted: Arc<Mutex<PersistedSession>>,
    #[pyo3(get)]
    dc_id: i32,
    /// Max FLOOD_WAIT this connection will sleep through automatically in
    /// `rpc_call` before giving up and propagating the error. Seconds.
    flood_sleep_threshold: u64,
    /// Set via `bind_message_box()`. When present, every successful
    /// `rpc_call` response is auto-fed into it (mirrors the Rust core's
    /// `Client::feed_own_updates`). `None` means responses are returned
    /// as-is with no update tracking applied.
    message_box: std::sync::Mutex<Option<Arc<Mutex<MessageBoxes>>>>,
}

impl DcConnection {
    /// Streaming-mode RPC: enqueue pre-serialized TL bytes to the sender
    /// task and await its oneshot response. One request in flight per call
    /// (same shape as blocking `rpc_call`) - the sender task itself already
    /// supports many callers enqueuing concurrently if that's ever needed.
    async fn enqueue_streaming(
        rpc_tx: &mpsc::Sender<RpcEnqueue>,
        body: Vec<u8>,
    ) -> Result<Vec<u8>, ferogram_mtsender::InvocationError> {
        let (tx, rx) = oneshot::channel();
        rpc_tx
            .send(RpcEnqueue { body, tx })
            .await
            .map_err(|_| ferogram_mtsender::InvocationError::Dropped)?;
        rx.await
            .map_err(|_| ferogram_mtsender::InvocationError::Dropped)?
    }
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
    /// "obfuscated", "padded_intermediate", or "faketls". "obfuscated" and
    /// "padded_intermediate" accept an optional `proxy_secret` (32 hex
    /// chars / 16 bytes) for MTProxy use. "faketls" requires both
    /// `proxy_secret` (mandatory, not optional, for this transport) and
    /// `domain` - the SNI hostname presented in the fake TLS ClientHello.
    ///
    /// Pass `"fastest"` to race a couple of the core's built-in transports
    /// (full + obfuscated) in parallel and keep whichever completes the DH
    /// handshake first - this only kicks in when there's no saved auth key
    /// yet, since a resumed connection already knows which transport it's
    /// on. `proxy_secret`/`domain` are ignored in this mode, since the race
    /// doesn't carry either through to its legs.
    ///
    /// `proxy` is a SOCKS5 relay, `"host:port"` or `"user:pass@host:port"`
    /// (an optional `socks5://` prefix is stripped). This is routing, not
    /// wire obfuscation - unrelated to `proxy_secret`/`transport`/`domain`.
    ///
    /// `pfs` requests a temp-key DH bind on top of a resumed (saved-key)
    /// connection. It has no effect on a fresh handshake, which already
    /// establishes a permanent key from scratch.
    ///
    /// `dc_addr` overrides the address this connects to, bypassing both
    /// the persisted session's saved address and the built-in DC table.
    ///
    /// `flood_sleep_threshold` (seconds) is the longest FLOOD_WAIT
    /// `rpc_call` will sleep through automatically before giving up and
    /// raising. Longer waits are propagated immediately.
    #[staticmethod]
    #[pyo3(signature = (
        session, api_id, api_hash, dc_id=0, test_mode=false, transport=None,
        proxy_secret=None, domain=None, proxy=None, pfs=false, dc_addr=None, flood_sleep_threshold=60,
        stream_updates=false
    ))]
    #[allow(clippy::too_many_arguments)]
    fn connect<'py>(
        py: Python<'py>,
        session: PyObject,
        api_id: i32,
        api_hash: String,
        dc_id: i16,
        test_mode: bool,
        transport: Option<String>,
        proxy_secret: Option<String>,
        domain: Option<String>,
        proxy: Option<String>,
        pfs: bool,
        dc_addr: Option<String>,
        flood_sleep_threshold: u64,
        // `False` (default): the connection stays in "blocking" mode -
        // the only mode `into_pipelined_sender()` (used by file-transfer
        // worker connections) supports.
        //
        // `True`: for the main session connection. Hands the socket to
        // `ferogram_mtsender::spawn_sender_task` right after the handshake
        // below, so a background loop keeps reading it continuously
        // instead of only while `rpc_call` has a request in flight. That
        // continuous read is what surfaces server-pushed update frames -
        // without it, updates are only discoverable via the periodic
        // `getDifference` poll, which can lag by up to `NO_UPDATES_TIMEOUT`
        // (15 min). See `recv_frame()`.
        stream_updates: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let _ = api_id;
        let _ = api_hash;
        let backend = resolve_session(py, &session)?;
        let use_fastest = transport
            .as_deref()
            .is_some_and(|t| t.eq_ignore_ascii_case("fastest"));
        // "fastest" only applies to a fresh DH handshake (the `None` branch
        // below); a resumed connection with a saved key still needs one
        // concrete TransportKind, so fall back to the core's own default.
        let transport_kind = if use_fastest {
            TransportKind::Full
        } else {
            parse_transport(
                transport.as_deref(),
                proxy_secret.as_deref(),
                domain.as_deref(),
            )?
        };
        let socks5 = proxy.as_deref().map(parse_socks5).transpose()?;
        let addr_override = dc_addr;
        future_into_py(py, async move {
            // SessionBackend::load/save are synchronous, blocking calls
            // (SQLite, file I/O, ...). Running them straight on this task
            // would stall a tokio worker thread for the duration of the
            // disk I/O, same bug the Rust core fixed in Client::save_session.
            // Every backend call in this file goes through spawn_blocking.
            let load_backend = Arc::clone(&backend);
            let persisted = tokio::task::spawn_blocking(move || load_backend.load())
                .await
                .map_err(py_err)?
                .map_err(py_err)?
                .unwrap_or_default();

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

            let dc_addr = addr_override.unwrap_or_else(|| {
                persisted
                    .dcs
                    .iter()
                    .find(|d| d.dc_id == dc_id as i32)
                    .map(|d| d.addr.clone())
                    .unwrap_or_else(|| {
                        addrs
                            .get(&(dc_id as i32))
                            .cloned()
                            .unwrap_or_else(|| "149.154.167.51:443".to_string())
                    })
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
                        socks5.as_ref(),
                        None,
                        &transport_kind,
                        dc_id,
                        pfs,
                    )
                    .await
                    .map_err(py_err)?;
                    (c, key, entry.first_salt, entry.time_offset)
                }
                None => {
                    let c = if use_fastest {
                        // connect_fastest only takes socks5 (no mtproxy leg,
                        // no transport - it races its own built-in set), and
                        // returns the winning transport's debug label, which
                        // we don't have a use for here.
                        tokio::time::timeout(
                            std::time::Duration::from_secs(30),
                            RustConn::connect_fastest(&dc_addr, socks5.as_ref(), dc_id),
                        )
                        .await
                        .map_err(|_| py_err("connect timed out after 30s"))?
                        .map_err(py_err)?
                        .0
                    } else {
                        tokio::time::timeout(
                            std::time::Duration::from_secs(30),
                            // mtproxy isn't wired up to a Python param yet, see comment above
                            RustConn::connect_raw(
                                &dc_addr,
                                socks5.as_ref(),
                                None,
                                &transport_kind,
                                dc_id,
                            ),
                        )
                        .await
                        .map_err(|_| py_err("connect timed out after 30s"))?
                        .map_err(py_err)?
                    };
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
            let save_backend = Arc::clone(&backend);
            let to_save = updated.clone();
            tokio::task::spawn_blocking(move || save_backend.save(&to_save))
                .await
                .map_err(py_err)?
                .map_err(py_err)?;

            if stream_updates {
                // Hand the socket to the sender task's own read loop. From
                // here on `conn` (the blocking RustConn) no longer exists -
                // rpc_call goes through `rpc_tx`/oneshot instead, and pushed
                // frames land in `frame_rx` for `recv_frame()` to drain.
                let (stream, frame_kind, enc) = conn.into_parts();
                let (handle, frame_rx) = spawn_sender_task(stream, enc, frame_kind, None);
                Ok(DcConnection {
                    inner: Arc::new(Mutex::new(None)),
                    rpc_tx: std::sync::Mutex::new(Some(handle.rpc_tx)),
                    frame_rx: Arc::new(Mutex::new(Some(frame_rx))),
                    session: backend,
                    persisted: Arc::new(Mutex::new(updated)),
                    dc_id: dc_id as i32,
                    flood_sleep_threshold,
                    message_box: std::sync::Mutex::new(None),
                })
            } else {
                Ok(DcConnection {
                    inner: Arc::new(Mutex::new(Some(conn))),
                    rpc_tx: std::sync::Mutex::new(None),
                    frame_rx: Arc::new(Mutex::new(None)),
                    session: backend,
                    persisted: Arc::new(Mutex::new(updated)),
                    dc_id: dc_id as i32,
                    flood_sleep_threshold,
                    message_box: std::sync::Mutex::new(None),
                })
            }
        })
    }

    /// Bind a `MessageBox` so every future `rpc_call` response is
    /// auto-fed into it - mirrors the Rust core's `feed_own_updates`, using
    /// the same `classify_own_response()` classifier under the hood.
    ///
    /// Call this once after `connect()`. If you reconnect/migrate to a new
    /// `DcConnection` (e.g. `_migrate()`'s DC-switch), call it again on the
    /// new connection with the *same* `MessageBox` object to keep tracking
    /// state across the switch - `MessageBox` owns the state, not
    /// `DcConnection`, so nothing is lost.
    fn bind_message_box(&self, mbox: &PyMessageBox) {
        *self.message_box.lock().expect("message_box mutex poisoned") = Some(mbox.shared());
    }

    /// Send pre-serialized TL bytes through the encrypted MTProto channel.
    /// Automatically sleeps through FLOOD_WAIT up to `flood_sleep_threshold`
    /// (set at `connect()` time); longer waits, and anything else, propagate
    /// straight to the caller.
    ///
    /// If a `MessageBox` is bound (via `bind_message_box`), the response is
    /// transparently classified and fed into it before returning - callers
    /// don't need to do anything extra for the common case (updates carried
    /// piggyback on a normal RPC response, e.g. `sendMessage` returning the
    /// new message's `Updates`).
    fn rpc_call<'py>(&self, py: Python<'py>, tl_bytes: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        let rpc_tx = self.rpc_tx.lock().expect("rpc_tx mutex poisoned").clone();
        let threshold = self.flood_sleep_threshold;
        let mbox = self
            .message_box
            .lock()
            .expect("message_box mutex poisoned")
            .clone();
        future_into_py(py, async move {
            let policy = Arc::new(AutoSleep {
                threshold: Duration::from_secs(threshold),
                io_errors_as_flood_of: Some(Duration::from_secs(1)),
            });
            let mut retries = RetryLoop::new(policy);
            loop {
                let result = if let Some(rpc_tx) = &rpc_tx {
                    Self::enqueue_streaming(rpc_tx, tl_bytes.clone()).await
                } else {
                    let mut guard = inner.lock().await;
                    let conn = guard.as_mut().ok_or_else(|| {
                        py_err("connection was consumed by into_pipelined_sender()")
                    })?;
                    let r = conn.rpc_call(&crate::raw::RawCall(tl_bytes.clone())).await;
                    drop(guard);
                    r
                };
                match result {
                    Ok(result) => {
                        if let Some(mbox) = &mbox {
                            if let Some(parsed) = ferogram_msgbox::classify_own_response(&result) {
                                let _ = mbox.lock().await.process_updates(parsed);
                            }
                        }
                        return Ok(result);
                    }
                    Err(e) => {
                        retries.advance(e).await.map_err(py_err)?;
                    }
                }
            }
        })
    }

    /// Like `rpc_call`, but for `channels.deleteMessages` specifically.
    ///
    /// `channels.deleteMessages` returns a channel-scoped `AffectedMessages`,
    /// but the generic auto-feed above can't tell that apart from a global
    /// one - only the call site knows `channel_id`. Use this instead of
    /// `rpc_call` for that one request so the response gets fed as
    /// `AffectedChannelMessages` correctly. Behaves exactly like `rpc_call`
    /// (same retry/FLOOD_WAIT/migrate handling) if no `MessageBox` is bound.
    fn delete_channel_messages<'py>(
        &self,
        py: Python<'py>,
        tl_bytes: Vec<u8>,
        channel_id: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        let rpc_tx = self.rpc_tx.lock().expect("rpc_tx mutex poisoned").clone();
        let threshold = self.flood_sleep_threshold;
        let mbox = self
            .message_box
            .lock()
            .expect("message_box mutex poisoned")
            .clone();
        future_into_py(py, async move {
            let policy = Arc::new(AutoSleep {
                threshold: Duration::from_secs(threshold),
                io_errors_as_flood_of: Some(Duration::from_secs(1)),
            });
            let mut retries = RetryLoop::new(policy);
            loop {
                let result = if let Some(rpc_tx) = &rpc_tx {
                    Self::enqueue_streaming(rpc_tx, tl_bytes.clone()).await
                } else {
                    let mut guard = inner.lock().await;
                    let conn = guard.as_mut().ok_or_else(|| {
                        py_err("connection was consumed by into_pipelined_sender()")
                    })?;
                    let r = conn.rpc_call(&crate::raw::RawCall(tl_bytes.clone())).await;
                    drop(guard);
                    r
                };
                match result {
                    Ok(result) => {
                        if let Some(mbox) = &mbox {
                            if let Ok(affected) =
                                ferogram_tl_types::types::messages::AffectedMessages::from_bytes_exact(
                                    &result,
                                )
                            {
                                let _ = mbox.lock().await.process_updates(
                                    ferogram_msgbox::UpdatesLike::AffectedChannelMessages {
                                        affected,
                                        channel_id,
                                    },
                                );
                            }
                        }
                        return Ok(result);
                    }
                    Err(e) => {
                        retries.advance(e).await.map_err(py_err)?;
                    }
                }
            }
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
            let p = persisted.lock().await.clone();
            tokio::task::spawn_blocking(move || session.save(&p))
                .await
                .map_err(py_err)?
                .map_err(py_err)
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
            let to_save = p.clone();
            drop(p);
            tokio::task::spawn_blocking(move || session.save(&to_save))
                .await
                .map_err(py_err)?
                .map_err(py_err)?;
            Ok(())
        })
    }

    /// Update just the address stored for `dc_id`, preserving its auth key
    /// (if any). Used to persist the address `help.getConfig` returned for
    /// the caller's `allow_ipv6` preference, without disturbing an
    /// already-established session.
    fn set_dc_addr<'py>(
        &self,
        py: Python<'py>,
        dc_id: i32,
        addr: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let persisted = Arc::clone(&self.persisted);
        let session = Arc::clone(&self.session);
        future_into_py(py, async move {
            let mut p = persisted.lock().await;
            if let Some(entry) = p.dcs.iter_mut().find(|d| d.dc_id == dc_id) {
                if entry.addr == addr {
                    return Ok(());
                }
                entry.addr = addr;
            } else {
                p.dcs.push(DcEntry {
                    dc_id,
                    addr,
                    auth_key: None,
                    first_salt: 0,
                    time_offset: 0,
                    flags: Default::default(),
                });
            }
            let to_save = p.clone();
            drop(p);
            tokio::task::spawn_blocking(move || session.save(&to_save))
                .await
                .map_err(py_err)?
                .map_err(py_err)?;
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
                let to_save = p.clone();
                drop(p);
                tokio::task::spawn_blocking(move || session.save(&to_save))
                    .await
                    .map_err(py_err)?
                    .map_err(py_err)?;
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
            let to_save = p.clone();
            drop(p);
            tokio::task::spawn_blocking(move || session.save(&to_save))
                .await
                .map_err(py_err)?
                .map_err(py_err)?;
            Ok(())
        })
    }

    /// Streaming mode only (`connect(stream_updates=True)`): await the next
    /// event from the sender task's background read loop.
    ///
    /// Returns `(kind, payload)`:
    /// - `("update", body)` - a raw pushed update frame. Feed it to
    ///   `MessageBox.process_raw(body)` the same way `apply_difference`
    ///   results are handled, then dispatch whatever comes back.
    /// - `("connected", b"")` - the sender task (re)established the
    ///   session. Call `MessageBox.mark_gap()` so a catch-up
    ///   `getDifference` runs and nothing sent while unobserved is missed.
    /// - `("error", message)` - the connection failed. This binding does
    ///   not auto-reconnect a streaming connection; the caller should stop
    ///   pumping and surface/log `message`.
    ///
    /// Returns `None` once the sender task has shut down for good (all
    /// handles dropped) - stop calling this after that.
    fn recv_frame<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let frame_rx = Arc::clone(&self.frame_rx);
        future_into_py(py, async move {
            let mut guard = frame_rx.lock().await;
            let rx = guard
                .as_mut()
                .ok_or_else(|| py_err("recv_frame() requires connect(stream_updates=True)"))?;
            match rx.recv().await {
                None => Ok(None),
                Some(FrameEvent::Update(body)) => Ok(Some(("update".to_string(), body))),
                Some(FrameEvent::Connected { .. }) => {
                    Ok(Some(("connected".to_string(), Vec::new())))
                }
                Some(FrameEvent::Error(e)) => {
                    Ok(Some(("error".to_string(), e.to_string().into_bytes())))
                }
            }
        })
    }

    /// Current auth key bytes for this connection (256 bytes).
    fn auth_key_bytes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let guard = inner.lock().await;
            let conn = guard
                .as_ref()
                .ok_or_else(|| py_err("connection was consumed by into_pipelined_sender()"))?;
            Ok(conn.auth_key_bytes().to_vec())
        })
    }

    fn __repr__(&self) -> String {
        "DcConnection(...)".into()
    }
}
