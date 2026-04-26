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

fn action_from_str(s: &str) -> ferogram::tl::enums::SendMessageAction {
    use ferogram::tl::enums::SendMessageAction as A;
    use ferogram::tl::types as tt;
    match s {
        "upload_photo" => {
            A::SendMessageUploadPhotoAction(tt::SendMessageUploadPhotoAction { progress: 0 })
        }
        "record_video" => A::SendMessageRecordVideoAction,
        "upload_video" => {
            A::SendMessageUploadVideoAction(tt::SendMessageUploadVideoAction { progress: 0 })
        }
        "record_audio" => A::SendMessageRecordAudioAction,
        "upload_audio" => {
            A::SendMessageUploadAudioAction(tt::SendMessageUploadAudioAction { progress: 0 })
        }
        "upload_document" => {
            A::SendMessageUploadDocumentAction(tt::SendMessageUploadDocumentAction { progress: 0 })
        }
        "geo_location" => A::SendMessageGeoLocationAction,
        "choose_contact" => A::SendMessageChooseContactAction,
        "game_play" => A::SendMessageGamePlayAction,
        "record_round" => A::SendMessageRecordRoundAction,
        "upload_round" => {
            A::SendMessageUploadRoundAction(tt::SendMessageUploadRoundAction { progress: 0 })
        }
        "choose_sticker" => A::SendMessageChooseStickerAction,
        "cancel" => A::SendMessageCancelAction,
        _ => A::SendMessageTypingAction,
    }
}

fn participant_status(p: &ferogram::participants::Participant) -> (&'static str, Option<String>) {
    use ferogram::participants::ParticipantStatus as S;
    match &p.status {
        S::Creator => ("creator", None),
        S::Admin => {
            let rank: Option<String> = None;
            ("admin", rank)
        }
        S::Member => ("member", None),
        S::Restricted => ("restricted", None),
        S::Left => ("left", None),
        S::Banned => ("banned", None),
    }
}

#[pymethods]
impl Client {
    #[staticmethod]
    fn builder(api_id: i32, api_hash: String, session: String) -> ClientBuilder {
        ClientBuilder {
            api_id,
            api_hash,
            session,
        }
    }

