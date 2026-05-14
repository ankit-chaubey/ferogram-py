// Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
// SPDX-License-Identifier: MIT OR Apache-2.0

use ferogram::tl;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

// InlineButton

/// A single inline keyboard button.
///
/// Create one with the static factory methods, then pass a list of buttons to
/// `InlineKeyboard.add_row()`.
///
/// # Examples
///
///     from ferogram import InlineButton, InlineKeyboard
///
///     kb = InlineKeyboard()
///     kb.add_row([InlineButton.callback("Yes", b"yes"), InlineButton.callback("No", b"no")])
///     kb.add_row([InlineButton.url("Visit", "https://example.com")])
#[pyclass]
#[derive(Clone)]
pub struct InlineButton {
    text: String,
    kind: InlineBtnKind,
}

#[derive(Clone)]
enum InlineBtnKind {
    Callback(Vec<u8>),
    Url(String),
    SwitchInline(String),
    SwitchElsewhere(String),
    CopyText(String),
    MiniApp(String),
    MiniAppSimple(String),
    Game,
    Buy,
}

impl InlineButton {
    pub(crate) fn to_tl(&self) -> tl::enums::KeyboardButton {
        match &self.kind {
            InlineBtnKind::Callback(data) => {
                tl::enums::KeyboardButton::Callback(tl::types::KeyboardButtonCallback {
                    requires_password: false,
                    text: self.text.clone(),
                    data: data.clone(),
                    style: None,
                })
            }
            InlineBtnKind::Url(url) => {
                tl::enums::KeyboardButton::Url(tl::types::KeyboardButtonUrl {
                    text: self.text.clone(),
                    url: url.clone(),
                    style: None,
                })
            }
            InlineBtnKind::SwitchInline(query) => {
                tl::enums::KeyboardButton::SwitchInline(tl::types::KeyboardButtonSwitchInline {
                    same_peer: true,
                    peer_types: None,
                    text: self.text.clone(),
                    query: query.clone(),
                    style: None,
                })
            }
            InlineBtnKind::SwitchElsewhere(query) => {
                tl::enums::KeyboardButton::SwitchInline(tl::types::KeyboardButtonSwitchInline {
                    same_peer: false,
                    peer_types: None,
                    text: self.text.clone(),
                    query: query.clone(),
                    style: None,
                })
            }
            InlineBtnKind::CopyText(copy) => {
                tl::enums::KeyboardButton::Copy(tl::types::KeyboardButtonCopy {
                    text: self.text.clone(),
                    copy_text: copy.clone(),
                    style: None,
                })
            }
            InlineBtnKind::MiniApp(url) => {
                tl::enums::KeyboardButton::WebView(tl::types::KeyboardButtonWebView {
                    text: self.text.clone(),
                    url: url.clone(),
                    style: None,
                })
            }
            InlineBtnKind::MiniAppSimple(url) => {
                tl::enums::KeyboardButton::SimpleWebView(tl::types::KeyboardButtonSimpleWebView {
                    text: self.text.clone(),
                    url: url.clone(),
                    style: None,
                })
            }
            InlineBtnKind::Game => tl::enums::KeyboardButton::Game(tl::types::KeyboardButtonGame {
                text: self.text.clone(),
                style: None,
            }),
            InlineBtnKind::Buy => tl::enums::KeyboardButton::Buy(tl::types::KeyboardButtonBuy {
                text: self.text.clone(),
                style: None,
            }),
        }
    }
}

#[pymethods]
impl InlineButton {
    /// Button that sends `data` as a callback query when pressed.
    #[staticmethod]
    fn callback(text: String, data: Vec<u8>) -> Self {
        Self {
            text,
            kind: InlineBtnKind::Callback(data),
        }
    }

    /// Button that opens `url` in the browser.
    #[staticmethod]
    fn url(text: String, url: String) -> Self {
        Self {
            text,
            kind: InlineBtnKind::Url(url),
        }
    }

    /// Button that switches to inline mode in the current chat with `query` prefilled.
    #[staticmethod]
    fn switch_inline(text: String, query: String) -> Self {
        Self {
            text,
            kind: InlineBtnKind::SwitchInline(query),
        }
    }

