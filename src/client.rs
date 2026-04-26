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

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use std::sync::Arc;
use tokio::sync::Mutex;

use crate::{auth::*, message::from_incoming, py_err, types::*};

#[pyclass]
pub struct Client {
    pub inner: Arc<ferogram::Client>,
    pub _shutdown: ferogram::ShutdownToken,
    stream: Arc<Mutex<ferogram::UpdateStream>>,
}

#[pymethods]
impl Client {
    #[staticmethod]
    fn builder(api_id: i32, api_hash: String, session: String) -> ClientBuilder {
        ClientBuilder { api_id, api_hash, session }
    }

    fn is_authorized<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.is_authorized().await.map_err(py_err) })
    }

    fn request_login_code<'py>(&self, py: Python<'py>, phone: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let tok = c.request_login_code(&phone).await.map_err(py_err)?;
            Ok(LoginToken(Arc::new(std::sync::Mutex::new(Some(tok)))))
        })
    }

    fn sign_in<'py>(&self, py: Python<'py>, token: &LoginToken, code: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        let owned = {
            let mut g = token.0.lock().map_err(py_err)?;
            g.take().ok_or_else(|| PyRuntimeError::new_err("LoginToken already consumed"))?
        };
        future_into_py(py, async move {
            match c.sign_in(&owned, &code).await {
                Ok(_) => Ok(None::<PasswordToken>),
                Err(ferogram::SignInError::PasswordRequired(box_tok)) => {
                    let hint = box_tok.hint().map(str::to_owned);
                    Ok(Some(PasswordToken { inner: Arc::new(std::sync::Mutex::new(Some(*box_tok))), hint }))
                }
                Err(e) => Err(py_err(e)),
            }
        })
    }

    fn check_password<'py>(&self, py: Python<'py>, token: &PasswordToken, password: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        let owned = {
            let mut g = token.inner.lock().map_err(py_err)?;
            g.take().ok_or_else(|| PyRuntimeError::new_err("PasswordToken already consumed"))?
        };
        future_into_py(py, async move {
            c.check_password(owned, password.as_bytes()).await.map_err(py_err)
        })
    }

    fn bot_sign_in<'py>(&self, py: Python<'py>, token: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.bot_sign_in(&token).await.map_err(py_err) })
    }

    fn save_session<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.save_session().await.map_err(py_err)?; Ok(()) })
    }

    fn sign_out<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.sign_out().await.map_err(py_err) })
    }

    fn export_session_string<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.export_session_string().await.map_err(py_err) })
    }

    fn next_update<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        let stream = Arc::clone(&self.stream);
        future_into_py(py, async move {
            let upd = stream.lock().await.next().await;
            match upd {
                None => Ok(None::<(String, PyObject)>),
                Some(u) => {
                    Python::with_gil(|py| {
                        Ok(crate::updates::update_to_py(py, u, c)
                            .map(|(k, v)| (k.to_owned(), v)))
                    })
                }
            }
        })
    }

    fn send_message<'py>(&self, py: Python<'py>, peer: String, text: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let m = c.send_message(&peer, &text).await.map_err(py_err)?;
            Ok(from_incoming(m, Some(c)))
        })
    }

    fn send_html<'py>(&self, py: Python<'py>, peer: String, html: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            Ok(from_incoming(c.send_html(peer, &html).await.map_err(py_err)?, Some(c)))
        })
    }

    fn send_markdown<'py>(&self, py: Python<'py>, peer: String, md: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            Ok(from_incoming(c.send_markdown(peer, &md).await.map_err(py_err)?, Some(c)))
        })
    }

    fn send_to_self<'py>(&self, py: Python<'py>, text: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.send_to_self(&text).await.map_err(py_err)?; Ok(()) })
    }

    fn edit_message<'py>(&self, py: Python<'py>, peer: String, message_id: i32, new_text: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.edit_message(peer, message_id, &new_text).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn delete_messages<'py>(&self, py: Python<'py>, message_ids: Vec<i32>, revoke: bool) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_messages(message_ids, revoke).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn forward_messages<'py>(&self, py: Python<'py>, destination: String, source: String, message_ids: Vec<i32>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.forward_messages(destination, &message_ids, source).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn pin_message<'py>(&self, py: Python<'py>, peer: String, message_id: i32) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.pin_message(peer, message_id, false, false, false).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn unpin_message<'py>(&self, py: Python<'py>, peer: String, message_id: i32) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.unpin_message(peer, message_id).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn mark_as_read<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.mark_as_read(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    #[pyo3(signature = (peer, path, caption = String::new()))]
    fn send_photo<'py>(&self, py: Python<'py>, peer: String, path: String, caption: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let data = tokio::fs::read(&path).await.map_err(py_err)?;
            let name = std::path::Path::new(&path).file_name()
                .and_then(|n| n.to_str()).unwrap_or("photo.jpg").to_owned();
            let uploaded = c.upload_file(&data, &name, "image/jpeg").await.map_err(py_err)?;
            let msg = c.send_file(peer, uploaded.as_photo_media(), &ferogram::InputMessage::text(caption)).await.map_err(py_err)?;
            Ok(from_incoming(msg, Some(c)))
        })
    }

    #[pyo3(signature = (peer, path, caption = String::new(), mime_type = None))]
    fn send_document<'py>(&self, py: Python<'py>, peer: String, path: String, caption: String, mime_type: Option<String>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let data = tokio::fs::read(&path).await.map_err(py_err)?;
            let name = std::path::Path::new(&path).file_name()
                .and_then(|n| n.to_str()).unwrap_or("file").to_owned();
            let mime = mime_type.as_deref().unwrap_or("application/octet-stream");
            let uploaded = c.upload_file(&data, &name, mime).await.map_err(py_err)?;
            let msg = c.send_file(peer, uploaded.as_document_media(), &ferogram::InputMessage::text(caption)).await.map_err(py_err)?;
            Ok(from_incoming(msg, Some(c)))
        })
    }

    #[pyo3(signature = (peer, path, caption = String::new(), mime_type = None))]
    fn send_file<'py>(&self, py: Python<'py>, peer: String, path: String, caption: String, mime_type: Option<String>) -> PyResult<Bound<'py, PyAny>> {
        self.send_document(py, peer, path, caption, mime_type)
    }

    fn get_me<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let u = c.get_me().await.map_err(py_err)?;
            Ok(User {
                id: u.id,
                first_name: u.first_name.clone().unwrap_or_default(),
                last_name: u.last_name.clone(),
                username: u.username.clone(),
                phone: u.phone.clone(),
                bot: u.bot,
            })
        })
    }

    #[pyo3(signature = (limit = 100))]
    fn get_dialogs<'py>(&self, py: Python<'py>, limit: i32) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let dialogs = c.get_dialogs(limit).await.map_err(py_err)?;
            Ok(dialogs.into_iter().map(|d| Dialog {
                title: d.title(), unread_count: d.unread_count(), top_message: d.top_message(),
            }).collect::<Vec<_>>())
        })
    }

    fn send_reaction<'py>(&self, py: Python<'py>, peer: String, message_id: i32, emoji: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.send_reaction(peer, message_id, ferogram::reactions::InputReactions::emoticon(&emoji))
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn invoke_raw<'py>(&self, py: Python<'py>, tl_bytes: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            crate::raw::invoke_raw_inner(&c, tl_bytes).await
        })
    }
}

pub fn make_client(inner: ferogram::Client, shutdown: ferogram::ShutdownToken) -> Client {
    let stream = inner.stream_updates();
    Client {
        inner: Arc::new(inner),
        _shutdown: shutdown,
        stream: Arc::new(Mutex::new(stream)),
    }
}
