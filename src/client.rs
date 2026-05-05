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
use ferogram::PeerExt;
use ferogram::tl;

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
        S::Admin => ("admin", None),
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
            allow_zero_hash: false,
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
            let m = c.send_message(peer, text).await.map_err(py_err)?;
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
                c.send_message(peer, ferogram::InputMessage::html(html))
                    .await
                    .map_err(py_err)?,
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
                c.send_message(peer, ferogram::InputMessage::markdown(md))
                    .await
                    .map_err(py_err)?,
                Some(c),
            ))
        })
    }

    fn send_to_self<'py>(&self, py: Python<'py>, text: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let m = c.send_to_self(text).await.map_err(py_err)?;
            Ok(from_incoming(m, Some(c)))
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
            c.edit_message(peer, message_id, new_text)
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
            c.delete_messages(&message_ids, revoke)
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
            c.forward_messages(
                destination,
                &message_ids,
                source,
                ferogram::ForwardOptions::default(),
            )
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
            c.pin_message(peer, message_id, false)
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
            let result: Vec<User> = users
                .into_iter()
                .filter_map(|u| {
                    if let ferogram::tl::enums::User::User(u) = u {
                        Some(tl_user_to_py(&u))
                    } else {
                        None
                    }
                })
                .collect();
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
                .map(|u| u.map(|u| ferogram_user_to_py(&u)))
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
            c.set_profile(first_name, last_name, about)
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
            c.set_username(username).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn update_status<'py>(&self, py: Python<'py>, offline: bool) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            if offline {
                c.set_offline().await.map_err(py_err)?;
            } else {
                c.set_online().await.map_err(py_err)?;
            }
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
                .search(peer, &query)
                .limit(limit)
                .fetch(&c)
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
            let msgs = c
                .search_global(&query)
                .limit(limit)
                .fetch(&c)
                .await
                .map_err(py_err)?;
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
            c.invite_users(peer, &user_ids).await.map_err(py_err)?;
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
            c.join_request(peer, user_id, true).await.map_err(py_err)?;
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
            c.join_request(peer, user_id, false).await.map_err(py_err)?;
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
            c.all_join_requests(peer, true, None::<String>)
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
            c.all_join_requests(peer, false, None::<String>)
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
            c.delete_contacts(&user_ids).await.map_err(py_err)?;
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
                    tl::enums::Peer::User(u) => u.user_id,
                    tl::enums::Peer::Chat(ch) => ch.chat_id,
                    tl::enums::Peer::Channel(ch) => ch.channel_id,
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

    // forwarding with return

    fn forward_messages_returning<'py>(
        &self,
        py: Python<'py>,
        destination: String,
        source: String,
        message_ids: Vec<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c
                .forward_messages(
                    destination,
                    &message_ids,
                    source,
                    ferogram::ForwardOptions::default(),
                )
                .await
                .map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    // scheduled messages

    fn delete_scheduled_messages<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        ids: Vec<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_scheduled_messages(peer, &ids)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn send_scheduled_now<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        ids: Vec<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.send_scheduled_now(peer, &ids).await.map_err(py_err)?;
            Ok(())
        })
    }

    // invite links

    fn accept_invite_link<'py>(
        &self,
        py: Python<'py>,
        link: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.accept_invite_link(&link).await.map_err(py_err)?;
            Ok(())
        })
    }

    #[pyo3(signature = (peer, expire_date=None, usage_limit=None, request_needed=false, title=None))]
    fn export_invite_link<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        expire_date: Option<i32>,
        usage_limit: Option<i32>,
        request_needed: bool,
        title: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let invite = c
                .export_invite_link(peer, expire_date, usage_limit, request_needed, title)
                .await
                .map_err(py_err)?;
            let link = match invite {
                tl::enums::ExportedChatInvite::ChatInviteExported(i) => i.link,
                tl::enums::ExportedChatInvite::ChatInvitePublicJoinRequests => String::new(),
            };
            Ok(link)
        })
    }

    fn revoke_invite_link<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        link: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let invite = c.revoke_invite_link(peer, link).await.map_err(py_err)?;
            let new_link = match invite {
                tl::enums::ExportedChatInvite::ChatInviteExported(i) => i.link,
                tl::enums::ExportedChatInvite::ChatInvitePublicJoinRequests => String::new(),
            };
            Ok(new_link)
        })
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (peer, link, expire_date=None, usage_limit=None, request_needed=None, title=None))]
    fn edit_invite_link<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        link: String,
        expire_date: Option<i32>,
        usage_limit: Option<i32>,
        request_needed: Option<bool>,
        title: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let invite = c
                .edit_invite_link(peer, link, expire_date, usage_limit, request_needed, title)
                .await
                .map_err(py_err)?;
            let updated = match invite {
                tl::enums::ExportedChatInvite::ChatInviteExported(i) => i.link,
                tl::enums::ExportedChatInvite::ChatInvitePublicJoinRequests => String::new(),
            };
            Ok(updated)
        })
    }

    #[pyo3(signature = (peer, admin_id, revoked=false, limit=100))]
    fn get_invite_links<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        admin_id: i64,
        revoked: bool,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let invites = c
                .get_invite_links(peer, admin_id, revoked, limit, None, None)
                .await
                .map_err(py_err)?;
            let links: Vec<String> = invites
                .into_iter()
                .filter_map(|i| match i {
                    tl::enums::ExportedChatInvite::ChatInviteExported(e) => Some(e.link),
                    _ => None,
                })
                .collect();
            Ok(links)
        })
    }

    fn delete_invite_link<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        link: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_invite_link(peer, link).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn delete_revoked_invite_links<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        admin_id: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_revoked_invite_links(peer, admin_id)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    #[pyo3(signature = (peer, link=None, requested=false, limit=100))]
    fn get_invite_link_members<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        link: Option<String>,
        requested: bool,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let members = c
                .get_invite_link_members(peer, link, requested, limit, 0, 0)
                .await
                .map_err(py_err)?;
            Ok(members
                .into_iter()
                .map(|m| InviteLinkMember {
                    user_id: m.user_id,
                    date: m.date,
                    requested: m.requested,
                    about: m.about,
                })
                .collect::<Vec<_>>())
        })
    }

    // contacts

    fn import_contacts<'py>(
        &self,
        py: Python<'py>,
        contacts: Vec<(String, String, String)>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let refs: Vec<(&str, &str, &str)> = contacts
                .iter()
                .map(|(p, f, l)| (p.as_str(), f.as_str(), l.as_str()))
                .collect();
            let result = c.import_contacts(&refs).await.map_err(py_err)?;
            Ok(result.imported.len() as i32)
        })
    }

    fn search_contacts<'py>(
        &self,
        py: Python<'py>,
        query: String,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let peers = c.search_contacts(query, limit).await.map_err(py_err)?;
            let ids: Vec<i64> = peers
                .iter()
                .map(|p| match p {
                    tl::enums::Peer::User(u) => u.user_id,
                    tl::enums::Peer::Chat(ch) => ch.chat_id,
                    tl::enums::Peer::Channel(ch) => ch.channel_id,
                })
                .collect();
            Ok(ids)
        })
    }

    fn set_profile_photo<'py>(&self, py: Python<'py>, path: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let data = tokio::fs::read(&path).await.map_err(py_err)?;
            let name = std::path::Path::new(&path)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("avatar.jpg")
                .to_owned();
            let uploaded = c
                .upload_file(&data, &name, "image/jpeg")
                .await
                .map_err(py_err)?;
            c.set_profile_photo(uploaded).await.map_err(py_err)?;
            Ok(())
        })
    }

    // message threads

    fn get_message_read_participants<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let list = c
                .get_message_read_participants(peer, msg_id)
                .await
                .map_err(py_err)?;
            Ok(list
                .into_iter()
                .map(|r| ReadParticipant {
                    user_id: r.user_id,
                    date: r.date,
                })
                .collect::<Vec<_>>())
        })
    }

    #[pyo3(signature = (peer, msg_id, limit=100, offset_id=0))]
    fn get_replies<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        limit: i32,
        offset_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c
                .get_replies(peer, msg_id, limit, offset_id)
                .await
                .map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    fn read_discussion<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        read_max_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.read_discussion(peer, msg_id, read_max_id)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn get_media_group<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c.get_media_group(peer, msg_id).await.map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    // reactions / reactions extras

    fn get_message_reactions<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_ids: Vec<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.get_reactions(peer, msg_ids).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn send_paid_reaction<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        count: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.send_paid_reaction(peer, msg_id, count)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // speech / translation

    fn transcribe_audio<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let result = c.transcribe_audio(peer, msg_id).await.map_err(py_err)?;
            Ok(result.text)
        })
    }

    fn toggle_peer_translations<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        disabled: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.toggle_peer_translations(peer, disabled)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // admin log

    #[pyo3(signature = (peer, query = String::new(), limit = 100, max_id = 0, min_id = 0))]
    fn get_admin_log<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        query: String,
        limit: i32,
        max_id: i64,
        min_id: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let events = c
                .get_admin_log(peer, query, limit, max_id, min_id)
                .await
                .map_err(py_err)?;
            Ok(events
                .into_iter()
                .map(|e| {
                    let action = format!("{:?}", e.action)
                        .split('(')
                        .next()
                        .unwrap_or("Unknown")
                        .to_string();
                    AdminLogEvent {
                        id: e.id,
                        date: e.date,
                        user_id: e.user_id,
                        action,
                    }
                })
                .collect::<Vec<_>>())
        })
    }

    // chat settings

    fn toggle_no_forwards<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        enabled: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.toggle_no_forwards(peer, enabled).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn set_chat_theme<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        emoticon: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.set_chat_theme(peer, emoticon).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn export_message_link<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        grouped: bool,
        thread: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let kind = if grouped {
                ferogram::LinkKind::Grouped
            } else if thread {
                ferogram::LinkKind::Thread
            } else {
                ferogram::LinkKind::Normal
            };
            let link = c
                .export_message_link(peer, msg_id, kind)
                .await
                .map_err(py_err)?;
            Ok(link)
        })
    }

    // send-as

    fn get_send_as_peers<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let peers = c.get_send_as_peers(peer).await.map_err(py_err)?;
            let ids: Vec<i64> = peers
                .iter()
                .map(|p| match p {
                    tl::enums::Peer::User(u) => u.user_id,
                    tl::enums::Peer::Chat(ch) => ch.chat_id,
                    tl::enums::Peer::Channel(ch) => ch.channel_id,
                })
                .collect();
            Ok(ids)
        })
    }

    fn set_default_send_as<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        send_as_peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.set_default_send_as(peer, send_as_peer)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // dialogs extras

    fn mark_dialog_unread<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        unread: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            if unread {
                c.mark_dialog_unread(peer).await.map_err(py_err)?;
            } else {
                c.mark_dialog_read(peer).await.map_err(py_err)?;
            }
            Ok(())
        })
    }

    fn get_poll_results<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        poll_hash: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.get_poll_results(peer, msg_id, poll_hash)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn get_forum_topics_by_id<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        topic_ids: Vec<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let topics = c
                .get_forum_topics_by_id(peer, topic_ids)
                .await
                .map_err(py_err)?;
            Ok(topics
                .iter()
                .filter_map(tl_forum_topic_to_py)
                .collect::<Vec<_>>())
        })
    }

    // bot extras

    #[pyo3(signature = (bot_user_id, peer, start_param = String::new()))]
    fn start_bot<'py>(
        &self,
        py: Python<'py>,
        bot_user_id: i64,
        peer: String,
        start_param: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.start_bot(bot_user_id, peer, start_param)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    #[pyo3(signature = (peer, msg_id, user_id, score, force = false, edit_message = true))]
    #[allow(clippy::too_many_arguments)]
    fn set_game_score<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        user_id: i64,
        score: i32,
        force: bool,
        edit_message: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.set_game_score(peer, msg_id, user_id, score, force, edit_message)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn answer_precheckout_query<'py>(
        &self,
        py: Python<'py>,
        query_id: i64,
        ok: bool,
        error_message: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.answer_precheckout_query(query_id, ok, error_message)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn answer_shipping_query<'py>(
        &self,
        py: Python<'py>,
        query_id: i64,
        error: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.answer_shipping_query(query_id, error, None)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // stickers (short-name based helpers)

    fn get_sticker_set<'py>(
        &self,
        py: Python<'py>,
        short_name: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let ss_input =
                tl::enums::InputStickerSet::ShortName(tl::types::InputStickerSetShortName {
                    short_name,
                });
            let result = c.get_sticker_set(ss_input).await.map_err(py_err)?;
            let tl::enums::StickerSet::StickerSet(s) = result.set;
            Ok(StickerSetInfo {
                id: s.id,
                title: s.title,
                short_name: s.short_name,
                count: s.count,
                animated: false,
                videos: false,
                emojis: s.emojis,
            })
        })
    }

    fn install_sticker_set<'py>(
        &self,
        py: Python<'py>,
        short_name: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let ss_input =
                tl::enums::InputStickerSet::ShortName(tl::types::InputStickerSetShortName {
                    short_name,
                });
            c.install_sticker_set(ss_input, false)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn uninstall_sticker_set<'py>(
        &self,
        py: Python<'py>,
        short_name: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let ss_input =
                tl::enums::InputStickerSet::ShortName(tl::types::InputStickerSetShortName {
                    short_name,
                });
            c.uninstall_sticker_set(ss_input).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn get_all_stickers<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            match c.get_all_stickers(0).await.map_err(py_err)? {
                None => Ok(vec![]),
                Some(sets) => Ok(sets
                    .into_iter()
                    .map(|s| StickerSetInfo {
                        id: s.id,
                        title: s.title,
                        short_name: s.short_name,
                        count: s.count,
                        animated: false,
                        videos: false,
                        emojis: s.emojis,
                    })
                    .collect::<Vec<_>>()),
            }
        })
    }

    // account extras

    fn set_emoji_status<'py>(
        &self,
        py: Python<'py>,
        document_id: Option<i64>,
        until: Option<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.set_emoji_status(document_id, until)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn get_linked_channel<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let id = c.get_linked_channel(peer).await.map_err(py_err)?;
            Ok(id)
        })
    }

    fn get_chat_full_raw<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let full = c.get_chat_full(peer).await.map_err(py_err)?;
            let tl::enums::messages::ChatFull::ChatFull(f) = full;
            let (id, about, members_count) = match f.full_chat {
                tl::enums::ChatFull::ChatFull(ch) => (ch.id, ch.about, Some(0i32)),
                tl::enums::ChatFull::ChannelFull(ch) => (ch.id, ch.about, ch.participants_count),
            };
            Ok((id, about, members_count))
        })
    }

    fn migrate_chat<'py>(&self, py: Python<'py>, chat_id: i64) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let chat = c.migrate_chat(chat_id).await.map_err(py_err)?;
            tl_chat_to_py(&chat).ok_or_else(|| py_err("unexpected chat variant"))
        })
    }

    // answer query methods

    fn answer_callback_query<'py>(
        &self,
        py: Python<'py>,
        query_id: i64,
        text: Option<String>,
        alert: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.answer_callback_query(query_id, text.as_deref(), alert)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // answer_inline_query: results as JSON strings (each a serialized InputBotInlineResult)
    // For the Python layer we expose a simplified article-only helper
    fn answer_inline_query_articles<'py>(
        &self,
        py: Python<'py>,
        query_id: i64,
        articles: Vec<(String, String, String)>,
        cache_time: i32,
        is_personal: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            // articles: Vec<(id, title, message_text)>
            let results = articles
                .into_iter()
                .map(|(id, title, msg)| {
                    tl::enums::InputBotInlineResult::InputBotInlineResult(
                        tl::types::InputBotInlineResult {
                            id,
                            r#type: "article".into(),
                            title: Some(title),
                            description: None,
                            url: None,
                            thumb: None,
                            content: None,
                            send_message: tl::enums::InputBotInlineMessage::Text(
                                tl::types::InputBotInlineMessageText {
                                    no_webpage: false,
                                    invert_media: false,
                                    message: msg,
                                    entities: None,
                                    reply_markup: None,
                                },
                            ),
                        },
                    )
                })
                .collect();
            c.answer_inline_query(query_id, results, cache_time, is_personal, None)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // profile

    fn delete_profile_photos<'py>(
        &self,
        py: Python<'py>,
        photo_ids: Vec<(i64, i64, Vec<u8>)>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.delete_profile_photos(photo_ids).await.map_err(py_err)?;
            Ok(())
        })
    }

    fn edit_chat_photo<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        path: String,
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
            let input_file = match uploaded.as_photo_media() {
                tl::enums::InputMedia::UploadedPhoto(p) => p.file,
                _ => unreachable!(),
            };
            let photo = tl::enums::InputChatPhoto::InputChatUploadedPhoto(
                tl::types::InputChatUploadedPhoto {
                    video: None,
                    file: Some(input_file),
                    video_start_ts: None,
                    video_emoji_markup: None,
                },
            );
            c.edit_chat_photo(peer, photo).await.map_err(py_err)?;
            Ok(())
        })
    }

    // default banned rights: pass a dict of restriction keys -> bool
    // keys: send_messages, send_media, send_stickers, send_gifs, send_games,
    //       send_inline, embed_links, send_polls, change_info, invite_users, pin_messages
    fn edit_chat_default_banned_rights<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        restrictions: std::collections::HashMap<String, bool>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.edit_chat_default_banned_rights(peer, |b| {
                let mut b = b;
                for (k, v) in &restrictions {
                    b = match k.as_str() {
                        "send_messages" => b.send_messages(!v),
                        "send_media" => b.send_media(!v),
                        "send_stickers" => b.send_stickers(!v),
                        "send_gifs" => b.send_gifs(!v),
                        "send_games" => b.send_games(!v),
                        "send_inline" => b.send_inline(!v),
                        "embed_links" => b.embed_links(!v),
                        "send_polls" => b.send_polls(!v),
                        "change_info" => b.change_info(!v),
                        "invite_users" => b.invite_users(!v),
                        "pin_messages" => b.pin_messages(!v),
                        _ => b,
                    };
                }
                b
            })
            .await
            .map_err(py_err)?;
            Ok(())
        })
    }

    // message extras

    fn get_reply_to_message<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c
                .get_messages_by_id(peer, &[msg_id])
                .await
                .map_err(py_err)?;
            let parent = msgs.into_iter().next();
            // now fetch its reply_to
            if let Some(m) = parent {
                let result = m.get_reply_with(&c).await.map_err(py_err)?;
                Ok(result.map(|r| from_incoming(r, Some(Arc::clone(&c)))))
            } else {
                Ok(None)
            }
        })
    }

    fn get_discussion_message<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let disc = c
                .get_discussion_message(peer.clone(), msg_id)
                .await
                .map_err(py_err)?;
            let msg_ids: Vec<i32> = disc
                .messages
                .iter()
                .filter_map(|m| match m {
                    ferogram::tl::enums::Message::Message(msg) => Some(msg.id),
                    ferogram::tl::enums::Message::Service(svc) => Some(svc.id),
                    _ => None,
                })
                .collect();
            let unread_count = disc.unread_count;
            let max_id = disc.max_id;
            let read_inbox_max_id = disc.read_inbox_max_id;
            let fetched = c.get_messages_by_id(peer, &msg_ids).await.map_err(py_err)?;
            let msgs = fetched
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>();
            Ok((msgs, unread_count, max_id, read_inbox_max_id))
        })
    }

    fn get_web_page_preview<'py>(
        &self,
        py: Python<'py>,
        text: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let media = c.get_web_page_preview(text).await.map_err(py_err)?;
            // Return the URL if it's a webpage
            let url = match &media {
                tl::enums::MessageMedia::WebPage(wp) => match &wp.webpage {
                    tl::enums::WebPage::WebPage(w) => Some(w.url.clone()),
                    _ => None,
                },
                _ => None,
            };
            Ok(url)
        })
    }

    fn get_admins_with_invites<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let result = c.get_admins_with_invites(peer).await.map_err(py_err)?;
            let pairs: Vec<(i64, i32)> = result
                .admins
                .into_iter()
                .map(|a| match a {
                    tl::enums::ChatAdminWithInvites::ChatAdminWithInvites(x) => {
                        (x.admin_id, x.invites_count)
                    }
                })
                .collect();
            Ok(pairs)
        })
    }

    fn get_all_drafts<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.clear_all_drafts().await.map_err(py_err)?;
            Ok(())
        })
    }

    // reaction list: returns Vec<(user_id, reaction_emoji_or_document_id)>
    #[allow(unused_variables)]
    #[pyo3(signature = (peer, msg_id, limit = 100))]
    fn get_reaction_list<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            // get_reactions triggers a server-side update; data comes via update stream
            c.get_reactions(peer, vec![msg_id]).await.map_err(py_err)?;
            let pairs: Vec<(i64, String)> = vec![];
            Ok(pairs)
        })
    }

    // notify settings: simplified mute/unmute helper
    fn mute_chat<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        mute_until: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let settings = tl::enums::InputPeerNotifySettings::InputPeerNotifySettings(
                tl::types::InputPeerNotifySettings {
                    show_previews: None,
                    silent: None,
                    mute_until: Some(mute_until),
                    sound: None,
                    stories_muted: false,
                    stories_hide_sender: false,
                    stories_sound: None,
                },
            );
            c.update_notify_settings(peer, settings)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    fn get_pinned_dialogs<'py>(
        &self,
        py: Python<'py>,
        folder_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let dialogs = c.get_pinned_dialogs(folder_id).await.map_err(py_err)?;
            // Return peer IDs
            let ids: Vec<i64> = dialogs
                .iter()
                .filter_map(|d| {
                    let peer = match d {
                        tl::enums::Dialog::Dialog(d) => Some(&d.peer),
                        _ => None,
                    }?;
                    Some(match peer {
                        tl::enums::Peer::User(u) => u.user_id,
                        tl::enums::Peer::Chat(c) => c.chat_id,
                        tl::enums::Peer::Channel(c) => c.channel_id,
                    })
                })
                .collect();
            Ok(ids)
        })
    }

    #[pyo3(signature = (peer, msg_id, limit = 100))]
    fn get_poll_votes<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        limit: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let result = c
                .get_poll_votes(peer, msg_id, None, limit, None)
                .await
                .map_err(py_err)?;
            let pairs: Vec<(i64, Vec<u8>)> = result
                .votes
                .into_iter()
                .map(|v| match v {
                    tl::enums::MessagePeerVote::MessagePeerVote(x) => (x.peer.bare_id(), x.option),
                    tl::enums::MessagePeerVote::InputOption(x) => (x.peer.bare_id(), vec![]),
                    tl::enums::MessagePeerVote::Multiple(x) => {
                        (x.peer.bare_id(), x.options.into_iter().flatten().collect())
                    }
                })
                .collect();
            Ok(pairs)
        })
    }

    fn get_custom_emoji_documents<'py>(
        &self,
        py: Python<'py>,
        document_ids: Vec<i64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let docs = c
                .get_custom_emoji_documents(document_ids)
                .await
                .map_err(py_err)?;
            let ids: Vec<i64> = docs
                .iter()
                .filter_map(|d| match d {
                    tl::enums::Document::Document(doc) => Some(doc.id),
                    _ => None,
                })
                .collect();
            Ok(ids)
        })
    }

    fn get_game_high_scores<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        user_id: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let scores = c
                .get_game_high_scores(peer, msg_id, user_id)
                .await
                .map_err(py_err)?;
            let result: Vec<(i32, i64, i32)> = scores
                .into_iter()
                .map(|s| (s.pos, s.user_id, s.score))
                .collect();
            Ok(result)
        })
    }

    // send_invoice helper
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (peer, title, description, payload, currency, prices, photo_url=None, need_name=false, need_phone=false, need_email=false, need_shipping_address=false, is_flexible=false))]
    fn send_invoice<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        title: String,
        description: String,
        payload: String,
        currency: String,
        prices: Vec<(String, i64)>,
        photo_url: Option<String>,
        need_name: bool,
        need_phone: bool,
        need_email: bool,
        need_shipping_address: bool,
        is_flexible: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msg = c
                .send_invoice(
                    peer,
                    title,
                    description,
                    payload,
                    ferogram::InvoiceOptions {
                        currency,
                        prices,
                        photo_url,
                        need_name,
                        need_phone,
                        need_email,
                        need_shipping_address,
                        is_flexible,
                    },
                )
                .await
                .map_err(py_err)?;
            Ok(from_incoming(msg, Some(Arc::clone(&c))))
        })
    }

    // resolve helpers

    fn resolve_peer<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let p = c.resolve_peer(&peer).await.map_err(py_err)?;
            let id = match p {
                tl::enums::Peer::User(u) => u.user_id,
                tl::enums::Peer::Chat(ch) => ch.chat_id,
                tl::enums::Peer::Channel(ch) => ch.channel_id,
            };
            Ok(id)
        })
    }

    /// Resolve an integer peer ID to a typed InputPeer dict using the Rust cache.
    ///
    /// Returns a dict: {"_": "inputPeerUser"|"inputPeerChannel"|"inputPeerChat",
    ///                  "user_id"|"channel_id"|"chat_id": i64,
    ///                  "access_hash": i64}   (access_hash absent for chat)
    ///
    /// Returns None if the access_hash is not yet cached (caller must fall back
    /// to a live API call and then retry after populate_cache).
    fn get_input_peer<'py>(&self, py: Python<'py>, peer_id: i64) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            Python::with_gil(|py| {
                let cache = pyo3::PyErr::take(py); // just to get py handle
                drop(cache);
                Ok::<_, pyo3::PyErr>(())
            })?;
            // Build a Peer enum from the raw id using the same sign convention
            // as Telegram: positive = user, -100xxxx = channel, small neg = chat
            let peer = if peer_id > 0 {
                tl::enums::Peer::User(tl::types::PeerUser { user_id: peer_id })
            } else {
                let abs = peer_id.unsigned_abs() as i64;
                if abs > 1_000_000_000 {
                    tl::enums::Peer::Channel(tl::types::PeerChannel {
                        channel_id: abs - 1_000_000_000,
                    })
                } else {
                    tl::enums::Peer::Chat(tl::types::PeerChat { chat_id: -peer_id })
                }
            };

            match c.resolve_to_input_peer(&peer).await {
                Ok(tl::enums::InputPeer::User(u)) => Python::with_gil(|py| {
                    let d = pyo3::types::PyDict::new(py);
                    d.set_item("_", "inputPeerUser")?;
                    d.set_item("user_id", u.user_id)?;
                    d.set_item("access_hash", u.access_hash)?;
                    Ok(Some(d.unbind()))
                }),
                Ok(tl::enums::InputPeer::Channel(ch)) => Python::with_gil(|py| {
                    let d = pyo3::types::PyDict::new(py);
                    d.set_item("_", "inputPeerChannel")?;
                    d.set_item("channel_id", ch.channel_id)?;
                    d.set_item("access_hash", ch.access_hash)?;
                    Ok(Some(d.unbind()))
                }),
                Ok(tl::enums::InputPeer::Chat(ch)) => Python::with_gil(|py| {
                    let d = pyo3::types::PyDict::new(py);
                    d.set_item("_", "inputPeerChat")?;
                    d.set_item("chat_id", ch.chat_id)?;
                    Ok(Some(d.unbind()))
                }),
                Ok(tl::enums::InputPeer::PeerSelf) => Python::with_gil(|py| {
                    let d = pyo3::types::PyDict::new(py);
                    d.set_item("_", "inputPeerSelf")?;
                    Ok(Some(d.unbind()))
                }),
                // Cache miss - return None so Python can fall back to live lookup
                Err(_) => Ok(None),
                _ => Ok(None),
            }
        })
    }

    /// Explicitly warm the Rust peer cache by calling GetDialogs.
    /// Call this once after connect() if you need to resolve integer peer IDs
    /// before any message has arrived (e.g. on a fresh session).
    /// Do NOT call at startup routinely - it does a full GetDialogs round-trip.
    fn warm_peer_cache_from_dialogs<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.warm_peer_cache_from_dialogs().await.map_err(py_err)?;
            Ok(())
        })
    }

    fn resolve_username<'py>(
        &self,
        py: Python<'py>,
        username: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let username = username.trim_start_matches('@').to_owned();
            let p = c
                .resolve_peer(&format!("@{username}"))
                .await
                .map_err(py_err)?;
            let id = match p {
                tl::enums::Peer::User(u) => u.user_id,
                tl::enums::Peer::Chat(ch) => ch.chat_id,
                tl::enums::Peer::Channel(ch) => ch.channel_id,
            };
            Ok(id)
        })
    }

    // get_messages (history)

    #[pyo3(signature = (peer, limit = 100, offset_id = 0))]
    fn get_history<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        limit: i32,
        offset_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c
                .get_message_history(peer, limit, offset_id)
                .await
                .map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    // upload media (file path → reusable media reference ID)

    fn upload_media<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        path: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let data = tokio::fs::read(&path).await.map_err(py_err)?;
            let name = std::path::Path::new(&path)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("file")
                .to_owned();
            let mime = if name.ends_with(".jpg") || name.ends_with(".jpeg") {
                "image/jpeg"
            } else if name.ends_with(".png") {
                "image/png"
            } else if name.ends_with(".mp4") {
                "video/mp4"
            } else if name.ends_with(".mp3") {
                "audio/mpeg"
            } else {
                "application/octet-stream"
            };
            let uploaded = c.upload_file(&data, &name, mime).await.map_err(py_err)?;
            let media_input = uploaded.as_document_media();
            let result = c
                .upload_media(peer.clone(), media_input)
                .await
                .map_err(py_err)?;
            let doc_id = match result {
                tl::enums::MessageMedia::Document(d) => match d.document {
                    Some(tl::enums::Document::Document(doc)) => Some(doc.id),
                    _ => None,
                },
                _ => None,
            };
            Ok(doc_id)
        })
    }

    // download media

    fn download_media<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        msg_id: i32,
        path: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c
                .get_messages_by_id(peer, &[msg_id])
                .await
                .map_err(py_err)?;
            let msg = msgs
                .into_iter()
                .next()
                .ok_or_else(|| py_err("message not found"))?;
            let found = msg.download_media(&path).await.map_err(py_err)?;
            if !found {
                return Err(py_err("no downloadable media in message"));
            }
            Ok(path)
        })
    }

    // edit inline message (id as bytes = serialized InputBotInlineMessageId)

    fn edit_inline_message<'py>(
        &self,
        py: Python<'py>,
        dc_id: i32,
        id_bytes: Vec<u8>,
        new_text: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            use ferogram::tl::{Cursor, Deserializable};
            let mut cur = Cursor::from_slice(&id_bytes);
            let id = tl::enums::InputBotInlineMessageId::deserialize(&mut cur).map_err(py_err)?;
            let _ = dc_id;
            let ok = c
                .edit_inline_message(id, &new_text, None)
                .await
                .map_err(py_err)?;
            Ok(ok)
        })
    }

    // full answer_inline_query: results as list of (type, id, title, message_text, [thumb_url])
    // type: "article" | "photo" | "document"

    fn answer_inline_query<'py>(
        &self,
        py: Python<'py>,
        query_id: i64,
        results: Vec<(String, String, String, String, Option<String>)>,
        cache_time: i32,
        is_personal: bool,
        next_offset: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let tl_results = results
                .into_iter()
                .map(|(type_, id, title, msg, _thumb)| {
                    tl::enums::InputBotInlineResult::InputBotInlineResult(
                        tl::types::InputBotInlineResult {
                            id,
                            r#type: type_,
                            title: Some(title),
                            description: None,
                            url: None,
                            thumb: None,
                            content: None,
                            send_message: tl::enums::InputBotInlineMessage::Text(
                                tl::types::InputBotInlineMessageText {
                                    no_webpage: false,
                                    invert_media: false,
                                    message: msg,
                                    entities: None,
                                    reply_markup: None,
                                },
                            ),
                        },
                    )
                })
                .collect();
            c.answer_inline_query(query_id, tl_results, cache_time, is_personal, next_offset)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // QR login

    fn export_login_token<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let (token, expires) = c.export_login_token().await.map_err(py_err)?;
            Ok((token, expires))
        })
    }

    fn check_qr_login<'py>(&self, py: Python<'py>, token: Vec<u8>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let username = c.check_qr_login(token).await.map_err(py_err)?;
            Ok(username)
        })
    }

    // privacy

    fn get_privacy<'py>(&self, py: Python<'py>, key: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let k = parse_privacy_key(&key).map_err(py_err)?;
            let rules = c.get_privacy(k).await.map_err(py_err)?;
            let strs: Vec<String> = rules
                .iter()
                .map(|r| {
                    format!("{:?}", r)
                        .split('(')
                        .next()
                        .unwrap_or("Unknown")
                        .to_owned()
                })
                .collect();
            Ok(strs)
        })
    }

    // set_privacy: rule_type one of "allow_all","allow_contacts","allow_users","disallow_all","disallow_users"
    fn set_privacy<'py>(
        &self,
        py: Python<'py>,
        key: String,
        rule: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let k = parse_privacy_key(&key).map_err(py_err)?;
            let r = parse_privacy_rule(&rule).map_err(py_err)?;
            c.set_privacy(k, vec![r]).await.map_err(py_err)?;
            Ok(())
        })
    }

    // notify settings

    fn get_notify_settings<'py>(
        &self,
        py: Python<'py>,
        peer: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let result = c.get_notify_settings(peer).await.map_err(py_err)?;
            let tl::enums::PeerNotifySettings::PeerNotifySettings(s) = result;
            Ok(NotifySettings {
                mute_until: s.mute_until,
                silent: s.silent,
                show_previews: s.show_previews,
            })
        })
    }

    fn update_notify_settings<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        mute_until: Option<i32>,
        silent: Option<bool>,
        show_previews: Option<bool>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let settings = tl::enums::InputPeerNotifySettings::InputPeerNotifySettings(
                tl::types::InputPeerNotifySettings {
                    show_previews,
                    silent,
                    mute_until,
                    sound: None,
                    stories_muted: false,
                    stories_hide_sender: false,
                    stories_sound: None,
                },
            );
            c.update_notify_settings(peer, settings)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // set_chat_reactions: "all" | "none" | comma-separated emoji e.g. "👍,👎,❤"

    fn set_chat_reactions<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        reactions: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let available = match reactions.as_str() {
                "all" => tl::enums::ChatReactions::All(tl::types::ChatReactionsAll {
                    allow_custom: true,
                }),
                "none" => tl::enums::ChatReactions::None,
                list => {
                    let emoji_list = list
                        .split(',')
                        .map(|e| {
                            tl::enums::Reaction::Emoji(tl::types::ReactionEmoji {
                                emoticon: e.trim().to_owned(),
                            })
                        })
                        .collect();
                    tl::enums::ChatReactions::Some(tl::types::ChatReactionsSome {
                        reactions: emoji_list,
                    })
                }
            };
            c.set_chat_reactions(peer, available)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // transfer_chat_ownership (empty SRP, only works without 2FA)

    fn transfer_chat_ownership<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        new_owner_id: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let password = tl::enums::InputCheckPasswordSrp::InputCheckPasswordEmpty;
            c.transfer_chat_ownership(peer, new_owner_id, password)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    // stats

    fn get_broadcast_stats<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        _dark: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let raw = c.get_broadcast_stats(peer).await.map_err(py_err)?;
            let tl::enums::stats::BroadcastStats::BroadcastStats(s) = raw;
            let tl::enums::StatsDateRangeDays::StatsDateRangeDays(period) = s.period;
            let tl::enums::StatsAbsValueAndPrev::StatsAbsValueAndPrev(followers) = s.followers;
            let tl::enums::StatsAbsValueAndPrev::StatsAbsValueAndPrev(vpp) = s.views_per_post;
            let tl::enums::StatsAbsValueAndPrev::StatsAbsValueAndPrev(spp) = s.shares_per_post;
            let tl::enums::StatsPercentValue::StatsPercentValue(notif) = s.enabled_notifications;
            Ok(BroadcastStats {
                period_min_date: period.min_date,
                period_max_date: period.max_date,
                followers_current: followers.current,
                followers_previous: followers.previous,
                views_per_post_current: vpp.current,
                views_per_post_previous: vpp.previous,
                shares_per_post_current: spp.current,
                shares_per_post_previous: spp.previous,
                enabled_notifications_percent: notif.part / notif.total,
            })
        })
    }

    fn get_megagroup_stats<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        _dark: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let raw = c.get_megagroup_stats(peer).await.map_err(py_err)?;
            let tl::enums::stats::MegagroupStats::MegagroupStats(s) = raw;
            let tl::enums::StatsDateRangeDays::StatsDateRangeDays(period) = s.period;
            let tl::enums::StatsAbsValueAndPrev::StatsAbsValueAndPrev(members) = s.members;
            let tl::enums::StatsAbsValueAndPrev::StatsAbsValueAndPrev(messages) = s.messages;
            let tl::enums::StatsAbsValueAndPrev::StatsAbsValueAndPrev(viewers) = s.viewers;
            let tl::enums::StatsAbsValueAndPrev::StatsAbsValueAndPrev(posters) = s.posters;
            Ok(MegagroupStats {
                period_min_date: period.min_date,
                period_max_date: period.max_date,
                members_current: members.current,
                members_previous: members.previous,
                messages_current: messages.current,
                messages_previous: messages.previous,
                viewers_current: viewers.current,
                viewers_previous: viewers.previous,
                posters_current: posters.current,
                posters_previous: posters.previous,
            })
        })
    }

    /// Unified: set_profile replaces update_profile (0.3.6 stabilised name).
    #[pyo3(signature = (first_name=None, last_name=None, about=None))]
    fn set_profile<'py>(
        &self,
        py: Python<'py>,
        first_name: Option<String>,
        last_name: Option<String>,
        about: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.set_profile(first_name, last_name, about)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    /// set_username - stable alias (replaces update_username).
    fn set_username<'py>(&self, py: Python<'py>, username: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.set_username(username).await.map_err(py_err)?;
            Ok(())
        })
    }

    /// set_online - appear online. Replaces update_status(offline=False).
    fn set_online<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.set_online().await.map_err(py_err) })
    }

    /// set_offline - appear offline. Replaces update_status(offline=True).
    fn set_offline<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move { c.set_offline().await.map_err(py_err) })
    }

    /// mark_dialog_read - clears unread flag for a dialog.
    fn mark_dialog_read<'py>(&self, py: Python<'py>, peer: String) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.mark_dialog_read(peer).await.map_err(py_err)?;
            Ok(())
        })
    }

    /// sync_drafts - push all drafts as update events (replaces get_all_drafts public role).
    fn sync_drafts<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.sync_drafts().await.map_err(py_err)?;
            Ok(())
        })
    }

    /// get_message_history - stable public name for message history.
    #[pyo3(signature = (peer, limit = 100, offset_id = 0))]
    fn get_message_history<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        limit: i32,
        offset_id: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let msgs = c
                .get_message_history(peer, limit, offset_id)
                .await
                .map_err(py_err)?;
            Ok(msgs
                .into_iter()
                .map(|m| from_incoming(m, Some(Arc::clone(&c))))
                .collect::<Vec<_>>())
        })
    }

    /// join_request - unified approve/reject.
    fn join_request<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        user_id: i64,
        approve: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.join_request(peer, user_id, approve)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    /// all_join_requests - unified bulk approve/reject.
    #[pyo3(signature = (peer, approve, link = None))]
    fn all_join_requests<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        approve: bool,
        link: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            c.all_join_requests(peer, approve, link)
                .await
                .map_err(py_err)?;
            Ok(())
        })
    }

    /// open_mini_app - open a bot mini-app WebView.
    /// app_type: "main" | "url" | "simple"
    /// app_value: URL for "url"/"simple", empty for "main"
    #[pyo3(signature = (peer, app_type, app_value = String::new()))]
    fn open_mini_app<'py>(
        &self,
        py: Python<'py>,
        peer: String,
        app_type: String,
        app_value: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let c = Arc::clone(&self.inner);
        future_into_py(py, async move {
            let app = match app_type.as_str() {
                "main" => ferogram::MiniApp::Main,
                "simple" => ferogram::MiniApp::Simple(app_value),
                _ => ferogram::MiniApp::Url(app_value),
            };
            let session = c.open_mini_app(peer, app).await.map_err(py_err)?;
            Ok(MiniAppSession {
                url: session.url,
                query_id: session.query_id,
            })
        })
    }
}

