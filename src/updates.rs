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

use ferogram::PeerExt;
use ferogram::tl;
use pyo3::prelude::*;
use pyo3_async_runtimes::tokio::future_into_py;
use std::sync::Arc;

use crate::types::{ChatBoost, PreCheckoutQuery, ShippingQuery};
use crate::{message::from_incoming, py_err};

// helpers

fn reaction_str(r: &tl::enums::Reaction) -> String {
    match r {
        tl::enums::Reaction::Emoji(e) => e.emoticon.clone(),
        tl::enums::Reaction::CustomEmoji(c) => format!("custom:{}", c.document_id),
        tl::enums::Reaction::Paid => "paid".to_string(),
        tl::enums::Reaction::Empty => String::new(),
    }
}

fn action_str(a: &tl::enums::SendMessageAction) -> &'static str {
    use tl::enums::SendMessageAction as A;
    match a {
        A::SendMessageTypingAction => "typing",
        A::SendMessageCancelAction => "cancel",
        A::SendMessageRecordVideoAction => "record_video",
        A::SendMessageUploadVideoAction(_) => "upload_video",
        A::SendMessageRecordAudioAction => "record_audio",
        A::SendMessageUploadAudioAction(_) => "upload_audio",
        A::SendMessageUploadPhotoAction(_) => "upload_photo",
        A::SendMessageUploadDocumentAction(_) => "upload_document",
        A::SendMessageGeoLocationAction => "geo_location",
        A::SendMessageChooseContactAction => "choose_contact",
        A::SendMessageGamePlayAction => "game_play",
        A::SendMessageRecordRoundAction => "record_round",
        A::SendMessageUploadRoundAction(_) => "upload_round",
        A::SendMessageChooseStickerAction => "choose_sticker",
        A::SendMessageHistoryImportAction(_) => "history_import",
        A::SendMessageEmojiInteraction(_) => "emoji_interaction",
        A::SendMessageEmojiInteractionSeen(_) => "emoji_interaction_seen",
        _ => "other",
    }
}

// update types

#[pyclass]
pub struct CallbackQuery {
    #[pyo3(get)]
    pub query_id: i64,
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub message_id: Option<i32>,
    #[pyo3(get)]
    pub chat_id: Option<i64>,
    #[pyo3(get)]
    pub data: Option<String>,
    pub(crate) client: Arc<ferogram::Client>,
}

#[pymethods]
impl CallbackQuery {
    fn __repr__(&self) -> String {
        format!("CallbackQuery(id={}, data={:?})", self.query_id, self.data)
    }

    #[pyo3(signature = (text = None, alert = false))]
    fn answer<'py>(
        &self,
        py: Python<'py>,
        text: Option<String>,
        alert: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.client);
        let qid = self.query_id;
        future_into_py(py, async move {
            c.answer_callback_query(qid, text.as_deref(), alert)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }
}

#[pyclass]
pub struct MessageDeletion {
    #[pyo3(get)]
    pub message_ids: Vec<i32>,
    #[pyo3(get)]
    pub channel_id: Option<i64>,
}

#[pymethods]
impl MessageDeletion {
    fn __repr__(&self) -> String {
        format!(
            "MessageDeletion(ids={:?}, channel_id={:?})",
            self.message_ids, self.channel_id
        )
    }
}

#[pyclass]
pub struct InlineQuery {
    #[pyo3(get)]
    pub query_id: i64,
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub query: String,
    #[pyo3(get)]
    pub offset: String,
    #[pyo3(get)]
    pub peer_id: Option<i64>,
}

#[pymethods]
impl InlineQuery {
    fn __repr__(&self) -> String {
        format!(
            "InlineQuery(user_id={}, query={:?})",
            self.user_id, self.query
        )
    }
}

#[pyclass]
pub struct InlineSend {
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub query: String,
    #[pyo3(get)]
    pub result_id: String,
    #[pyo3(get)]
    pub msg_id_bytes: Option<Vec<u8>>,
    #[pyo3(get)]
    pub msg_id_dc: Option<i32>,
}

