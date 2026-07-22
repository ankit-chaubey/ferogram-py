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

//! Python binding for `ferogram_mtsender::PipelinedSender`  - the "X > 1"
//! half of Telegram's upload/download performance recommendation: multiple
//! chunk requests in flight on one socket, instead of one-at-a-time
//! `DcConnection::rpc_call`.
//!
//! Get one via `DcConnection.into_pipelined_sender()`. The two-call split
//! (`enqueue` then `request.wait()`) is what actually gives you X > 1 on
//! the Python side: call `enqueue` several times before `wait`-ing on any
//! of them, same as the Rust core's `media.rs` window loop does.

use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;

use ferogram_mtsender::{InvocationError, PipelinedSender};
use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use tokio::sync::Mutex;

use crate::py_err;

type PendingRpc = Pin<Box<dyn Future<Output = Result<Vec<u8>, InvocationError>> + Send>>;

/// A single enqueued-but-not-yet-awaited RPC. Returned by
/// `PipelinedSender.enqueue()`; call `.wait()` whenever you actually need
/// the result. Holding several of these before calling `.wait()` on any of
/// them is what puts more than one request in flight at once.
#[pyclass]
pub struct PyPipelinedRequest {
    fut: Arc<Mutex<Option<PendingRpc>>>,
}

#[pymethods]
impl PyPipelinedRequest {
    /// Await the eventual RPC response body. Can only be called once  -
    /// calling it twice on the same request raises.
    fn wait<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let fut = Arc::clone(&self.fut);
        future_into_py(py, async move {
            let f = {
                let mut guard = fut.lock().await;
                guard
                    .take()
                    .ok_or_else(|| py_err("request already awaited"))?
            };
            f.await.map_err(py_err)
        })
    }

    fn __repr__(&self) -> String {
        "PipelinedRequest(...)".into()
    }
}

/// A pipelined transfer connection: multiple chunk requests can be
/// enqueued and in flight simultaneously on one socket. Cheap to clone
/// (shares the underlying channel/liveness flag with the Rust
/// `PipelinedSender`), so it's fine to hand the same instance to several
/// concurrent coroutines if needed, though the usual pattern is one per
/// transfer worker.
#[pyclass]
pub struct PyPipelinedSender {
    inner: PipelinedSender,
}

impl PyPipelinedSender {
    pub fn new(inner: PipelinedSender) -> Self {
        Self { inner }
    }
}

#[pymethods]
impl PyPipelinedSender {
    /// `True` if the underlying sender task is still running. Does not
    /// guarantee the *next* request will succeed (the connection could die
    /// between this check and the next `enqueue`), but is enough to decide
    /// whether to keep using this sender or open a fresh one.
    fn is_alive(&self) -> bool {
        self.inner.is_alive()
    }

    /// Enqueue a pre-serialised TL request body and return immediately
    /// with a `PipelinedRequest`  - does **not** wait for the server's
    /// response. Call `enqueue` several times before `.wait()`-ing on any
    /// of the results to actually get X > 1 requests in flight; awaiting
    /// each one right away defeats the purpose and degrades to one request
    /// at a time.
    ///
    /// Raises immediately if the sender task has already shut down (e.g.
    /// the connection died); check `is_alive()` after a failure to decide
    /// whether to open a fresh `PipelinedSender` instead of retrying on a
    /// dead connection.
    fn enqueue<'py>(&self, py: Python<'py>, tl_bytes: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        future_into_py(py, async move {
            let fut = inner.enqueue(tl_bytes).await.map_err(py_err)?;
            let boxed: PendingRpc = Box::pin(fut);
            Ok(PyPipelinedRequest {
                fut: Arc::new(Mutex::new(Some(boxed))),
            })
        })
    }

    /// Enqueue and immediately await a single request  - convenience for
    /// call sites that don't need explicit pipelining (e.g. the final part
    /// of a transfer, or error-recovery paths). Equivalent to
    /// `sender.enqueue(body).wait()` but without a round-trip through a
    /// separate `PipelinedRequest` object.
    fn call<'py>(&self, py: Python<'py>, tl_bytes: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        future_into_py(
            py,
            async move { inner.call(tl_bytes).await.map_err(py_err) },
        )
    }

    fn __repr__(&self) -> String {
        format!("PipelinedSender(alive={})", self.inner.is_alive())
    }
}
