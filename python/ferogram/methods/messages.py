# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# ferogram is a high-performance Telegram MTProto framework written in Rust.
# ferogram-py is a Python MTProto library powered by ferogram, delivering
# native Rust performance through a clean and Pythonic API for building
# Telegram clients, bots, and applications.
#
# Rust: https://github.com/ankit-chaubey/ferogram
# Python: https://github.com/ankit-chaubey/ferogram-py
#
# If you use or modify this code, keep this notice at the top of the file
# and include the LICENSE-MIT or LICENSE-APACHE file from this repository.


"""Sending, editing, searching and reacting to messages, polls and drafts."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from ..raw import tl as _tl
from ..raw.generated._tl_schema import _SCHEMA
from ..types import (
    ChatAction, Message,
)
from .._internal import (
    _as_input_channel,
    _markup_to_dict,
)

if TYPE_CHECKING:
    pass


class MessageMethods:
    """Sending, editing, searching and reacting to messages, polls and drafts."""

    async def send_message(self, peer: Any, text: str, *,
                           parse_mode: str | None = None,
                           reply_to: int | None = None,
                           reply_markup=None,
                           no_webpage: bool = True,
                           silent: bool = False,
                           schedule_date: int | None = None,
                           send_as: Any = None,
                           noforwards: bool = False,
                           background: bool = False,
                           clear_draft: bool = False,
                           effect: int | None = None,
                           invert_media: bool = False) -> Message:
        pm = self._resolve_pm(parse_mode)
        if pm in ("markdown", "md"):
            plain, entities = _tl.parse_markdown(text)
        elif pm == "html":
            plain, entities = _tl.parse_html(text)
        else:
            plain, entities = text, []
        input_peer = await self._resolve_peer(peer)
        req: dict = {
            "_": "messages.sendMessage",
            "peer": input_peer,
            "message": plain,
            "random_id": random.randint(-(2**63), 2**63 - 1),
            "entities": entities,
        }
        if no_webpage:
            req["no_webpage"] = True
        if silent:
            req["silent"] = True
        if noforwards:
            req["noforwards"] = True
        if background:
            req["background"] = True
        if clear_draft:
            req["clear_draft"] = True
        if invert_media:
            req["invert_media"] = True
        if schedule_date is not None:
            req["schedule_date"] = schedule_date
        if effect is not None:
            req["effect"] = effect
        if send_as is not None:
            req["send_as"] = await self._resolve_peer(send_as)
        if reply_to is not None:
            req["reply_to"] = {"_": "inputReplyToMessage", "reply_to_msg_id": reply_to}
        if reply_markup is not None:
            req["reply_markup"] = _markup_to_dict(reply_markup)
        resp = await self._rpc(req)
        return self._extract_sent_message(resp, text=plain, peer_id=input_peer)

    async def send_to_self(self, text: str) -> None:
        await self.send_message("me", text)

    async def edit_message(self, peer: Any, message_id: int, new_text: str, *,
                           parse_mode: str | None = None,
                           reply_markup=None,
                           no_webpage: bool = True) -> None:
        pm = self._resolve_pm(parse_mode)
        if pm in ("markdown", "md"):
            plain, entities = _tl.parse_markdown(new_text)
        elif pm == "html":
            plain, entities = _tl.parse_html(new_text)
        else:
            plain, entities = new_text, []
        input_peer = await self._resolve_peer(peer)
        req: dict = {
            "_": "messages.editMessage",
            "peer": input_peer,
            "id": message_id,
            "message": plain,
        }
        if no_webpage:
            req["no_webpage"] = True
        if entities:
            req["entities"] = entities
        if reply_markup is not None:
            req["reply_markup"] = _markup_to_dict(reply_markup)
        await self._rpc(req)

    async def delete_message(self, message_id: int, revoke: bool = True) -> None:
        await self.delete_messages([message_id], revoke)

    async def delete_messages(self, message_ids: list[int], revoke: bool = True) -> None:
        await self._rpc({
            "_": "messages.deleteMessages",
            "id": message_ids,
            "revoke": revoke,
        })

    async def delete_messages_in(self, peer: Any, message_ids: list[int], revoke: bool = True) -> None:
        """Delete messages in a specific chat, using channels.deleteMessages for channels/supergroups."""
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if t == "inputPeerChannel":
            channel_id = input_peer["channel_id"]
            req_bytes = _tl.serialize({
                "_": "channels.deleteMessages",
                "channel": {
                    "_": "inputChannel",
                    "channel_id": channel_id,
                    "access_hash": input_peer.get("access_hash", 0),
                },
                "id": message_ids,
            }, _SCHEMA)
            # channels.deleteMessages returns a channel-scoped
            # AffectedMessages - the generic rpc_call auto-feed can't tell
            # that apart from a global one, only this call site knows
            # channel_id, so route it through the dedicated method instead.
            await self._conn.delete_channel_messages(req_bytes, channel_id)
        else:
            await self._rpc({
                "_": "messages.deleteMessages",
                "id": message_ids,
                "revoke": revoke,
            })

    async def forward_messages(self, destination: str, source: str, message_ids: list[int], *,
                               silent: bool = False,
                               drop_author: bool = False,
                               drop_media_captions: bool = False,
                               noforwards: bool = False,
                               background: bool = False,
                               schedule_date: int | None = None,
                               send_as: Any = None) -> None:
        from_peer = await self._resolve_peer(source)
        to_peer   = await self._resolve_peer(destination)
        req: dict = {
            "_": "messages.forwardMessages",
            "from_peer": from_peer,
            "to_peer": to_peer,
            "id": message_ids,
            "random_id": [random.randint(-(2**63), 2**63 - 1) for _ in message_ids],
        }
        if silent:
            req["silent"] = True
        if drop_author:
            req["drop_author"] = True
        if drop_media_captions:
            req["drop_media_captions"] = True
        if noforwards:
            req["noforwards"] = True
        if background:
            req["background"] = True
        if schedule_date is not None:
            req["schedule_date"] = schedule_date
        if send_as is not None:
            req["send_as"] = await self._resolve_peer(send_as)
        await self._rpc(req)

    async def pin_message(self, peer: Any, message_id: int, *, notify: bool = False) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.updatePinnedMessage",
            "peer": input_peer,
            "id": message_id,
            "silent": not notify,
        })

    async def unpin_message(self, peer: str, message_id: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.updatePinnedMessage",
            "peer": input_peer,
            "id": message_id,
            "unpin": True,
        })

    async def unpin_all_messages(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.unpinAllMessages", "peer": input_peer})

    async def mark_as_read(self, peer: str) -> None:
        await self.mark_dialog_read(peer)

    async def mark_dialog_read(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.readHistory", "peer": input_peer, "max_id": 0})

    async def clear_mentions(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.readMentions", "peer": input_peer})

    async def send_reaction(self, peer: str, message_id: int, emoji: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.sendReaction",
            "peer": input_peer,
            "msg_id": message_id,
            "reaction": [{"_": "reactionEmoji", "emoticon": emoji}],
        })

    async def send_chat_action(self, peer: str, action: "ChatAction | str") -> None:
        input_peer = await self._resolve_peer(peer)
        action_str = str(action)
        action_map = {
            "typing": "sendMessageTypingAction",
            "record_video": "sendMessageRecordVideoAction",
            "upload_video": "sendMessageUploadVideoAction",
            "record_audio": "sendMessageRecordAudioAction",
            "upload_audio": "sendMessageUploadAudioAction",
            "upload_photo": "sendMessageUploadPhotoAction",
            "upload_document": "sendMessageUploadDocumentAction",
            "find_location": "sendMessageGeoLocationAction",
            "record_video_note": "sendMessageRecordRoundAction",
            "upload_video_note": "sendMessageUploadRoundAction",
            "choose_sticker": "sendMessageChooseStickerAction",
            "cancel": "sendMessageCancelAction",
        }
        tl_action = action_map.get(action_str, action_str)
        await self._rpc({
            "_": "messages.setTyping",
            "peer": input_peer,
            "action": {"_": tl_action},
        })

    async def send_dice(self, peer: str, emoticon: str = "🎲") -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": {"_": "inputMediaDice", "emoticon": emoticon},
            "message": "",
            "random_id": random.randint(-(2**63), 2**63 - 1),
        })

    async def get_messages_by_id(self, peer: str, message_ids: list[int]) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "channels.getMessages",
            "channel": input_peer,
            "id": [{"_": "inputMessageID", "id": mid} for mid in message_ids],
        })
        return result.get("messages", []) if isinstance(result, dict) else []

    async def get_message(self, peer: str, msg_id: int) -> dict | None:
        msgs = await self.get_messages_by_id(peer, [msg_id])
        return msgs[0] if msgs else None

    async def get_message_history(self, peer: str, limit: int = 100, offset_id: int = 0) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getHistory",
            "peer": input_peer,
            "offset_id": offset_id,
            "offset_date": 0,
            "add_offset": 0,
            "limit": limit,
            "max_id": 0,
            "min_id": 0,
            "hash": 0,
        })
        return result.get("messages", []) if isinstance(result, dict) else []

    async def search_messages(self, peer: str, query: str, limit: int = 100) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.search",
            "peer": input_peer,
            "q": query,
            "filter": {"_": "inputMessagesFilterEmpty"},
            "min_date": 0,
            "max_date": 0,
            "offset_id": 0,
            "add_offset": 0,
            "limit": limit,
            "max_id": 0,
            "min_id": 0,
            "hash": 0,
        })
        return result.get("messages", []) if isinstance(result, dict) else []

    async def search_global(self, query: str, limit: int = 100) -> list[dict]:
        result = await self._rpc({
            "_": "messages.searchGlobal",
            "q": query,
            "filter": {"_": "inputMessagesFilterEmpty"},
            "min_date": 0,
            "max_date": 0,
            "offset_rate": 0,
            "offset_peer": {"_": "inputPeerEmpty"},
            "offset_id": 0,
            "limit": limit,
        })
        return result.get("messages", []) if isinstance(result, dict) else []

    async def get_pinned_message(self, peer: str) -> dict | None:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.search",
            "peer": input_peer,
            "q": "",
            "filter": {"_": "inputMessagesFilterPinned"},
            "min_date": 0, "max_date": 0, "offset_id": 0, "add_offset": 0,
            "limit": 1, "max_id": 0, "min_id": 0, "hash": 0,
        })
        msgs = result.get("messages", []) if isinstance(result, dict) else []
        return msgs[0] if msgs else None

    async def get_scheduled_messages(self, peer: str) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getScheduledHistory", "peer": input_peer, "hash": 0})
        return result.get("messages", []) if isinstance(result, dict) else []

    async def translate_messages(self, peer: str, msg_ids: list[int], to_lang: str) -> list[str]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.translateText",
            "peer": input_peer,
            "id": msg_ids,
            "to_lang": to_lang,
        })
        return [r.get("text", "") for r in (result.get("result") or [])]

    async def get_reply_to_message(self, peer: str, msg_id: int) -> dict | None:
        msg = await self.get_message(peer, msg_id)
        if not msg:
            return None
        reply_to = msg.get("reply_to", {})
        reply_id = reply_to.get("reply_to_msg_id") if isinstance(reply_to, dict) else None
        if reply_id is None:
            return None
        return await self.get_message(peer, reply_id)

    async def get_discussion_message(self, peer: str, msg_id: int) -> tuple[list[dict], int, int, int]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getDiscussionMessage", "peer": input_peer, "msg_id": msg_id})
        msgs = result.get("messages", [])
        return msgs, result.get("unread_count", 0), result.get("max_id", 0), result.get("read_inbox_max_id", 0)

    async def save_draft(self, peer: str, text: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.saveDraft", "peer": input_peer, "message": text})

    async def clear_all_drafts(self) -> None:
        await self._rpc({"_": "messages.clearAllDrafts"})

    async def sync_drafts(self) -> None:
        await self._rpc({"_": "messages.getAllDrafts"})

    async def send_poll(self, peer: str, question: str, answers: list[str], *,
                        quiz: bool = False, correct_index: int | None = None,
                        multiple_choice: bool = False, public_voters: bool = False,
                        shuffle_answers: bool = False, hide_results_until_close: bool = False,
                        close_period: int | None = None, close_date: int | None = None,
                        solution: str | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        poll: dict = {
            "_": "poll",
            "id": random.randint(0, 2**63 - 1),
            "question": {"_": "textWithEntities", "text": question, "entities": []},
            "answers": [
                {"_": "pollAnswer",
                 "text": {"_": "textWithEntities", "text": a, "entities": []},
                 "option": bytes([i])}
                for i, a in enumerate(answers)
            ],
            "quiz": quiz,
            "multiple_choice": multiple_choice and not quiz,
            "public_voters": public_voters,
            "shuffle_answers": shuffle_answers,
            "hide_results_until_close": hide_results_until_close,
            "hash": 0,
        }
        if close_period is not None:
            poll["close_period"] = close_period
        if close_date is not None:
            poll["close_date"] = close_date
        media: dict = {"_": "inputMediaPoll", "poll": poll}
        if quiz and correct_index is not None:
            media["correct_answers"] = [correct_index]
        if solution:
            media["solution"] = solution
            media["solution_entities"] = []
        await self._rpc({
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": media,
            "message": "",
            "random_id": random.randint(-(2**63), 2**63 - 1),
        })

    async def send_vote(self, peer: str, msg_id: int, options: list[bytes]) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.sendVote", "peer": input_peer, "msg_id": msg_id, "options": options})

    async def get_poll_votes(self, peer: str, msg_id: int, limit: int = 100) -> list[tuple[int, bytes]]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getPollVotes",
            "peer": input_peer,
            "id": msg_id,
            "limit": limit,
        })
        votes = result.get("votes", []) if isinstance(result, dict) else []
        return [(v.get("user_id", 0), v.get("option", b"")) for v in votes]

    async def get_poll_results(self, peer: str, msg_id: int, poll_hash: int = 0) -> dict:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getPollResults", "peer": input_peer, "msg_id": msg_id,
                                  "poll_hash": poll_hash})
        return result if isinstance(result, dict) else {}

    async def poll_results(self, peer: str, msg_id: int) -> dict:
        return await self.get_poll_results(peer, msg_id)

    async def get_poll_stats(self, peer: str, msg_id: int) -> str:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "stats.getMessagePublicForwards",
            "channel": _as_input_channel(input_peer, "get_poll_stats"),
            "msg_id": msg_id,
            "offset": "",
            "limit": 100,
        })
        return str(result)

    async def read_reactions(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.readReactions", "peer": input_peer})

    async def clear_recent_reactions(self) -> None:
        await self._rpc({"_": "messages.clearRecentReactions"})

    async def get_reaction_list(self, peer: str, msg_id: int, limit: int = 100) -> list[tuple[int, str]]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getMessageReactionsList",
            "peer": input_peer,
            "id": msg_id,
            "limit": limit,
        })
        reactions = result.get("reactions", []) if isinstance(result, dict) else []
        out = []
        for r in reactions:
            peer_id = r.get("peer_id", r.get("user_id", 0))
            emoji = ""
            reaction = r.get("reaction", {})
            if isinstance(reaction, dict):
                emoji = reaction.get("emoticon", "")
            out.append((peer_id, emoji))
        return out

    async def delete_reaction(self, peer: str, msg_id: int) -> None:
        """Remove your own reaction from a message.

        MTProto has no method to remove another user's reaction.
        Sends messages.sendReaction with an empty reaction list, which
        clears the calling user's reaction on the given message.
        """
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "messages.sendReaction",
            "peer": input_peer,
            "msg_id": msg_id,
            "reaction": [],
        })

    async def get_custom_emoji_documents(self, document_ids: list[int]) -> list[int]:
        result = await self._rpc({"_": "messages.getCustomEmojiDocuments", "document_id": document_ids})
        docs = result if isinstance(result, list) else []
        return [d.get("id", 0) for d in docs if isinstance(d, dict)]

    async def get_web_page_preview(self, text: str) -> str | None:
        result = await self._rpc({"_": "messages.getWebPagePreview", "message": text})
        if isinstance(result, dict) and result.get("_") == "messageMediaWebPage":
            page = result.get("webpage", {})
            return page.get("url") if isinstance(page, dict) else None
        return None

    async def iter_reaction_users(self, peer: str, msg_id: int, *, reaction: str | None = None):
        input_peer = await self._resolve_peer(peer)
        req: dict = {"_": "messages.getMessageReactionsList", "peer": input_peer, "id": msg_id, "limit": 100}
        if reaction:
            req["reaction"] = {"_": "reactionEmoji", "emoticon": reaction}
        result = await self._rpc(req)
        reactions = result.get("reactions", []) if isinstance(result, dict) else []
        for r in reactions:
            yield r

    async def iter_messages(self, peer: str, *, limit: int | None = None, offset_id: int = 0):
        remaining = limit
        cur_offset = offset_id
        batch = 100
        while True:
            chunk_size = batch if remaining is None else min(batch, remaining)
            if chunk_size <= 0:
                return
            msgs = await self.get_message_history(peer, chunk_size, cur_offset)
            if not msgs:
                return
            for m in msgs:
                yield m
            if remaining is not None:
                remaining -= len(msgs)
                if remaining <= 0:
                    return
            if len(msgs) < chunk_size:
                return
            cur_offset = msgs[-1].get("id", 0)