    fn is_authorized<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.is_authorized().await.map_err(py_err) })
    }

    fn request_login_code<'py>(
        &self,
        py: Python<'py>,
        phone: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let tok = c.request_login_code(&phone).await.map_err(py_err)?;
            Ok(LoginToken(Arc::new(std::sync::Mutex::new(Some(tok)))))
        })
    }

    fn sign_in<'py>(
        &self,
        py: Python<'py>,
        token: &LoginToken,
        code: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        let owned = {
            let mut g = token.0.lock().map_err(py_err)?;
            g.take()
                .ok_or_else(|| PyRuntimeError::new_err("LoginToken already consumed"))?
        };
        future_into_py(py, async move {
            match c.sign_in(&owned, &code).await {
                Ok(_) => Ok(None::<PasswordToken>),
                Err(ferogram::SignInError::PasswordRequired(box_tok)) => {
                    let hint = box_tok.hint().map(str::to_owned);
                    Ok(Some(PasswordToken {
                        inner: Arc::new(std::sync::Mutex::new(Some(*box_tok))),
                        hint,
                    }))
                }
                Err(e) => Err(py_err(e)),
            }
        })
    }

    fn check_password<'py>(
        &self,
        py: Python<'py>,
        token: &PasswordToken,
        password: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        let owned = {
            let mut g = token.inner.lock().map_err(py_err)?;
            g.take()
                .ok_or_else(|| PyRuntimeError::new_err("PasswordToken already consumed"))?
        };
        future_into_py(py, async move {
            c.check_password(owned, password.as_bytes())
                .await
                .map_err(py_err)
        })
    }

    fn bot_sign_in<'py>(&self, py: Python<'py>, token: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(
            py,
            async move { c.bot_sign_in(&token).await.map_err(py_err) },
        )
    }

    fn save_session<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.save_session().await.map_err(py_err)?;
            Ok(())
        })
    }

    fn sign_out<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.sign_out().await.map_err(py_err) })
    }

    fn export_session_string<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.export_session_string().await.map_err(py_err)
        })
    }

    fn next_update<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        let stream = Arc::clone(&self.stream);
        future_into_py(py, async move {
            let upd = stream.lock().await.next().await;
            match upd {
                None => Ok(None::<(String, PyObject)>),
                Some(u) => Python::with_gil(|py| {
                    Ok(crate::updates::update_to_py(py, u, c).map(|(k, v)| (k.to_owned(), v)))
                }),
            }
        })
    }

    // messaging

    fn send_message<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        text: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let m = c.send_message(&peer, &text).await.map_err(py_err)?;
            Ok(from_incoming(m, Some(c)))
        })
    }

    fn send_html<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        html: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            Ok(from_incoming(
                c.send_html(peer, &html).await.map_err(py_err)?,
                Some(c),
            ))
        })
    }

    fn send_markdown<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        md: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            Ok(from_incoming(
                c.send_markdown(peer, &md).await.map_err(py_err)?,
                Some(c),
            ))
        })
    }

    fn send_to_self<'py>(&self, py: Python<'py>, text: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.send_to_self(&text).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn edit_message<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        message_id: i32,
        new_text: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.edit_message(peer, message_id, &new_text)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn delete_messages<'py>(
        &self,
        py: Python<'py>,
        message_ids: Vec<i32>,
        revoke: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_messages(message_ids, revoke)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn forward_messages<'py>(
        &self,
        py: Python<'py>,
        destination: String,
        source: String,
        message_ids: Vec<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.forward_messages(destination, &message_ids, source)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn pin_message<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        message_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.pin_message(peer, message_id, false, false, false)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn unpin_message<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        message_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.unpin_message(peer, message_id).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn unpin_all_messages<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.unpin_all_messages(peer).await.map_err(py_err)?;
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

    fn clear_mentions<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.clear_mentions(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn send_reaction<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        message_id: i32,
        emoji: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.send_reaction(
                peer,
                message_id,
                ferogram::reactions::InputReactions::emoticon(&emoji),
            )
            .await
            .map_err(py_err)?;
            Ok(())
        })
    }

    fn send_chat_action<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        action: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.send_chat_action(peer, action_from_str(&action))
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn get_messages_by_id<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        ids: Vec<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c.get_messages_by_id(peer, &ids).await.map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    fn send_dice<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        emoji: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.send_dice(peer, emoji).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn delete_dialog<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_dialog(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn get_online_count<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let n = c.get_online_count(peer).await.map_err(py_err)?;
            Ok(n)
        })
    }

    // chat membership

    fn join_chat<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.join_chat(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn leave_chat<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.leave_chat(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn get_chat_administrators<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let list = c.get_chat_administrators(peer).await.map_err(py_err)?;
            let result: Vec<ChatMember> = list
                .iter()
                .map(|p| {
                    let (status_s, rank) = participant_status(p);
                    ChatMember {
                        user_id: p.user.id,
                        first_name: p.user.first_name.clone().unwrap_or_default(),
                        last_name: p.user.last_name.clone(),
                        username: p.user.username.clone(),
                        bot: p.user.bot,
                        status: status_s.to_string(),
                        admin_rank: rank,
                    }
                })
                .collect();
            Ok(result)
        })
    }

    fn archive_chat<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.archive_chat(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn unarchive_chat<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.unarchive_chat(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn pin_dialog<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.pin_dialog(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn unpin_dialog<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.unpin_dialog(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    // contacts / blocking

    fn block_user<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.block_user(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn unblock_user<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.unblock_user(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn get_contacts<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let users = c.get_contacts().await.map_err(py_err)?;
            let result: Vec<User> = match users {
                None => vec![],
                Some(list) => list
                    .into_iter()
                    .filter_map(|u| {
                        if let ferogram::tl::enums::User::User(u) = u {
                            Some(tl_user_to_py(&u))
                        } else {
                            None
                        }
                    })
                    .collect(),
            };
            Ok(result)
        })
    }

    // account

    fn get_users_by_id<'py>(&self, py: Python<'py>, ids: Vec<i64>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let users = c.get_users_by_id(&ids).await.map_err(py_err)?;
            let result: Vec<Option<User>> = users
                .into_iter()
                .map(|u| {
                    u.map(|u| User {
                        id: u.id(),
                        first_name: u.first_name().unwrap_or_default().to_owned(),
                        last_name: u.last_name().map(str::to_owned),
                        username: u.username().map(str::to_owned),
                        phone: u.phone().map(str::to_owned),
                        bot: u.bot(),
                    })
                })
                .collect();
            Ok(result)
        })
    }

    fn get_user_full<'py>(&self, py: Python<'py>, user_id: i64) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let f = c.get_user_full(user_id).await.map_err(py_err)?;
            Ok(UserFull {
                id: f.id,
                about: f.about.clone(),
                common_chats_count: f.common_chats_count,
                blocked: f.blocked,
                phone_calls_available: f.phone_calls_available,
                video_calls_available: f.video_calls_available,
            })
        })
    }

    #[pyo3(signature = (first_name=None, last_name=None, about=None))]
    fn update_profile<'py>(
        &self,
        py: Python<'py>,
        first_name: Option<String>,
        last_name: Option<String>,
        about: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.update_profile(first_name, last_name, about)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn update_username<'py>(
        &self,
        py: Python<'py>,
        username: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.update_username(username).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn update_status<'py>(&self, py: Python<'py>, offline: bool) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.update_status(offline).await.map_err(py_err)?;
            Ok(())
        })
    }

    // media

    #[pyo3(signature = (peer, path, caption = String::new()))]
    fn send_photo<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        path: String,
        caption: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let data = tokio::fs::read(&path).await.map_err(py_err)?;
            let name = std::path::Path::new(&path)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("photo.jpg")
                .to_owned();
            let uploaded = c
                .upload_file(&data, &name, "image/jpeg")
                .await
                .map_err(py_err)?;
            let msg = c
                .send_file(
                    peer,
                    uploaded.as_photo_media(),
                    &ferogram::InputMessage::text(caption),
                )
                .await
                .map_err(py_err)?;
            Ok(from_incoming(msg, Some(c)))
        })
    }

    #[pyo3(signature = (peer, path, caption = String::new(), mime_type = None))]
    fn send_document<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        path: String,
        caption: String,
        mime_type: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let data = tokio::fs::read(&path).await.map_err(py_err)?;
            let name = std::path::Path::new(&path)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("file")
                .to_owned();
            let mime = mime_type.as_deref().unwrap_or("application/octet-stream");
            let uploaded = c.upload_file(&data, &name, mime).await.map_err(py_err)?;
            let msg = c
                .send_file(
                    peer,
                    uploaded.as_document_media(),
                    &ferogram::InputMessage::text(caption),
                )
                .await
                .map_err(py_err)?;
            Ok(from_incoming(msg, Some(c)))
        })
    }

    #[pyo3(signature = (peer, path, caption = String::new(), mime_type = None))]
    fn send_file<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        path: String,
        caption: String,
        mime_type: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.send_document(py, peer, path, caption, mime_type)
    }

    // account helpers

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
            Ok(dialogs
                .into_iter()
                .map(|d| Dialog {
                    title: d.title(),
                    unread_count: d.unread_count(),
                    top_message: d.top_message(),
                })
                .collect::<Vec<_>>())
        })
    }

    fn invoke_raw<'py>(&self, py: Python<'py>, tl_bytes: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            crate::raw::invoke_raw_inner(&c, tl_bytes).await
        })
    }

    // search

    fn search_messages<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        query: String,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c
                .search_messages(peer, &query, limit)
                .await
                .map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    fn search_global<'py>(
        &self,
        py: Python<'py>,
        query: String,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c.search_global(&query, limit).await.map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    // chat creation

    fn create_group<'py>(
        &self,
        py: Python<'py>,
        title: String,
        user_ids: Vec<i64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let chat = c.create_group(title, user_ids).await.map_err(py_err)?;
            tl_chat_to_py(&chat).ok_or_else(|| py_err("unexpected chat variant"))
        })
    }

    fn create_channel<'py>(
        &self,
        py: Python<'py>,
        title: String,
        about: String,
        broadcast: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let chat = c
                .create_channel(title, about, broadcast)
                .await
                .map_err(py_err)?;
            tl_chat_to_py(&chat).ok_or_else(|| py_err("unexpected chat variant"))
        })
    }

    fn delete_channel<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(
            py,
            async move { c.delete_channel(peer).await.map_err(py_err) },
        )
    }

    fn delete_chat<'py>(&self, py: Python<'py>, chat_id: i64) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(
            py,
            async move { c.delete_chat(chat_id).await.map_err(py_err) },
        )
    }

    fn edit_chat_title<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        title: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.edit_chat_title(peer, title).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn edit_chat_about<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        about: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.edit_chat_about(peer, about).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn invite_users<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        user_ids: Vec<i64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.invite_users(peer, user_ids).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn set_history_ttl<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        period: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.set_history_ttl(peer, period).await.map_err(py_err)?;
            Ok(())
        })
    }

    // members / join requests

    fn approve_join_request<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        user_id: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.approve_join_request(peer, user_id)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn reject_join_request<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        user_id: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.reject_join_request(peer, user_id).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn approve_all_join_requests<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.approve_all_join_requests(peer, None::<String>)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn reject_all_join_requests<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.reject_all_join_requests(peer, None::<String>)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // contacts

    #[pyo3(signature = (user_id, first_name, last_name = String::new(), phone = String::new()))]
    fn add_contact<'py>(
        &self,
        py: Python<'py>,
        user_id: i64,
        first_name: String,
        last_name: String,
        phone: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.add_contact(user_id, first_name, last_name, phone, false)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn delete_contacts<'py>(
        &self,
        py: Python<'py>,
        user_ids: Vec<i64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_contacts(user_ids).await.map_err(py_err)?;
            Ok(())
        })
    }

    // returns list of peer IDs (i64) of blocked users/chats
    #[pyo3(signature = (limit = 100))]
    fn get_blocked_users<'py>(&self, py: Python<'py>, limit: i32) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let peers = c.get_blocked_users(0, limit).await.map_err(py_err)?;
            let ids: Vec<i64> = peers
                .iter()
                .map(|p| match p {
                    ferogram::tl::enums::Peer::User(u) => u.user_id,
                    ferogram::tl::enums::Peer::Chat(ch) => ch.chat_id,
                    ferogram::tl::enums::Peer::Channel(ch) => ch.channel_id,
                })
                .collect();
            Ok(ids)
        })
    }

    #[pyo3(signature = (user_id, limit = 100))]
    fn get_common_chats<'py>(
        &self,
        py: Python<'py>,
        user_id: i64,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let chats = c
                .get_common_chats(user_id, 0, limit)
                .await
                .map_err(py_err)?;
            Ok(chats.iter().filter_map(tl_chat_to_py).collect::<Vec<_>>())
        })
    }

    // account

    fn get_authorizations<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let auths = c.get_authorizations().await.map_err(py_err)?;
            Ok(auths
                .into_iter()
                .map(|a| Authorization {
                    hash: a.hash,
                    device_model: a.device_model,
                    platform: a.platform,
                    system_version: a.system_version,
                    app_name: a.app_name,
                    app_version: a.app_version,
                    date_created: a.date_created,
                    date_active: a.date_active,
                    ip: a.ip,
                    country: a.country,
                    region: a.region,
                    current: a.current,
                })
                .collect::<Vec<_>>())
        })
    }

    fn terminate_session<'py>(&self, py: Python<'py>, hash: i64) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.terminate_session(hash).await.map_err(py_err)?;
            Ok(())
        })
    }

    // messages

    fn get_scheduled_messages<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c.get_scheduled_messages(peer).await.map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    fn get_pinned_message<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msg = c.get_pinned_message(peer).await.map_err(py_err)?;
            Ok(msg.map(|m| from_incoming(m, Some(Arc::clone(&c)))))
        })
    }

    fn translate_messages<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_ids: Vec<i32>,
        to_lang: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let results = c
                .translate_messages(peer, msg_ids, to_lang)
                .await
                .map_err(py_err)?;
            Ok(results.into_iter().map(|t| t.text).collect::<Vec<_>>())
        })
    }

    #[pyo3(signature = (peer, max_id = 0, revoke = false))]
    fn delete_chat_history<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        max_id: i32,
        revoke: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_chat_history(peer, max_id, revoke)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // drafts

    fn save_draft<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        text: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.save_draft(peer, text).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn clear_all_drafts<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.clear_all_drafts().await.map_err(py_err)?;
            Ok(())
        })
    }

    // polls

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (peer, question, answers, quiz = false, correct_index = None, multiple_choice = false))]
    fn send_poll<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        question: String,
        answers: Vec<String>,
        quiz: bool,
        correct_index: Option<usize>,
        multiple_choice: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let refs: Vec<&str> = answers.iter().map(String::as_str).collect();
            c.send_poll(peer, question, &refs, quiz, correct_index, multiple_choice)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // options: list of 1-byte option indices (e.g. [b'\x00'] for first option)
    fn send_vote<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        options: Vec<Vec<u8>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.send_vote(peer, msg_id, options).await.map_err(py_err)?;
            Ok(())
        })
    }

    // reactions

    fn read_reactions<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.read_reactions(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn clear_recent_reactions<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.clear_recent_reactions().await.map_err(py_err)?;
            Ok(())
        })
    }

    // bot commands

    fn set_bot_commands<'py>(
        &self,
        py: Python<'py>,
        commands: Vec<(String, String)>,
        lang_code: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let refs: Vec<(&str, &str)> = commands
                .iter()
                .map(|(a, b)| (a.as_str(), b.as_str()))
                .collect();
            c.set_bot_commands(&refs, None, &lang_code)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn delete_bot_commands<'py>(
        &self,
        py: Python<'py>,
        lang_code: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_bot_commands(None, &lang_code)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    #[pyo3(signature = (name = None, about = None, description = None, lang_code = String::new()))]
    fn set_bot_info<'py>(
        &self,
        py: Python<'py>,
        name: Option<String>,
        about: Option<String>,
        description: Option<String>,
        lang_code: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.set_bot_info(
                name.as_deref(),
                about.as_deref(),
                description.as_deref(),
                &lang_code,
            )
            .await
            .map_err(py_err)?;
            Ok(())
        })
    }

    fn get_bot_info<'py>(&self, py: Python<'py>, lang_code: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let info = c.get_bot_info(&lang_code).await.map_err(py_err)?;
            Ok(BotInfo {
                name: info.name,
                about: info.about,
                description: info.description,
            })
        })
    }

    // forum

    #[pyo3(signature = (peer, limit = 100))]
    fn get_forum_topics<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let topics = c
                .get_forum_topics(peer, None, limit, 0, 0, 0)
                .await
                .map_err(py_err)?;
            Ok(topics
                .iter()
                .filter_map(tl_forum_topic_to_py)
                .collect::<Vec<_>>())
        })
    }

    #[pyo3(signature = (peer, title, icon_color = None, icon_emoji_id = None))]
    fn create_forum_topic<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        title: String,
        icon_color: Option<i32>,
        icon_emoji_id: Option<i64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.create_forum_topic(peer, title, icon_color, icon_emoji_id)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    #[pyo3(signature = (peer, topic_id, title = None, closed = None, hidden = None))]
    fn edit_forum_topic<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        topic_id: i32,
        title: Option<String>,
        closed: Option<bool>,
        hidden: Option<bool>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.edit_forum_topic(peer, topic_id, title, None, closed, hidden)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn delete_forum_topic_history<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        top_msg_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_forum_topic_history(peer, top_msg_id)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn toggle_forum<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        enabled: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.toggle_forum(peer, enabled).await.map_err(py_err)?;
            Ok(())
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
