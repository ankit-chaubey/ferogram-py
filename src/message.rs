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
use std::sync::Arc;

use crate::py_err;

#[pyclass]
#[derive(Clone)]
pub struct Message {
    #[pyo3(get)]
    pub id: i32,
    #[pyo3(get)]
    pub text: Option<String>,
    #[pyo3(get)]
    pub date: i32,
    #[pyo3(get)]
    pub edit_date: Option<i32>,
    #[pyo3(get)]
    pub chat_id: i64,
    #[pyo3(get)]
    pub from_id: Option<i64>,
    #[pyo3(get)]
    pub outgoing: bool,
    #[pyo3(get)]
    pub mentioned: bool,
    #[pyo3(get)]
    pub pinned: bool,
    #[pyo3(get)]
    pub reply_to_message_id: Option<i32>,
    #[pyo3(get)]
    pub via_bot_id: Option<i64>,
    #[pyo3(get)]
    pub grouped_id: Option<i64>,
    #[pyo3(get)]
    pub has_media: bool,
    #[pyo3(get)]
    pub has_photo: bool,
    #[pyo3(get)]
    pub has_document: bool,
    #[pyo3(get)]
    pub is_forwarded: bool,
    #[pyo3(get)]
    pub post_author: Option<String>,
    #[pyo3(get)]
    pub view_count: Option<i32>,
    #[pyo3(get)]
    pub reply_count: Option<i32>,
    pub(crate) client: Option<Arc<ferogram::Client>>,
    pub(crate) _inner_markup: Option<ferogram::tl::enums::ReplyMarkup>,
    /// Eagerly resolved channel kind (populated at construction when available).
    pub(crate) channel_kind_cached: Option<ferogram::types::ChannelKind>,
}

// Internal helper: build an InputMessage from text + optional parse_mode

fn make_input(text: String, parse_mode: Option<&str>) -> ferogram::InputMessage {
    match parse_mode {
        Some("html") => ferogram::InputMessage::html(text),
        Some("markdown") | Some("md") => ferogram::InputMessage::markdown(text),
        _ => ferogram::InputMessage::text(&text),
    }
}

#[pymethods]
impl Message {
    fn __repr__(&self) -> String {
        format!(
            "Message(id={}, chat_id={}, text={:?})",
            self.id, self.chat_id, self.text
        )
    }

    #[getter]
    fn is_private(&self) -> bool {
        self.chat_id > 0
    }

    #[getter]
    fn is_group(&self) -> bool {
        self.chat_id < 0
    }

    #[getter]
    fn is_reply(&self) -> bool {
        self.reply_to_message_id.is_some()
    }

    // reply - send to the same chat, quoting this message
    //
    // parse_mode: None (plain) | "html" | "markdown" / "md"

