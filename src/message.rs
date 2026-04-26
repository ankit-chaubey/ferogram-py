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

// Rich message object returned from both updates and send calls.

use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use std::sync::Arc;

use crate::py_err;

#[pyclass]
#[derive(Clone)]
pub struct Message {
    #[pyo3(get)] pub id:                  i32,
    #[pyo3(get)] pub text:                Option<String>,
    #[pyo3(get)] pub date:                i32,
    #[pyo3(get)] pub chat_id:             i64,
    #[pyo3(get)] pub from_id:             Option<i64>,
    #[pyo3(get)] pub outgoing:            bool,
    #[pyo3(get)] pub mentioned:           bool,
    #[pyo3(get)] pub pinned:              bool,
    #[pyo3(get)] pub reply_to_message_id: Option<i32>,
    #[pyo3(get)] pub via_bot_id:          Option<i64>,
    #[pyo3(get)] pub grouped_id:          Option<i64>,
    #[pyo3(get)] pub has_media:           bool,
    #[pyo3(get)] pub has_photo:           bool,
    pub(crate) client: Option<Arc<ferogram::Client>>,
}

#[pymethods]
impl Message {
    fn __repr__(&self) -> String {
        format!("Message(id={}, chat_id={}, text={:?})", self.id, self.chat_id, self.text)
    }

    fn reply<'py>(&self, py: Python<'py>, text: String) -> PyResult<Bound<'py, PyAny>> {
        let client   = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let chat_id  = self.chat_id.to_string();
        let reply_id = self.id;
        future_into_py(py, async move {
            let msg = client
                .send_message_to_peer_ex(
                    chat_id.as_str(),
                    &ferogram::InputMessage::text(&text).reply_to(Some(reply_id)),
                )
                .await
                .map_err(py_err)?;
            Ok(from_incoming(msg, Some(client)))
        })
    }

    fn reply_html<'py>(&self, py: Python<'py>, html: String) -> PyResult<Bound<'py, PyAny>> {
        let client   = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let chat_id  = self.chat_id.to_string();
        let reply_id = self.id;
        future_into_py(py, async move {
            let msg = client
                .send_message_to_peer_ex(
                    chat_id.as_str(),
                    &ferogram::InputMessage::html(html).reply_to(Some(reply_id)),
                )
                .await
                .map_err(py_err)?;
            Ok(from_incoming(msg, Some(client)))
        })
    }

    fn reply_markdown<'py>(&self, py: Python<'py>, md: String) -> PyResult<Bound<'py, PyAny>> {
        let client   = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let chat_id  = self.chat_id.to_string();
        let reply_id = self.id;
        future_into_py(py, async move {
            let msg = client
                .send_message_to_peer_ex(
                    chat_id.as_str(),
                    &ferogram::InputMessage::markdown(md).reply_to(Some(reply_id)),
                )
                .await
                .map_err(py_err)?;
            Ok(from_incoming(msg, Some(client)))
        })
    }

    fn respond<'py>(&self, py: Python<'py>, text: String) -> PyResult<Bound<'py, PyAny>> {
        let client  = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let chat_id = self.chat_id.to_string();
        future_into_py(py, async move {
            let msg = client.send_message(&chat_id, &text).await.map_err(py_err)?;
            Ok(from_incoming(msg, Some(client)))
        })
    }

    fn respond_html<'py>(&self, py: Python<'py>, html: String) -> PyResult<Bound<'py, PyAny>> {
        let client  = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let chat_id = self.chat_id.to_string();
        future_into_py(py, async move {
            let msg = client.send_html(chat_id, &html).await.map_err(py_err)?;
            Ok(from_incoming(msg, Some(client)))
        })
    }

    fn respond_markdown<'py>(&self, py: Python<'py>, md: String) -> PyResult<Bound<'py, PyAny>> {
        let client  = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let chat_id = self.chat_id.to_string();
        future_into_py(py, async move {
            let msg = client.send_markdown(chat_id, &md).await.map_err(py_err)?;
            Ok(from_incoming(msg, Some(client)))
        })
    }

    fn edit<'py>(&self, py: Python<'py>, new_text: String) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer   = self.chat_id.to_string();
        let id     = self.id;
        future_into_py(py, async move {
            client.edit_message(peer, id, &new_text).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn edit_html<'py>(&self, py: Python<'py>, html: String) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer   = self.chat_id.to_string();
        let id     = self.id;
        future_into_py(py, async move {
            client.edit_message_ex(peer, id, ferogram::InputMessage::html(html)).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn edit_markdown<'py>(&self, py: Python<'py>, md: String) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer   = self.chat_id.to_string();
        let id     = self.id;
        future_into_py(py, async move {
            client.edit_message_ex(peer, id, ferogram::InputMessage::markdown(md)).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn delete<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let ids    = vec![self.id];
        future_into_py(py, async move {
            client.delete_messages(ids, true).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn forward_to<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let src    = self.chat_id.to_string();
        let ids    = vec![self.id];
        future_into_py(py, async move {
            client.forward_messages(peer, &ids, src).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn pin<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer   = self.chat_id.to_string();
        let id     = self.id;
        future_into_py(py, async move {
            client.pin_message(peer, id, false, false, false).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn react<'py>(&self, py: Python<'py>, emoji: String) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone().ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer   = self.chat_id.to_string();
        let id     = self.id;
        future_into_py(py, async move {
            client
                .send_reaction(peer, id, ferogram::reactions::InputReactions::emoticon(&emoji))
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }
}

pub fn from_incoming(m: ferogram::update::IncomingMessage, client: Option<Arc<ferogram::Client>>) -> Message {
    Message {
        id:                  m.id(),
        text:                m.text().map(str::to_owned),
        date:                m.date(),
        chat_id:             m.chat_id(),
        from_id:             m.from_id(),
        outgoing:            m.outgoing(),
        mentioned:           m.mentioned(),
        pinned:              m.pinned(),
        reply_to_message_id: m.reply_to_message_id(),
        via_bot_id:          m.via_bot_id(),
        grouped_id:          m.grouped_id(),
        has_media:           m.has_media(),
        has_photo:           m.has_photo(),
        client,
    }
}
