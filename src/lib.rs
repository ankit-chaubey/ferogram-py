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

pub mod auth;
pub mod client;
pub mod message;
pub mod raw;
pub mod types;
pub mod updates;

pub fn py_err(e: impl std::fmt::Display) -> PyErr {
    PyRuntimeError::new_err(e.to_string())
}

#[pymodule]
fn _ferogram(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<client::Client>()?;
    m.add_class::<auth::ClientBuilder>()?;
    m.add_class::<auth::LoginToken>()?;
    m.add_class::<auth::PasswordToken>()?;
    m.add_class::<message::Message>()?;
    m.add_class::<types::User>()?;
    m.add_class::<types::Dialog>()?;
    m.add_class::<types::ChatMember>()?;
    m.add_class::<types::UserFull>()?;
    m.add_class::<types::Chat>()?;
    m.add_class::<types::Authorization>()?;
    m.add_class::<types::ForumTopic>()?;
    m.add_class::<types::BotInfo>()?;
    m.add_class::<types::InviteLinkMember>()?;
    m.add_class::<types::ReadParticipant>()?;
    m.add_class::<types::AdminLogEvent>()?;
    m.add_class::<types::StickerSetInfo>()?;
    m.add_class::<types::BroadcastStats>()?;
    m.add_class::<types::MegagroupStats>()?;
    m.add_class::<types::NotifySettings>()?;
    // update types
    m.add_class::<updates::CallbackQuery>()?;
    m.add_class::<updates::MessageDeletion>()?;
    m.add_class::<updates::InlineQuery>()?;
    m.add_class::<updates::InlineSend>()?;
    m.add_class::<updates::UserStatus>()?;
    m.add_class::<updates::ChatAction>()?;
    m.add_class::<updates::ParticipantUpdate>()?;
    m.add_class::<updates::JoinRequest>()?;
    m.add_class::<updates::MessageReaction>()?;
    m.add_class::<updates::PollVote>()?;
    m.add_class::<updates::BotStopped>()?;
    m.add_class::<updates::RawUpdate>()?;
    // new in 0.3.6 / updated in 0.3.7 (binding v0.2.0)
    m.add_class::<types::ShippingQuery>()?;
    m.add_class::<types::PreCheckoutQuery>()?;
    m.add_class::<types::ChatBoost>()?;
    m.add_class::<types::MiniAppSession>()?;
    Ok(())
}
