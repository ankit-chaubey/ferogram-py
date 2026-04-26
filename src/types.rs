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

// Simple data types returned from account/dialog calls.

use pyo3::prelude::*;

#[pyclass]
pub struct User {
    #[pyo3(get)]
    pub id: i64,
    #[pyo3(get)]
    pub first_name: String,
    #[pyo3(get)]
    pub last_name: Option<String>,
    #[pyo3(get)]
    pub username: Option<String>,
    #[pyo3(get)]
    pub phone: Option<String>,
    #[pyo3(get)]
    pub bot: bool,
}

#[pymethods]
impl User {
    fn __repr__(&self) -> String {
        format!(
            "User(id={}, username={:?}, first_name={:?})",
            self.id, self.username, self.first_name
        )
    }

    #[getter]
    fn full_name(&self) -> String {
        match &self.last_name {
            Some(ln) => format!("{} {}", self.first_name, ln),
            None => self.first_name.clone(),
        }
    }

    #[getter]
    fn mention(&self) -> String {
        match &self.username {
            Some(u) => format!("@{}", u),
            None => self.first_name.clone(),
        }
    }
}

#[pyclass]
pub struct Dialog {
    #[pyo3(get)]
    pub title: String,
    #[pyo3(get)]
    pub unread_count: i32,
    #[pyo3(get)]
    pub top_message: i32,
}

#[pymethods]
impl Dialog {
    fn __repr__(&self) -> String {
        format!(
            "Dialog(title={:?}, unread={})",
            self.title, self.unread_count
        )
    }
}

// Returned from get_chat_administrators.
// status: "creator" | "admin" | "member" | "restricted" | "left" | "banned"
#[pyclass]
pub struct ChatMember {
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub first_name: String,
    #[pyo3(get)]
    pub last_name: Option<String>,
    #[pyo3(get)]
    pub username: Option<String>,
    #[pyo3(get)]
    pub bot: bool,
    #[pyo3(get)]
    pub status: String,
    #[pyo3(get)]
    pub admin_rank: Option<String>,
}

#[pymethods]
impl ChatMember {
    fn __repr__(&self) -> String {
        format!(
            "ChatMember(user_id={}, status={:?})",
            self.user_id, self.status
        )
    }

    #[getter]
    fn is_admin(&self) -> bool {
        self.status == "admin" || self.status == "creator"
    }

    #[getter]
    fn is_creator(&self) -> bool {
        self.status == "creator"
    }

    #[getter]
    fn full_name(&self) -> String {
        match &self.last_name {
            Some(ln) => format!("{} {}", self.first_name, ln),
            None => self.first_name.clone(),
        }
    }
}

// Returned from get_user_full.
#[pyclass]
pub struct UserFull {
    #[pyo3(get)]
    pub id: i64,
    #[pyo3(get)]
    pub about: Option<String>,
    #[pyo3(get)]
    pub common_chats_count: i32,
    #[pyo3(get)]
    pub blocked: bool,
    #[pyo3(get)]
    pub phone_calls_available: bool,
    #[pyo3(get)]
    pub video_calls_available: bool,
}

#[pymethods]
impl UserFull {
    fn __repr__(&self) -> String {
        format!(
            "UserFull(id={}, about={:?}, blocked={})",
            self.id, self.about, self.blocked
        )
    }
}

// Returned from create_group / create_channel / get_common_chats.
#[pyclass]
pub struct Chat {
    #[pyo3(get)]
    pub id: i64,
    #[pyo3(get)]
    pub title: String,
    #[pyo3(get)]
    pub is_channel: bool,
    #[pyo3(get)]
    pub is_megagroup: bool,
    #[pyo3(get)]
    pub username: Option<String>,
    #[pyo3(get)]
    pub members_count: Option<i32>,
}

#[pymethods]
impl Chat {
    fn __repr__(&self) -> String {
        format!("Chat(id={}, title={:?})", self.id, self.title)
    }

    #[getter]
    fn is_group(&self) -> bool {
        !self.is_channel
    }

    #[getter]
    fn is_broadcast(&self) -> bool {
        self.is_channel && !self.is_megagroup
    }

    #[getter]
    fn is_supergroup(&self) -> bool {
        self.is_channel && self.is_megagroup
    }
}

pub fn tl_chat_to_py(c: &ferogram::tl::enums::Chat) -> Option<Chat> {
    match c {
        ferogram::tl::enums::Chat::Chat(ch) => Some(Chat {
            id: ch.id,
            title: ch.title.clone(),
            is_channel: false,
            is_megagroup: false,
            username: None,
            members_count: Some(ch.participants_count),
        }),
        ferogram::tl::enums::Chat::Channel(ch) => Some(Chat {
            id: ch.id,
            title: ch.title.clone(),
            is_channel: true,
            is_megagroup: ch.megagroup,
            username: ch.username.clone(),
            members_count: ch.participants_count,
        }),
        _ => None,
    }
}

// Returned from get_authorizations.
#[pyclass]
pub struct Authorization {
    #[pyo3(get)]
    pub hash: i64,
    #[pyo3(get)]
    pub device_model: String,
    #[pyo3(get)]
    pub platform: String,
    #[pyo3(get)]
    pub system_version: String,
    #[pyo3(get)]
    pub app_name: String,
    #[pyo3(get)]
    pub app_version: String,
    #[pyo3(get)]
    pub date_created: i32,
    #[pyo3(get)]
    pub date_active: i32,
    #[pyo3(get)]
    pub ip: String,
    #[pyo3(get)]
    pub country: String,
    #[pyo3(get)]
    pub region: String,
    #[pyo3(get)]
    pub current: bool,
}

#[pymethods]
impl Authorization {
    fn __repr__(&self) -> String {
        format!(
            "Authorization(device={:?}, country={:?}, current={})",
            self.device_model, self.country, self.current
        )
    }
}

// Returned from get_forum_topics.
#[pyclass]
pub struct ForumTopic {
    #[pyo3(get)]
    pub id: i32,
    #[pyo3(get)]
    pub title: String,
    #[pyo3(get)]
    pub top_message: i32,
    #[pyo3(get)]
    pub unread_count: i32,
    #[pyo3(get)]
    pub date: i32,
    #[pyo3(get)]
    pub closed: bool,
    #[pyo3(get)]
    pub hidden: bool,
}

#[pymethods]
impl ForumTopic {
    fn __repr__(&self) -> String {
        format!("ForumTopic(id={}, title={:?})", self.id, self.title)
    }
}

pub fn tl_forum_topic_to_py(t: &ferogram::tl::enums::ForumTopic) -> Option<ForumTopic> {
    match t {
        ferogram::tl::enums::ForumTopic::ForumTopic(t) => Some(ForumTopic {
            id: t.id,
            title: t.title.clone(),
            top_message: t.top_message,
            unread_count: t.unread_count,
            date: t.date,
            closed: t.closed,
            hidden: t.hidden,
        }),
        _ => None,
    }
}

// Returned from get_bot_info.
#[pyclass]
pub struct BotInfo {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub about: String,
    #[pyo3(get)]
    pub description: String,
}

#[pymethods]
impl BotInfo {
    fn __repr__(&self) -> String {
        format!("BotInfo(name={:?})", self.name)
    }
}

// Helper: map tl::types::User -> Python User
pub fn tl_user_to_py(u: &ferogram::tl::types::User) -> User {
    User {
        id: u.id,
        first_name: u.first_name.clone().unwrap_or_default(),
        last_name: u.last_name.clone(),
        username: u.username.clone(),
        phone: u.phone.clone(),
        bot: u.bot,
    }
}
