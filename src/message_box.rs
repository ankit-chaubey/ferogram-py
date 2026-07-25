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

// Wraps `ferogram_msgbox::MessageBoxes` - the same pts/qts/seq gap
// tracker the Rust `ferogram` client uses - as a Python-callable object.
//
// Rust-typed `Update`/`User`/`Chat` values never cross into Python: every
// method here takes and returns raw TL bytes, which the Python side already
// knows how to build/parse with its own codegen'd `ferogram/raw` module. This
// class only makes the *decisions* (is there a gap, is a diff due, what pts
// to advance to) - `client.py` still drives the actual RPCs.

use std::sync::Arc;
use std::time::Instant;

use ferogram_msgbox::{self as mb, MessageBoxes};
use ferogram_tl_types::{self as tl, Cursor, Deserializable, Serializable};
use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use tokio::sync::Mutex;

use crate::py_err;

/// Serialize a batch of TL values to raw bytes, one entry per item, for the
/// Python side to deserialize with its own `_tl` module.
fn to_bytes_vec<T: Serializable>(items: &[T]) -> Vec<Vec<u8>> {
    items.iter().map(|item| item.to_bytes()).collect()
}

/// Update-gap tracking state machine (pts/qts/seq), Python-facing wrapper.
///
/// Usage::
///
///     mbox = MessageBox()
///     conn.bind_message_box(mbox)   # DcConnection auto-feeds RPC responses into it
///     ...
///     delay = await mbox.check_deadline_secs()
///     # sleep `delay`, then:
///     req = await mbox.get_difference_bytes()
///     if req is not None:
///         body = await conn.rpc_call(req)
///         updates, users, chats = await mbox.apply_difference(body)
#[pyclass(name = "MessageBox")]
pub struct PyMessageBox {
    inner: Arc<Mutex<MessageBoxes>>,
}

impl PyMessageBox {
    /// Internal-only: hand the same shared state to a `DcConnection` so its
    /// `rpc_call` can auto-feed into this box. Not exposed to Python -
    /// Python only ever sees `MessageBox` as an opaque handle.
    pub(crate) fn shared(&self) -> Arc<Mutex<MessageBoxes>> {
        Arc::clone(&self.inner)
    }
}

#[pymethods]
impl PyMessageBox {
    /// Create a new, empty box (no prior state).
    #[new]
    fn new() -> Self {
        Self {
            inner: Arc::new(Mutex::new(MessageBoxes::new())),
        }
    }

    /// Restore from a previously-persisted `session_state()` tuple.
    #[staticmethod]
    fn load(pts: i32, qts: i32, date: i32, seq: i32, channels: Vec<(i64, i32)>) -> Self {
        let snap = mb::UpdatesStateSnap {
            pts,
            qts,
            date,
            seq,
            channels: channels
                .into_iter()
                .map(|(id, pts)| mb::ChannelState { id, pts })
                .collect(),
        };
        Self {
            inner: Arc::new(Mutex::new(MessageBoxes::load(snap))),
        }
    }