    #[pyo3(signature = (text, parse_mode = None))]
    fn reply<'py>(
        &self,
        py: Python<'py>,
        text: String,
        parse_mode: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let chat_id = self.chat_id.to_string();
        let reply_id = self.id;
        future_into_py(py, async move {
            let input = make_input(text, parse_mode.as_deref()).reply_to(Some(reply_id));
            let msg = client
                .send_message(chat_id.as_str(), input)
                .await
                .map_err(py_err)?;
            Ok(from_incoming(msg, Some(client)))
        })
    }

    // respond - send to the same chat without quoting
    //
    // parse_mode: None (plain) | "html" | "markdown" / "md"

    #[pyo3(signature = (text, parse_mode = None))]
    fn respond<'py>(
        &self,
        py: Python<'py>,
        text: String,
        parse_mode: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let chat_id = self.chat_id.to_string();
        future_into_py(py, async move {
            let input = make_input(text, parse_mode.as_deref());
            let msg = client.send_message(chat_id, input).await.map_err(py_err)?;
            Ok(from_incoming(msg, Some(client)))
        })
    }

    // edit - replace this message's text in-place
    //
    // parse_mode: None (plain) | "html" | "markdown" / "md"

    #[pyo3(signature = (new_text, parse_mode = None))]
    fn edit<'py>(
        &self,
        py: Python<'py>,
        new_text: String,
        parse_mode: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer = self.chat_id.to_string();
        let id = self.id;
        future_into_py(py, async move {
            match parse_mode.as_deref() {
                Some("html") | Some("markdown") | Some("md") => {
                    let input = make_input(new_text, parse_mode.as_deref());
                    client.edit_message(peer, id, input).await.map_err(py_err)?;
                }
                _ => {
                    client
                        .edit_message(peer, id, new_text.as_str())
                        .await
                        .map_err(py_err)?;
                }
            }
            Ok(())
        })
    }

    // Other message actions

    fn delete<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let ids = vec![self.id];
        future_into_py(py, async move {
            client.delete_messages(&ids, true).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn forward_to<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let src = self.chat_id.to_string();
        let ids = vec![self.id];
        future_into_py(py, async move {
            client
                .forward_messages(peer, &ids, src, ferogram::ForwardOptions::default())
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn pin<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer = self.chat_id.to_string();
        let id = self.id;
        future_into_py(py, async move {
            client.pin_message(peer, id, false).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn react<'py>(&self, py: Python<'py>, emoji: String) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer = self.chat_id.to_string();
        let id = self.id;
        future_into_py(py, async move {
            client
                .send_reaction(
                    peer,
                    id,
                    ferogram::reactions::InputReactions::emoticon(&emoji),
                )
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn mark_read<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer = self.chat_id.to_string();
        future_into_py(py, async move {
            client.mark_read(peer).await.map_err(py_err)?;
            Ok(())
        })
    }
    /// Reload this message from the server and return the updated copy.
    /// Usage: msg = await msg.refetch()
    fn refetch<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer = self.chat_id.to_string();
        let id = self.id;
        future_into_py(py, async move {
            let msgs = client.get_messages(peer, &[id]).await.map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .next()
                .map(|m| from_incoming(m, Some(client))))
        })
    }

    /// Return the channel kind: "megagroup", "broadcast", "gigagroup", or None.
    fn channel_kind<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone();
        let chat_id = self.chat_id;
        future_into_py(py, async move {
            let client = match client {
                Some(c) => c,
                None => return Ok(None::<String>),
            };
            if chat_id >= 0 {
                return Ok(None);
            }
            let channel_id = if chat_id < -1_000_000_000_000 {
                ((-chat_id) - 1_000_000_000_000) as i64
            } else {
                (-chat_id) as i64
            };
            let s = match client.channel_kind_of(channel_id).await {
                Some(ferogram::types::ChannelKind::Megagroup) => "megagroup",
                Some(ferogram::types::ChannelKind::Gigagroup) => "gigagroup",
                Some(ferogram::types::ChannelKind::Broadcast) => "broadcast",
                None => return Ok(None),
            };
            Ok(Some(s.to_string()))
        })
    }

    fn is_megagroup<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone();
        let chat_id = self.chat_id;
        future_into_py(py, async move {
            let client = match client {
                Some(c) => c,
                None => return Ok(false),
            };
            if chat_id >= 0 {
                return Ok(false);
            }
            let channel_id = if chat_id < -1_000_000_000_000 {
                ((-chat_id) - 1_000_000_000_000) as i64
            } else {
                (-chat_id) as i64
            };
            Ok(matches!(
                client.channel_kind_of(channel_id).await,
                Some(ferogram::types::ChannelKind::Megagroup)
            ))
        })
    }

    fn is_broadcast<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let client = self.client.clone();
        let chat_id = self.chat_id;
        future_into_py(py, async move {
            let client = match client {
                Some(c) => c,
                None => return Ok(false),
            };
            if chat_id >= 0 {
                return Ok(false);
            }
            let channel_id = if chat_id < -1_000_000_000_000 {
                ((-chat_id) - 1_000_000_000_000) as i64
            } else {
                (-chat_id) as i64
            };
            Ok(matches!(
                client.channel_kind_of(channel_id).await,
                Some(ferogram::types::ChannelKind::Broadcast)
            ))
        })
    }
}

#[allow(dead_code)]
impl Message {
    // internal helpers for click_button / find_button (not exposed to Python)
    fn _callback_data_at(&self, row: usize, col: usize) -> Option<Vec<u8>> {
        let rows = self._keyboard_rows()?;
        let btn_row = match rows.get(row)? {
            ferogram::tl::enums::KeyboardButtonRow::KeyboardButtonRow(r) => &r.buttons,
        };
        if let Some(ferogram::tl::enums::KeyboardButton::Callback(b)) = btn_row.get(col) {
            Some(b.data.clone())
        } else {
            None
        }
    }
    fn _callback_data_by_text(&self, text: &str) -> Option<Vec<u8>> {
        for row in self._keyboard_rows()? {
            let buttons = match row {
                ferogram::tl::enums::KeyboardButtonRow::KeyboardButtonRow(r) => &r.buttons,
            };
            for btn in buttons {
                if let ferogram::tl::enums::KeyboardButton::Callback(b) = btn {
                    if b.text == text {
                        return Some(b.data.clone());
                    }
                }
            }
        }
        None
    }
    fn _keyboard_rows(&self) -> Option<&Vec<ferogram::tl::enums::KeyboardButtonRow>> {
        match self._inner_markup.as_ref()? {
            ferogram::tl::enums::ReplyMarkup::ReplyInlineMarkup(k) => Some(&k.rows),
            _ => None,
        }
    }