    /// Button that switches to inline mode in a user-chosen (different) chat.
    #[staticmethod]
    fn switch_elsewhere(text: String, query: String) -> Self {
        Self {
            text,
            kind: InlineBtnKind::SwitchElsewhere(query),
        }
    }

    /// Button that copies `copy_text` to clipboard when pressed.
    #[staticmethod]
    fn copy_text(text: String, copy_text: String) -> Self {
        Self {
            text,
            kind: InlineBtnKind::CopyText(copy_text),
        }
    }

    /// Button that opens a mini-app (full WebView with JS bridge).
    #[staticmethod]
    fn mini_app(text: String, url: String) -> Self {
        Self {
            text,
            kind: InlineBtnKind::MiniApp(url),
        }
    }

    /// Button that opens a simple mini-app (no JS bridge, no query_id).
    #[staticmethod]
    fn mini_app_simple(text: String, url: String) -> Self {
        Self {
            text,
            kind: InlineBtnKind::MiniAppSimple(url),
        }
    }

    /// Game launch button (bots only; must be the first button in the first row).
    #[staticmethod]
    fn game(text: String) -> Self {
        Self {
            text,
            kind: InlineBtnKind::Game,
        }
    }

    /// Payment buy button (bots only; must be the first button in the first row).
    #[staticmethod]
    fn buy(text: String) -> Self {
        Self {
            text,
            kind: InlineBtnKind::Buy,
        }
    }

    fn __repr__(&self) -> String {
        let kind = match &self.kind {
            InlineBtnKind::Callback(_) => "callback",
            InlineBtnKind::Url(_) => "url",
            InlineBtnKind::SwitchInline(_) => "switch_inline",
            InlineBtnKind::SwitchElsewhere(_) => "switch_elsewhere",
            InlineBtnKind::CopyText(_) => "copy_text",
            InlineBtnKind::MiniApp(_) => "mini_app",
            InlineBtnKind::MiniAppSimple(_) => "mini_app_simple",
            InlineBtnKind::Game => "game",
            InlineBtnKind::Buy => "buy",
        };
        format!("InlineButton({:?}, kind={})", self.text, kind)
    }
}

// InlineKeyboard

/// Inline keyboard attached to a message.
///
/// Build the keyboard by adding rows of `InlineButton`s, then pass it as
/// `reply_markup` to `send_message`.
///
/// # Examples
///
///     kb = InlineKeyboard()
///     kb.add_row([InlineButton.callback("Yes", b"yes"), InlineButton.callback("No", b"no")])
///     kb.add_row([InlineButton.url("Docs", "https://example.com")])
///     await client.send_message(peer, "Choose:", reply_markup=kb)
#[pyclass]
pub struct InlineKeyboard {
    rows: Vec<Vec<InlineButton>>,
}

#[pymethods]
impl InlineKeyboard {
    #[new]
    fn new() -> Self {
        Self { rows: vec![] }
    }

    /// Append a row of inline buttons. Buttons appear left-to-right within the row.
    fn add_row(&mut self, buttons: Vec<PyRef<InlineButton>>) -> PyResult<()> {
        if buttons.is_empty() {
            return Err(PyValueError::new_err(
                "row must contain at least one button",
            ));
        }
        self.rows
            .push(buttons.iter().map(|b| (**b).clone()).collect());
        Ok(())
    }

    /// Number of rows currently in the keyboard.
    #[getter]
    fn row_count(&self) -> usize {
        self.rows.len()
    }

    fn __repr__(&self) -> String {
        format!("InlineKeyboard(rows={})", self.rows.len())
    }
}

impl InlineKeyboard {
    pub(crate) fn to_tl_markup(&self) -> tl::enums::ReplyMarkup {
        let rows = self
            .rows
            .iter()
            .map(|row| {
                tl::enums::KeyboardButtonRow::KeyboardButtonRow(tl::types::KeyboardButtonRow {
                    buttons: row.iter().map(|b| b.to_tl()).collect(),
                })
            })
            .collect();
        tl::enums::ReplyMarkup::ReplyInlineMarkup(tl::types::ReplyInlineMarkup { rows })
    }
}

// ReplyButton