fn parse_privacy_key(key: &str) -> Result<tl::enums::InputPrivacyKey, String> {
    match key {
        "status_timestamp" => Ok(tl::enums::InputPrivacyKey::StatusTimestamp),
        "chat_invite" => Ok(tl::enums::InputPrivacyKey::ChatInvite),
        "call" => Ok(tl::enums::InputPrivacyKey::PhoneCall),
        "forwards" => Ok(tl::enums::InputPrivacyKey::Forwards),
        "profile_photo" => Ok(tl::enums::InputPrivacyKey::ProfilePhoto),
        "phone_number" => Ok(tl::enums::InputPrivacyKey::PhoneNumber),
        "voice_messages" => Ok(tl::enums::InputPrivacyKey::VoiceMessages),
        "bio" => Ok(tl::enums::InputPrivacyKey::About),
        "birthday" => Ok(tl::enums::InputPrivacyKey::Birthday),
        _ => Err(format!(
            "unknown privacy key: {key}. use: status_timestamp, chat_invite, call, forwards, profile_photo, phone_number, voice_messages, bio, birthday"
        )),
    }
}

fn parse_privacy_rule(rule: &str) -> Result<tl::enums::InputPrivacyRule, String> {
    match rule {
        "allow_all" => Ok(tl::enums::InputPrivacyRule::InputPrivacyValueAllowAll),
        "allow_contacts" => Ok(tl::enums::InputPrivacyRule::InputPrivacyValueAllowContacts),
        "disallow_all" => Ok(tl::enums::InputPrivacyRule::InputPrivacyValueDisallowAll),
        "disallow_contacts" => Ok(tl::enums::InputPrivacyRule::InputPrivacyValueDisallowContacts),
        _ => Err(format!(
            "unknown rule: {rule}. use: allow_all, allow_contacts, disallow_all, disallow_contacts"
        )),
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