    /// Find a button by type and value, returns (row, col) or None.
    /// filter_type: "pos" | "text" | "data"
    /// For "pos": filter_value is "row,col" e.g. "0,1"
    /// For "text": filter_value is the button label
    /// For "data": filter_value is the callback data as a hex string
    fn find_button(&self, filter_type: &str, filter_value: &str) -> Option<(usize, usize)> {
        let markup = match &self._inner_markup {
            Some(m) => m,
            None => return None,
        };
        let rows = match markup {
            ferogram::tl::enums::ReplyMarkup::ReplyInlineMarkup(k) => &k.rows,
            _ => return None,
        };
        match filter_type {
            "pos" => {
                let parts: Vec<usize> = filter_value
                    .split(',')
                    .filter_map(|s| s.trim().parse().ok())
                    .collect();
                if parts.len() == 2 {
                    Some((parts[0], parts[1]))
                } else {
                    None
                }
            }
            "text" => {
                for (ri, row) in rows.iter().enumerate() {
                    let buttons = match row {
                        ferogram::tl::enums::KeyboardButtonRow::KeyboardButtonRow(r) => &r.buttons,
                    };
                    for (ci, btn) in buttons.iter().enumerate() {
                        let lbl = match btn {
                            ferogram::tl::enums::KeyboardButton::Callback(b) => b.text.as_str(),
                            ferogram::tl::enums::KeyboardButton::Url(b) => b.text.as_str(),
                            _ => continue,
                        };
                        if lbl == filter_value {
                            return Some((ri, ci));
                        }
                    }
                }
                None
            }
            "data" => {
                let want = hex::decode(filter_value).unwrap_or_default();
                for (ri, row) in rows.iter().enumerate() {
                    let buttons = match row {
                        ferogram::tl::enums::KeyboardButtonRow::KeyboardButtonRow(r) => &r.buttons,
                    };
                    for (ci, btn) in buttons.iter().enumerate() {
                        if let ferogram::tl::enums::KeyboardButton::Callback(b) = btn {
                            if b.data == want {
                                return Some((ri, ci));
                            }
                        }
                    }
                }
                None
            }
            _ => None,
        }
    }

    /// Click a button by type and value. Returns true if the click succeeded.
    /// filter_type: "pos" | "text" | "data"
    /// For "pos": filter_value is "row,col"
    /// For "text": filter_value is the button label
    /// For "data": filter_value is the callback data as hex
    fn click_button<'py>(
        &self,
        py: Python<'py>,
        filter_type: String,
        filter_value: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let client = self
            .client
            .clone()
            .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("no client on message"))?;
        let peer = self.chat_id.to_string();
        let msg_id = self.id;

        let data: Vec<u8> = match filter_type.as_str() {
            "pos" => {
                let parts: Vec<usize> = filter_value
                    .split(',')
                    .filter_map(|s| s.trim().parse().ok())
                    .collect();
                if parts.len() != 2 {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "pos filter_value must be 'row,col'",
                    ));
                }
                self._callback_data_at(parts[0], parts[1]).ok_or_else(|| {
                    pyo3::exceptions::PyValueError::new_err("no button at position")
                })?
            }
            "text" => self._callback_data_by_text(&filter_value).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err("no button with that text")
            })?,
            "data" => hex::decode(&filter_value)
                .map_err(|_| pyo3::exceptions::PyValueError::new_err("data must be hex-encoded"))?,
            _ => {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "filter_type must be 'pos', 'text', or 'data'",
                ));
            }
        };

        future_into_py(py, async move {
            let msgs = client.get_messages(peer, &[msg_id]).await.map_err(py_err)?;
            let msg = msgs
                .into_iter()
                .next()
                .ok_or_else(|| py_err("message not found"))?;
            msg.click_button(ferogram::update::ButtonFilter::Data(&data))
                .await
                .map_err(py_err)?;
            Ok(true)
        })
    }
}

pub fn from_incoming(
    m: ferogram::update::IncomingMessage,
    client: Option<Arc<ferogram::Client>>,
) -> Message {
    Message {
        id: m.id(),
        text: m.text().map(str::to_owned),
        date: m.date(),
        edit_date: m.edit_date(),
        chat_id: m.chat_id(),
        from_id: m.sender_user_id(),
        outgoing: m.outgoing(),
        mentioned: m.mentioned(),
        pinned: m.pinned(),
        reply_to_message_id: m.reply_to_message_id(),
        via_bot_id: m.via_bot_id(),
        grouped_id: m.grouped_id(),
        has_media: m.has_media(),
        has_photo: m.has_photo(),
        has_document: m.has_document(),
        is_forwarded: m.is_forwarded(),
        post_author: m.post_author().map(str::to_owned),
        view_count: m.view_count(),
        reply_count: m.reply_count(),
        client,
        _inner_markup: m.reply_markup().cloned(),
        channel_kind_cached: None,
    }
}