/// A single button for a reply keyboard (shown below the text input box).
///
/// The most common type is `ReplyButton.text("label")` which sends that text
/// when pressed. Specialised variants like `request_phone` or `request_geo`
/// prompt the user to share data.
#[pyclass]
#[derive(Clone)]
pub struct ReplyButton {
    text: String,
    kind: ReplyBtnKind,
}

#[derive(Clone)]
enum ReplyBtnKind {
    Text,
    RequestPhone,
    RequestGeo,
    RequestPoll,
    RequestQuiz,
}

impl ReplyButton {
    fn to_tl(&self) -> tl::enums::KeyboardButton {
        match self.kind {
            ReplyBtnKind::Text => {
                tl::enums::KeyboardButton::KeyboardButton(tl::types::KeyboardButton {
                    text: self.text.clone(),
                    style: None,
                })
            }
            ReplyBtnKind::RequestPhone => {
                tl::enums::KeyboardButton::RequestPhone(tl::types::KeyboardButtonRequestPhone {
                    text: self.text.clone(),
                    style: None,
                })
            }
            ReplyBtnKind::RequestGeo => tl::enums::KeyboardButton::RequestGeoLocation(
                tl::types::KeyboardButtonRequestGeoLocation {
                    text: self.text.clone(),
                    style: None,
                },
            ),
            ReplyBtnKind::RequestPoll => {
                tl::enums::KeyboardButton::RequestPoll(tl::types::KeyboardButtonRequestPoll {
                    quiz: None,
                    text: self.text.clone(),
                    style: None,
                })
            }
            ReplyBtnKind::RequestQuiz => {
                tl::enums::KeyboardButton::RequestPoll(tl::types::KeyboardButtonRequestPoll {
                    quiz: Some(true),
                    text: self.text.clone(),
                    style: None,
                })
            }
        }
    }
}

#[pymethods]
impl ReplyButton {
    /// Plain text button; pressing it sends that text as a message.
    #[staticmethod]
    fn text(label: String) -> Self {
        Self {
            text: label,
            kind: ReplyBtnKind::Text,
        }
    }

    /// Button that prompts the user to share their phone number.
    #[staticmethod]
    fn request_phone(label: String) -> Self {
        Self {
            text: label,
            kind: ReplyBtnKind::RequestPhone,
        }
    }

    /// Button that prompts the user to share their location.
    #[staticmethod]
    fn request_geo(label: String) -> Self {
        Self {
            text: label,
            kind: ReplyBtnKind::RequestGeo,
        }
    }

    /// Button that asks the user to create and share a poll.
    #[staticmethod]
    fn request_poll(label: String) -> Self {
        Self {
            text: label,
            kind: ReplyBtnKind::RequestPoll,
        }
    }

    /// Button that asks the user to create and share a quiz.
    #[staticmethod]
    fn request_quiz(label: String) -> Self {
        Self {
            text: label,
            kind: ReplyBtnKind::RequestQuiz,
        }
    }

    fn __repr__(&self) -> String {
        format!("ReplyButton({:?})", self.text)
    }
}

// ReplyKeyboard

/// Reply keyboard shown below the message input box.
///
/// # Examples
///
///     kb = ReplyKeyboard(resize=True)
///     kb.add_row([ReplyButton.text("Option A"), ReplyButton.text("Option B")])
///     kb.add_row([ReplyButton.request_phone("Share phone")])
///     await client.send_message(peer, "Pick one:", reply_markup=kb)
#[pyclass]
pub struct ReplyKeyboard {
    rows: Vec<Vec<ReplyButton>>,
    resize: bool,
    single_use: bool,
    selective: bool,
    placeholder: Option<String>,
}

#[pymethods]
impl ReplyKeyboard {
    /// Create a new reply keyboard.
    ///
    /// - `resize`: shrink the keyboard to fit its content (recommended for short keyboards).
    /// - `single_use`: hide the keyboard after a single press.
    /// - `selective`: show only to mentioned or replied-to users.
    /// - `placeholder`: hint text shown in the input box when the keyboard is active.
    #[new]
    #[pyo3(signature = (*, resize=false, single_use=false, selective=false, placeholder=None))]
    fn new(resize: bool, single_use: bool, selective: bool, placeholder: Option<String>) -> Self {
        Self {
            rows: vec![],
            resize,
            single_use,
            selective,
            placeholder,
        }
    }