#[pymethods]
impl InlineSend {
    fn __repr__(&self) -> String {
        format!(
            "InlineSend(user_id={}, result_id={:?})",
            self.user_id, self.result_id
        )
    }
}

#[pyclass]
pub struct UserStatus {
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub online: bool,
    // unix ts when online expires; 0 when not online
    #[pyo3(get)]
    pub expires: i32,
    // last seen unix ts; 0 when unknown
    #[pyo3(get)]
    pub was_online: i32,
    // "online" | "offline" | "recently" | "last_week" | "last_month" | "unknown"
    #[pyo3(get)]
    pub status: String,
}

#[pymethods]
impl UserStatus {
    fn __repr__(&self) -> String {
        format!(
            "UserStatus(user_id={}, status={:?})",
            self.user_id, self.status
        )
    }
}

#[pyclass]
pub struct ChatAction {
    #[pyo3(get)]
    pub peer_id: i64,
    #[pyo3(get)]
    pub user_id: i64,
    // "typing" | "upload_photo" | "record_video" | "cancel" | ... | "other"
    #[pyo3(get)]
    pub action: String,
}

#[pymethods]
impl ChatAction {
    fn __repr__(&self) -> String {
        format!(
            "ChatAction(user_id={}, action={:?})",
            self.user_id, self.action
        )
    }
}

#[pyclass]
pub struct ParticipantUpdate {
    #[pyo3(get)]
    pub chat_id: i64,
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub actor_id: i64,
    #[pyo3(get)]
    pub date: i32,
    // true = channel/supergroup, false = basic group
    #[pyo3(get)]
    pub is_channel: bool,
}

#[pymethods]
impl ParticipantUpdate {
    fn __repr__(&self) -> String {
        format!(
            "ParticipantUpdate(chat_id={}, user_id={})",
            self.chat_id, self.user_id
        )
    }
}

#[pyclass]
pub struct JoinRequest {
    #[pyo3(get)]
    pub peer_id: i64,
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub about: String,
    #[pyo3(get)]
    pub date: i32,
}

#[pymethods]
impl JoinRequest {
    fn __repr__(&self) -> String {
        format!(
            "JoinRequest(user_id={}, peer_id={})",
            self.user_id, self.peer_id
        )
    }
}

#[pyclass]
pub struct MessageReaction {
    #[pyo3(get)]
    pub peer_id: i64,
    #[pyo3(get)]
    pub msg_id: i32,
    #[pyo3(get)]
    pub date: i32,
    #[pyo3(get)]
    pub actor_id: i64,
    #[pyo3(get)]
    pub old_reactions: Vec<String>,
    #[pyo3(get)]
    pub new_reactions: Vec<String>,
}

#[pymethods]
impl MessageReaction {
    fn __repr__(&self) -> String {
        format!(
            "MessageReaction(msg_id={}, new={:?})",
            self.msg_id, self.new_reactions
        )
    }
}

#[pyclass]
pub struct PollVote {
    #[pyo3(get)]
    pub poll_id: i64,
    #[pyo3(get)]
    pub peer_id: i64,
    #[pyo3(get)]
    pub positions: Vec<i32>,
}

#[pymethods]
impl PollVote {
    fn __repr__(&self) -> String {
        format!(
            "PollVote(poll_id={}, peer_id={})",
            self.poll_id, self.peer_id
        )
    }
}

#[pyclass]
pub struct BotStopped {
    #[pyo3(get)]
    pub user_id: i64,
    #[pyo3(get)]
    pub date: i32,
    #[pyo3(get)]
    pub stopped: bool,
}

#[pymethods]
impl BotStopped {
    fn __repr__(&self) -> String {
        format!(
            "BotStopped(user_id={}, stopped={})",
            self.user_id, self.stopped
        )
    }
}

