// Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
// SPDX-License-Identifier: MIT OR Apache-2.0

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::io;
use std::sync::Arc;

use ferogram_session::{
    BinaryFileBackend, InMemoryBackend, PersistedSession, SessionBackend, StringSessionBackend,
};

use crate::py_err;

/// Stores the session in a compact binary file on disk (default).
///
/// Usage::
///
///     client = Client(session=FileSession("my_account"), ...)
///
/// Appends ``.session`` automatically when no extension is given.
#[pyclass(frozen)]
pub struct FileSession {
    pub path: String,
}

#[pymethods]
impl FileSession {
    #[new]
    fn new(path: String) -> Self {
        let path = if std::path::Path::new(&path).extension().is_none() {
            format!("{path}.session")
        } else {
            path
        };
        Self { path }
    }

    fn __repr__(&self) -> String {
        format!("FileSession({:?})", self.path)
    }
}

/// Keeps the session in memory only. Nothing survives process exit.
///
/// Useful for ephemeral scripts, tests, or one-shot tasks.
///
/// Usage::
///
///     client = Client(session=MemorySession(), ...)
#[pyclass(frozen)]
pub struct MemorySession {}

#[pymethods]
impl MemorySession {
    #[new]
    fn new() -> Self {
        Self {}
    }

    fn __repr__(&self) -> String {
        "MemorySession()".into()
    }
}

/// Portable base64 string session.
///
/// Useful for serverless environments where you store state in an env var or
/// a database column. Starts empty; call ``client.export_session_string()``
/// to retrieve the string after connecting.
///
/// Usage::
///
///     client = Client(session=StringSession(), ...)
///     # or resume from an existing string:
///     client = Client(session=StringSession("AQA..."), ...)
#[pyclass(frozen)]
pub struct StringSession {
    pub data: String,
}

#[pymethods]
impl StringSession {
    #[new]
    #[pyo3(signature = (data = String::new()))]
    fn new(data: String) -> Self {
        Self { data }
    }

    fn __repr__(&self) -> String {
        if self.data.is_empty() {
            "StringSession()".into()
        } else {
            format!("StringSession({:?})", &self.data[..self.data.len().min(16)])
        }
    }
}

/// Stores the session in a local SQLite database.
///
/// Each table row is updated individually on every change - safe for
/// multi-process tooling and gives you an inspectable session file.
///
/// Usage::
///
///     client = Client(session=SqliteSession("my_account"), ...)
///
/// Appends ``.db`` automatically when no extension is given.
#[pyclass(frozen)]
pub struct SqliteSession {
    pub path: String,
}

#[pymethods]
impl SqliteSession {
    #[new]
    fn new(path: String) -> Self {
        let path = if std::path::Path::new(&path).extension().is_none() {
            format!("{path}.db")
        } else {
            path
        };
        Self { path }
    }

    fn __repr__(&self) -> String {
        format!("SqliteSession({:?})", self.path)
    }
}

/// Wrap any Python object as a session backend.
///
/// The Python object must implement:
///
/// .. code-block:: python
///
///     def save(self, data: bytes) -> None: ...
///     def load(self) -> bytes | None: ...
///     def delete(self) -> None: ...
///     def name(self) -> str: ...  # optional, defaults to class name
///
/// ``save`` / ``load`` / ``delete`` receive / return the raw binary session
/// blob (same format as ``FileSession``). Serialize/deserialize however you
/// like (database column, Redis key, S3 object, ...).
///
/// Usage::
///
///     class RedisSession:
///         def __init__(self, key):
///             self.key = key
///         def save(self, data):
///             redis.set(self.key, data)
///         def load(self):
///             return redis.get(self.key)
///         def delete(self):
///             redis.delete(self.key)
///
///     client = Client(session=CustomSession(RedisSession("my_key")), ...)
#[pyclass(frozen)]
pub struct CustomSession {
    pub obj: Py<PyAny>,
}