    /// Append a row of reply buttons.
    fn add_row(&mut self, buttons: Vec<PyRef<ReplyButton>>) -> PyResult<()> {
        if buttons.is_empty() {
            return Err(PyValueError::new_err(
                "row must contain at least one button",
            ));
        }
        self.rows
            .push(buttons.iter().map(|b| (**b).clone()).collect());
        Ok(())
    }

    /// Number of rows currently in the keyboard.
    #[getter]
    fn row_count(&self) -> usize {
        self.rows.len()
    }

    fn __repr__(&self) -> String {
        format!(
            "ReplyKeyboard(rows={}, resize={}, single_use={})",
            self.rows.len(),
            self.resize,
            self.single_use
        )
    }
}

impl ReplyKeyboard {
    pub(crate) fn to_tl_markup(&self) -> tl::enums::ReplyMarkup {
        let rows = self
            .rows
            .iter()
            .map(|row| {
                tl::enums::KeyboardButtonRow::KeyboardButtonRow(tl::types::KeyboardButtonRow {
                    buttons: row.iter().map(|b| b.to_tl()).collect(),
                })
            })
            .collect();
        tl::enums::ReplyMarkup::ReplyKeyboardMarkup(tl::types::ReplyKeyboardMarkup {
            resize: self.resize,
            single_use: self.single_use,
            selective: self.selective,
            persistent: false,
            rows,
            placeholder: self.placeholder.clone(),
        })
    }
}

// RemoveKeyboard

/// Removes any currently visible reply keyboard.
///
///     await client.send_message(peer, "Done!", reply_markup=RemoveKeyboard())
#[pyclass]
pub struct RemoveKeyboard {
    selective: bool,
}

#[pymethods]
impl RemoveKeyboard {
    #[new]
    #[pyo3(signature = (selective=false))]
    fn new(selective: bool) -> Self {
        Self { selective }
    }

    fn __repr__(&self) -> String {
        format!("RemoveKeyboard(selective={})", self.selective)
    }
}

impl RemoveKeyboard {
    pub(crate) fn to_tl_markup(&self) -> tl::enums::ReplyMarkup {
        tl::enums::ReplyMarkup::ReplyKeyboardHide(tl::types::ReplyKeyboardHide {
            selective: self.selective,
        })
    }
}

// ForceReply

/// Forces the client UI to open a reply dialog for this message.
///
///     await client.send_message(peer, "Reply to this:", reply_markup=ForceReply())
#[pyclass]
pub struct ForceReply {
    single_use: bool,
    selective: bool,
    placeholder: Option<String>,
}

#[pymethods]
impl ForceReply {
    #[new]
    #[pyo3(signature = (*, single_use=false, selective=false, placeholder=None))]
    fn new(single_use: bool, selective: bool, placeholder: Option<String>) -> Self {
        Self {
            single_use,
            selective,
            placeholder,
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "ForceReply(single_use={}, selective={})",
            self.single_use, self.selective
        )
    }
}

impl ForceReply {
    pub(crate) fn to_tl_markup(&self) -> tl::enums::ReplyMarkup {
        tl::enums::ReplyMarkup::ReplyKeyboardForceReply(tl::types::ReplyKeyboardForceReply {
            single_use: self.single_use,
            selective: self.selective,
            placeholder: self.placeholder.clone(),
        })
    }
}

// Helper: extract any markup type from a Python object

pub(crate) fn extract_markup(obj: &Bound<'_, PyAny>) -> PyResult<tl::enums::ReplyMarkup> {
    if let Ok(kb) = obj.downcast::<InlineKeyboard>() {
        return Ok(kb.borrow().to_tl_markup());
    }
    if let Ok(kb) = obj.downcast::<ReplyKeyboard>() {
        return Ok(kb.borrow().to_tl_markup());
    }
    if let Ok(rm) = obj.downcast::<RemoveKeyboard>() {
        return Ok(rm.borrow().to_tl_markup());
    }
    if let Ok(fr) = obj.downcast::<ForceReply>() {
        return Ok(fr.borrow().to_tl_markup());
    }
    Err(PyValueError::new_err(
        "reply_markup must be InlineKeyboard, ReplyKeyboard, RemoveKeyboard, or ForceReply",
    ))
}