/// A bot received a guest-chat inline query (bots only).
#[pyclass]
pub struct GuestChatQuery {
    #[pyo3(get)]
    pub query_id: i64,
    #[pyo3(get)]
    pub qts: i32,
    #[allow(dead_code)]
    pub(crate) client: Arc<ferogram::Client>,
}

#[pymethods]
impl GuestChatQuery {
    fn __repr__(&self) -> String {
        format!("GuestChatQuery(query_id={})", self.query_id)
    }
}

// raw fallback for unmapped update types
#[pyclass]
pub struct RawUpdate {
    #[pyo3(get)]
    pub constructor_id: u32,
    #[pyo3(get)]
    pub type_name: String,
}

#[pymethods]
impl RawUpdate {
    fn __repr__(&self) -> String {
        format!(
            "RawUpdate(cid=0x{:08x}, type={:?})",
            self.constructor_id, self.type_name
        )
    }
}

// dispatcher

pub fn update_to_py(
    py: Python<'_>,
    upd: ferogram::update::Update,
    client: Arc<ferogram::Client>,
) -> Option<(&'static str, PyObject)> {
    macro_rules! ok {
        ($key:expr, $val:expr) => {
            Some(($key, $val.into_pyobject(py).unwrap().into_any().unbind()))
        };
    }

    match upd {
        ferogram::update::Update::NewMessage(m) => {
            ok!("message", from_incoming(m, Some(Arc::clone(&client))))
        }
        ferogram::update::Update::MessageEdited(m) => {
            ok!(
                "edited_message",
                from_incoming(m, Some(Arc::clone(&client)))
            )
        }
        ferogram::update::Update::MessageDeleted(d) => {
            ok!(
                "message_deleted",
                MessageDeletion {
                    message_ids: d.message_ids,
                    channel_id: d.channel_id,
                }
            )
        }
        ferogram::update::Update::CallbackQuery(q) => {
            let chat_id = q.chat_peer.as_ref().map(|p| p.bare_id());
            ok!(
                "callback_query",
                CallbackQuery {
                    query_id: q.query_id,
                    user_id: q.user_id,
                    message_id: q.message_id,
                    chat_id,
                    data: q.data().map(str::to_owned),
                    client,
                }
            )
        }
        ferogram::update::Update::InlineQuery(q) => {
            ok!(
                "inline_query",
                InlineQuery {
                    query_id: q.query_id,
                    user_id: q.user_id,
                    query: q.query,
                    offset: q.offset,
                    peer_id: q.peer.as_ref().map(|p| p.bare_id()),
                }
            )
        }
        ferogram::update::Update::InlineSend(s) => {
            let (msg_id_bytes, msg_id_dc) = match &s.msg_id {
                Some(tl::enums::InputBotInlineMessageId::InputBotInlineMessageId(id)) => {
                    use ferogram::tl::Serializable;
                    (Some(id.to_bytes()), Some(id.dc_id))
                }
                Some(tl::enums::InputBotInlineMessageId::Id64(id)) => {
                    use ferogram::tl::Serializable;
                    (Some(id.to_bytes()), Some(id.dc_id))
                }
                None => (None, None),
            };
            ok!(
                "inline_send",
                InlineSend {
                    user_id: s.user_id,
                    query: s.query,
                    result_id: s.id,
                    msg_id_bytes,
                    msg_id_dc,
                }
            )
        }
        ferogram::update::Update::UserStatus(s) => {
            let (online, expires, was_online, status_s) = match &s.status {
                tl::enums::UserStatus::Online(o) => (true, o.expires, 0, "online"),
                tl::enums::UserStatus::Offline(o) => (false, 0, o.was_online, "offline"),
                tl::enums::UserStatus::Recently(_) => (false, 0, 0, "recently"),
                tl::enums::UserStatus::LastWeek(_) => (false, 0, 0, "last_week"),
                tl::enums::UserStatus::LastMonth(_) => (false, 0, 0, "last_month"),
                tl::enums::UserStatus::Empty => (false, 0, 0, "unknown"),
            };
            ok!(
                "user_status",
                UserStatus {
                    user_id: s.user_id,
                    online,
                    expires,
                    was_online,
                    status: status_s.to_string(),
                }
            )
        }
        ferogram::update::Update::UserTyping(a) => {
            ok!(
                "chat_action",
                ChatAction {
                    peer_id: a.peer.bare_id(),
                    user_id: a.user_id,
                    action: action_str(&a.action).to_string(),
                }
            )
        }
        ferogram::update::Update::ParticipantUpdate(p) => {
            ok!(
                "participant_update",
                ParticipantUpdate {
                    chat_id: p.chat_id,
                    user_id: p.user_id,
                    actor_id: p.actor_id,
                    date: p.date,
                    is_channel: p.is_channel,
                }
            )
        }
        ferogram::update::Update::JoinRequest(r) => {
            ok!(
                "join_request",
                JoinRequest {
                    peer_id: r.peer.bare_id(),
                    user_id: r.user_id,
                    about: r.about,
                    date: r.date,
                }
            )
        }
        ferogram::update::Update::MessageReaction(r) => {
            ok!(
                "message_reaction",
                MessageReaction {
                    peer_id: r.peer.bare_id(),
                    msg_id: r.msg_id,
                    date: r.date,
                    actor_id: r.actor.bare_id(),
                    old_reactions: r.old_reactions.iter().map(reaction_str).collect(),
                    new_reactions: r.new_reactions.iter().map(reaction_str).collect(),
                }
            )
        }
        ferogram::update::Update::PollVote(v) => {
            ok!(
                "poll_vote",
                PollVote {
                    poll_id: v.poll_id,
                    peer_id: v.peer.bare_id(),
                    positions: v.positions,
                }
            )
        }
        ferogram::update::Update::BotStopped(b) => {
            ok!(
                "bot_stopped",
                BotStopped {
                    user_id: b.user_id,
                    date: b.date,
                    stopped: b.stopped,
                }
            )
        }
        ferogram::update::Update::ShippingQuery(q) => {
            let addr = &q.shipping_address;
            ok!(
                "shipping_query",
                ShippingQuery {
                    query_id: q.query_id,
                    user_id: q.user_id,
                    payload: q.payload.clone(),
                    street_line1: addr.street_line1.clone(),
                    city: addr.city.clone(),
                    country_iso2: addr.country_iso2.clone(),
                }
            )
        }
        ferogram::update::Update::PreCheckoutQuery(q) => {
            ok!(
                "pre_checkout_query",
                PreCheckoutQuery {
                    query_id: q.query_id,
                    user_id: q.user_id,
                    payload: q.payload.clone(),
                    currency: q.currency.clone(),
                    total_amount: q.total_amount,
                    shipping_option_id: q.shipping_option_id.clone(),
                }
            )
        }
        ferogram::update::Update::ChatBoost(b) => {
            let peer_id = match &b.peer {
                ferogram::tl::enums::Peer::User(u) => u.user_id,
                ferogram::tl::enums::Peer::Chat(c) => c.chat_id,
                ferogram::tl::enums::Peer::Channel(c) => c.channel_id,
            };
            ok!(
                "chat_boost",
                ChatBoost {
                    peer_id,
                    qts: b.qts,
                }
            )
        }
        ferogram::update::Update::GuestChatQuery(q) => {
            ok!(
                "guest_chat_query",
                GuestChatQuery {
                    query_id: q.query_id,
                    qts: q.qts,
                    client,
                }
            )
        }
        ferogram::update::Update::Raw(r) => {
            let name = format!("{:?}", r.inner)
                .split('(')
                .next()
                .unwrap_or("Unknown")
                .to_string();
            ok!(
                "raw_update",
                RawUpdate {
                    constructor_id: r.constructor_id,
                    type_name: name,
                }
            )
        }
        _ => None,
    }
}