#[pymethods]
impl CustomSession {
    #[new]
    fn new(obj: Py<PyAny>) -> Self {
        Self { obj }
    }

    fn __repr__(&self, py: Python<'_>) -> String {
        let name = self
            .obj
            .bind(py)
            .get_type()
            .name()
            .map(|n| n.to_string())
            .unwrap_or_else(|_| "?".to_string());
        format!("CustomSession({name})")
    }
}

/// `SessionBackend` adapter that calls back into the Python object.
struct PythonBackend {
    obj: Py<PyAny>,
    label: String,
}

impl SessionBackend for PythonBackend {
    fn save(&self, session: &PersistedSession) -> io::Result<()> {
        let bytes = session.to_bytes();
        Python::attach(|py| {
            let b = PyBytes::new(py, &bytes);
            self.obj
                .call_method1(py, "save", (b,))
                .map_err(|e| io::Error::other(e.to_string()))?;
            Ok(())
        })
    }

    fn load(&self) -> io::Result<Option<PersistedSession>> {
        Python::attach(|py| {
            let result = self
                .obj
                .call_method0(py, "load")
                .map_err(|e| io::Error::other(e.to_string()))?;
            if result.is_none(py) {
                return Ok(None);
            }
            let bytes = result
                .extract::<Vec<u8>>(py)
                .map_err(|e| io::Error::other(e.to_string()))?;
            PersistedSession::from_bytes(&bytes).map(Some)
        })
    }

    fn delete(&self) -> io::Result<()> {
        Python::attach(|py| {
            self.obj
                .call_method0(py, "delete")
                .map_err(|e| io::Error::other(e.to_string()))?;
            Ok(())
        })
    }

    fn name(&self) -> &str {
        &self.label
    }
}

/// Resolve a Python session object to an `Arc<dyn SessionBackend>`.
///
/// Accepts any of the session classes above, or a plain `str` path
/// (treated as `FileSession` for backward compat).
pub fn resolve_session(py: Python<'_>, obj: &Py<PyAny>) -> PyResult<Arc<dyn SessionBackend>> {
    // FileSession
    if let Ok(s) = obj.cast_bound::<FileSession>(py) {
        return Ok(Arc::new(BinaryFileBackend::new(s.get().path.clone())));
    }

    // MemorySession
    if obj.cast_bound::<MemorySession>(py).is_ok() {
        return Ok(Arc::new(InMemoryBackend::new()));
    }

    // StringSession
    if let Ok(s) = obj.cast_bound::<StringSession>(py) {
        return Ok(Arc::new(StringSessionBackend::new(s.get().data.clone())));
    }

    // SqliteSession
    if let Ok(s) = obj.cast_bound::<SqliteSession>(py) {
        let backend = ferogram_session::SqliteBackend::open(&s.get().path).map_err(py_err)?;
        return Ok(Arc::new(backend));
    }

    // CustomSession - wrap Python object in PythonBackend
    if let Ok(s) = obj.cast_bound::<CustomSession>(py) {
        let inner = s.get().obj.clone_ref(py);
        let label = inner
            .bind(py)
            .get_type()
            .name()
            .map(|n| n.to_string())
            .unwrap_or_else(|_| "custom".into());
        // Check the required methods exist
        for method in ["save", "load", "delete"] {
            if !inner.bind(py).hasattr(method).unwrap_or(false) {
                return Err(py_err(format!(
                    "CustomSession object must implement {method}()"
                )));
            }
        }
        return Ok(Arc::new(PythonBackend { obj: inner, label }));
    }

    // Fallback: plain str path -> FileSession behaviour
    if let Ok(path) = obj.extract::<String>(py) {
        let path = if std::path::Path::new(&path).extension().is_none() {
            format!("{path}.session")
        } else {
            path
        };
        return Ok(Arc::new(BinaryFileBackend::new(path)));
    }

    Err(py_err(
        "session must be FileSession, MemorySession, StringSession, \
         SqliteSession, CustomSession, or a str path",
    ))
}
