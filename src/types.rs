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

// FIX E0599: variant is ::ForumTopic not ::Topic
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

#[pyclass]
pub struct InviteLinkMember {
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub date: i32,
    #[pyo3(get)]
    pub requested: bool,
    #[pyo3(get)]
    pub about: Option<String>,
}

#[pymethods]
impl InviteLinkMember {
    fn __repr__(&self) -> String {
        format!(
            "InviteLinkMember(user_id={}, requested={})",
            self.user_id, self.requested
        )
    }
}

#[pyclass]
pub struct ReadParticipant {
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub date: i32,
}

#[pymethods]
impl ReadParticipant {
    fn __repr__(&self) -> String {
        format!(
            "ReadParticipant(user_id={}, date={})",
            self.user_id, self.date
        )
    }
}

#[pyclass]
pub struct AdminLogEvent {
    #[pyo3(get)]
    pub id: i64,
    #[pyo3(get)]
    pub date: i32,
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub action: String,
}

#[pymethods]
impl AdminLogEvent {
    fn __repr__(&self) -> String {
        format!(
            "AdminLogEvent(id={}, user_id={}, action={:?})",
            self.id, self.user_id, self.action
        )
    }
}

// FIX E0609: `animated` and `videos` were removed from TL StickerSet in recent layers.
// Kept in the Python struct for API compatibility; always reported as false.
#[pyclass]
pub struct StickerSetInfo {
    #[pyo3(get)]
    pub id: i64,
    #[pyo3(get)]
    pub title: String,
    #[pyo3(get)]
    pub short_name: String,
    #[pyo3(get)]
    pub count: i32,
    #[pyo3(get)]
    pub animated: bool,
    #[pyo3(get)]
    pub videos: bool,
    #[pyo3(get)]
    pub emojis: bool,
}

#[pymethods]
impl StickerSetInfo {
    fn __repr__(&self) -> String {
        format!(
            "StickerSetInfo(title={:?}, short_name={:?}, count={})",
            self.title, self.short_name, self.count
        )
    }
}

#[pyclass]
pub struct BroadcastStats {
    #[pyo3(get)]
    pub period_min_date: i32,
    #[pyo3(get)]
    pub period_max_date: i32,
    #[pyo3(get)]
    pub followers_current: f64,
    #[pyo3(get)]
    pub followers_previous: f64,
    #[pyo3(get)]
    pub views_per_post_current: f64,
    #[pyo3(get)]
    pub views_per_post_previous: f64,
    #[pyo3(get)]
    pub shares_per_post_current: f64,
    #[pyo3(get)]
    pub shares_per_post_previous: f64,
    #[pyo3(get)]
    pub enabled_notifications_percent: f64,
}

#[pymethods]
impl BroadcastStats {
    fn __repr__(&self) -> String {
        format!(
            "BroadcastStats(followers={}, views_per_post={})",
            self.followers_current, self.views_per_post_current
        )
    }
}

#[pyclass]
pub struct MegagroupStats {
    #[pyo3(get)]
    pub period_min_date: i32,
    #[pyo3(get)]
    pub period_max_date: i32,
    #[pyo3(get)]
    pub members_current: f64,
    #[pyo3(get)]
    pub members_previous: f64,
    #[pyo3(get)]
    pub messages_current: f64,
    #[pyo3(get)]
    pub messages_previous: f64,
    #[pyo3(get)]
    pub viewers_current: f64,
    #[pyo3(get)]
    pub viewers_previous: f64,
    #[pyo3(get)]
    pub posters_current: f64,
    #[pyo3(get)]
    pub posters_previous: f64,
}

#[pymethods]
impl MegagroupStats {
    fn __repr__(&self) -> String {
        format!(
            "MegagroupStats(members={}, messages={})",
            self.members_current, self.messages_current
        )
    }
}

#[pyclass]
pub struct NotifySettings {
    #[pyo3(get)]
    pub mute_until: Option<i32>,
    #[pyo3(get)]
    pub silent: Option<bool>,
    #[pyo3(get)]
    pub show_previews: Option<bool>,
}

#[pymethods]
impl NotifySettings {
    fn __repr__(&self) -> String {
        format!(
            "NotifySettings(mute_until={:?}, silent={:?})",
            self.mute_until, self.silent
        )
    }
}

// Helper: map ferogram::tl::types::User (raw TL struct) -> Python User
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

// FIX E0308: Helper for the high-level ferogram::User wrapper (e.g. get_users_by_id).
pub fn ferogram_user_to_py(u: &ferogram::User) -> User {
    User {
        id: u.id(),
        first_name: u.first_name().unwrap_or("").to_owned(),
        last_name: u.last_name().map(str::to_owned),
        username: u.username().map(str::to_owned),
        phone: u.phone().map(str::to_owned),
        bot: u.bot(),
    }
}