    fn is_empty<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move { Ok(inner.lock().await.is_empty()) })
    }

    /// Set state right after login. Only valid while `is_empty()` is true.
    fn set_state<'py>(
        &self,
        py: Python<'py>,
        pts: i32,
        qts: i32,
        date: i32,
        seq: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            inner.lock().await.set_state(tl::types::updates::State {
                pts,
                qts,
                date,
                seq,
                unread_count: 0,
            });
            Ok(())
        })
    }

    /// Record a channel's pts from `GetDialogs` - a no-op if already tracked.
    fn try_set_channel_state<'py>(
        &self,
        py: Python<'py>,
        channel_id: i64,
        pts: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            inner.lock().await.try_set_channel_state(channel_id, pts);
            Ok(())
        })
    }

    /// Snapshot for session persistence: `(pts, qts, date, seq, [(channel_id, pts), ...])`.
    fn session_state<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let s = inner.lock().await.session_state();
            let channels: Vec<(i64, i32)> = s.channels.iter().map(|c| (c.id, c.pts)).collect();
            Ok((s.pts, s.qts, s.date, s.seq, channels))
        })
    }

    /// Seconds to wait before calling back in. `0.0` means a diff is already
    /// due - call `get_difference_bytes()` / `next_channel_diff()` right away
    /// instead of sleeping. Replaces the old fixed `asyncio.sleep(0.3)` poll.
    fn check_deadline_secs<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let deadline = inner.lock().await.check_deadlines();
            Ok(deadline
                .saturating_duration_since(Instant::now())
                .as_secs_f64())
        })
    }

    /// Feed a raw pushed-update frame (or an own-RPC response body not
    /// already routed through `DcConnection.rpc_call`'s auto-feed).
    ///
    /// Returns `None` when there's nothing to dispatch (no updates, or a gap
    /// was detected - `check_deadline_secs()` will report `0.0` next time a
    /// diff is due). On success returns serialized `(updates, users, chats)`.
    fn process_raw<'py>(&self, py: Python<'py>, body: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let Some(parsed) = mb::classify_own_response(&body) else {
                return Ok(None::<(Vec<Vec<u8>>, Vec<Vec<u8>>, Vec<Vec<u8>>)>);
            };
            match inner.lock().await.process_updates(parsed) {
                Ok((updates, users, chats)) => Ok(Some((
                    to_bytes_vec(&updates),
                    to_bytes_vec(&users),
                    to_bytes_vec(&chats),
                ))),
                Err(mb::Gap) => Ok(None),
            }
        })
    }

    /// Serialized `updates.getDifference` request, or `None` if the global
    /// (pts/qts) box doesn't need one right now.
    fn get_difference_bytes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            Ok(inner
                .lock()
                .await
                .get_difference()
                .map(|req| req.to_bytes()))
        })
    }

    /// Apply a raw `updates.Difference` RPC response. Returns serialized
    /// `(updates, users, chats)`.
    fn apply_difference<'py>(&self, py: Python<'py>, body: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut cur = Cursor::from_slice(&body);
            let diff = tl::enums::updates::Difference::deserialize(&mut cur).map_err(py_err)?;
            let (updates, users, chats) = inner.lock().await.apply_difference(diff);
            Ok((
                to_bytes_vec(&updates),
                to_bytes_vec(&users),
                to_bytes_vec(&chats),
            ))
        })
    }

    /// Clear pending state on the global box after a diff attempt fails
    /// (parse error / RPC error) - stops it re-firing every tick.
    fn abort_difference<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            inner.lock().await.abort_difference();
            Ok(())
        })
    }

    /// Forcibly advance pts/qts/date/seq to server-reported values, e.g.
    /// after a `getDifference` parse failure (unknown constructor from a
    /// newer layer) so the stale gap doesn't loop forever.
    fn force_reset_common_pts<'py>(
        &self,
        py: Python<'py>,
        pts: i32,
        qts: i32,
        date: i32,
        seq: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            inner
                .lock()
                .await
                .force_reset_common_pts(pts, qts, date, seq);
            Ok(())
        })
    }

    /// `(channel_id, pts)` for a channel that needs `getChannelDifference`,
    /// or `None`. The caller fills in `access_hash`/`limit` itself (this
    /// box has no peer cache) and calls `apply_channel_difference` with the
    /// raw response.
    fn next_channel_diff<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut guard = inner.lock().await;
            Ok(guard
                .get_channel_difference()
                .map(|(id, req)| (id, req.pts)))
        })
    }

    /// Apply a raw `updates.ChannelDifference` RPC response for `channel_id`.
    /// Returns serialized `(updates, users, chats)`.
    fn apply_channel_difference<'py>(
        &self,
        py: Python<'py>,
        body: Vec<u8>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let mut cur = Cursor::from_slice(&body);
            let diff =
                tl::enums::updates::ChannelDifference::deserialize(&mut cur).map_err(py_err)?;
            let (updates, users, chats) = inner.lock().await.apply_channel_difference(diff);
            Ok((
                to_bytes_vec(&updates),
                to_bytes_vec(&users),
                to_bytes_vec(&chats),
            ))
        })
    }

    /// Signal that the connection was (re)established - forces a catch-up
    /// `getDifference` on the next `check_deadline_secs()` tick, same as the
    /// Rust core's `UpdatesLike::ConnectionClosed` on reconnect/first
    /// connect. Call this whenever `DcConnection.recv_frame()` reports a
    /// `"connected"` event, so nothing sent while the socket was down (or
    /// before the pushed-update pump was listening) gets lost.
    fn mark_gap<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let _ = inner
                .lock()
                .await
                .process_updates(mb::UpdatesLike::ConnectionClosed);
            Ok(())
        })
    }

    /// End a channel diff prematurely. `banned=True` drops the channel from
    /// tracking permanently; otherwise it's retried later.
    fn end_channel_difference<'py>(
        &self,
        py: Python<'py>,
        banned: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let reason = if banned {
                mb::PrematureEndReason::Banned
            } else {
                mb::PrematureEndReason::TemporaryServerIssues
            };
            inner.lock().await.end_channel_difference(reason);
            Ok(())
        })
    }
}
