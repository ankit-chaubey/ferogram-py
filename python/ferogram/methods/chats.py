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


"""Chat and channel lifecycle, settings, forums, photos and statistics."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from ..types import (
    Chat,
)
from .._internal import _as_input_channel

if TYPE_CHECKING:
    pass


class ChatMethods:
    """Chat and channel lifecycle, settings, forums, photos and statistics."""

    async def get_chat(self, peer: Any) -> "Chat | None":
        from ..types import Chat as _Chat
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if t == "inputPeerChat":
            result = await self._rpc({
                "_": "messages.getChats",
                "id": [input_peer["chat_id"]],
            })
            chats = result.get("chats") or [] if isinstance(result, dict) else []
            return _Chat.from_tl(chats[0]) if chats else None
        if t == "inputPeerChannel":
            result = await self._rpc({
                "_": "channels.getChannels",
                "id": [{
                    "_": "inputChannel",
                    "channel_id": input_peer["channel_id"],
                    "access_hash": input_peer.get("access_hash", 0),
                }],
            })
            chats = result.get("chats") or [] if isinstance(result, dict) else []
            return _Chat.from_tl(chats[0]) if chats else None
        if t == "inputPeerUser":
            users = await self.get_users_by_id([input_peer["user_id"]])
            raw = users[0] if users else None
            if not raw:
                return None
            return _Chat(
                id=raw.get("id", 0),
                title=((raw.get("first_name") or "") + " " + (raw.get("last_name") or "")).strip(),
                username=raw.get("username"),
                is_channel=False, is_megagroup=False, is_gigagroup=False,
                is_broadcast=False, is_community=False, members_count=None,
                access_hash=raw.get("access_hash", 0), _raw=raw,
            )
        return None

    def _resolve_chat_invite_join_result(self, result: Any) -> dict | None:
        """Normalize a `messages.ChatInviteJoinResult` into a resolved InputPeer.

        `messages.importChatInvite` and `channels.joinChannel` no longer
        return a bare `Updates` object (layer 232) - they return this union:

          - `chatInviteJoinResultOk` wraps `updates: Updates`. The joined
            chat/channel/community is pulled out of the embedded
            users/chats and cached.
          - `chatInviteJoinResultWebView` carries only `bot_id`/`query_id`/
            `users`, with no Updates at all. Telegram hasn't actually
            completed the join here - the client needs to drive an
            interactive bot webview flow to finish it. That flow isn't
            implemented, so this returns None instead of pretending the
            join succeeded.
        """
        if not isinstance(result, dict):
            return None
        t = result.get("_", "")
        if t == "messages.chatInviteJoinResultWebView":
            return None
        if t != "messages.chatInviteJoinResultOk":
            return None
        updates = result.get("updates") or {}
        if not isinstance(updates, dict):
            return None
        self._populate_cache(updates)
        for ch in updates.get("chats") or []:
            if not isinstance(ch, dict) or ch.get("min"):
                continue
            ctype = ch.get("_", "")
            if ctype in ("channel", "community"):
                return {"_": "inputPeerChannel", "channel_id": ch.get("id"), "access_hash": ch.get("access_hash", 0)}
            if ctype == "chat":
                return {"_": "inputPeerChat", "chat_id": ch.get("id")}
        return None

    async def join_chat(self, peer: str) -> dict | None:
        """Join a chat, channel, or community by username/link.

        Returns the joined chat's InputPeer on success, or None if Telegram
        responded with a WebView join result - meaning the join requires an
        interactive bot flow that hasn't completed yet (see
        `_resolve_chat_invite_join_result`).
        """
        if peer.startswith("+") or "/+" in peer:
            link = peer.split("/+")[-1] if "/+" in peer else peer[1:]
            result = await self._rpc({"_": "messages.importChatInvite", "hash": link})
            return self._resolve_chat_invite_join_result(result)
        else:
            channel = await self._resolve_peer(peer)
            result = await self._rpc({"_": "channels.joinChannel", "channel": channel})
            if isinstance(result, dict) and result.get("_") == "messages.chatInviteJoinResultWebView":
                return None
            if isinstance(result, dict) and result.get("_") == "messages.chatInviteJoinResultOk":
                self._populate_cache(result.get("updates") or {})
            return channel

    async def leave_chat(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if "Channel" in t:
            await self._rpc({"_": "channels.leaveChannel", "channel": input_peer})
        else:
            me = await self.get_me()  # noqa: F841
            await self._rpc({"_": "messages.deleteChatUser", "chat_id": input_peer.get("chat_id", 0), "user_id": {"_": "inputUserSelf"}})

    async def get_online_count(self, peer: str) -> int:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getOnlines", "peer": input_peer})
        return result.get("onlines", 0) if isinstance(result, dict) else 0

    async def create_group(self, title: str, user_ids: list[int]) -> dict:
        result = await self._rpc({"_": "messages.createChat", "users": user_ids, "title": title})
        return result

    async def create_channel(self, title: str, about: str = "", broadcast: bool = True) -> dict:
        result = await self._rpc({
            "_": "channels.createChannel",
            "title": title,
            "about": about,
            "broadcast": broadcast,
            "megagroup": not broadcast,
        })
        return result

    async def delete_channel(self, peer: str) -> None:
        channel = await self._resolve_peer(peer)
        await self._rpc({"_": "channels.deleteChannel", "channel": channel})

    async def delete_chat(self, chat_id: int) -> None:
        await self._rpc({"_": "messages.deleteChat", "chat_id": chat_id})

    async def edit_chat_title(self, peer: str, title: str) -> None:
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if "Channel" in t:
            await self._rpc({"_": "channels.editTitle", "channel": input_peer, "title": title})
        else:
            await self._rpc({"_": "messages.editChatTitle", "chat_id": input_peer.get("chat_id", 0), "title": title})

    async def edit_chat_about(self, peer: str, about: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.editChatAbout", "peer": input_peer, "about": about})

    async def set_history_ttl(self, peer: str, period: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.setHistoryTTL", "peer": input_peer, "period": period})

    async def migrate_chat(self, chat_id: int) -> dict:
        result = await self._rpc({"_": "messages.migrateChat", "chat_id": chat_id})
        return result

    async def set_chat_reactions(self, peer: str, reactions: str) -> None:
        input_peer = await self._resolve_peer(peer)
        if reactions == "all":
            allowed = {"_": "chatReactionsAll"}
        elif reactions == "none":
            allowed = {"_": "chatReactionsNone"}
        else:
            emojis = [e.strip() for e in reactions.split(",") if e.strip()]
            allowed = {"_": "chatReactionsSome", "reactions": [{"_": "reactionEmoji", "emoticon": e} for e in emojis]}
        await self._rpc({"_": "messages.setChatAvailableReactions", "peer": input_peer, "available_reactions": allowed})

    async def toggle_forum(self, peer: str, enabled: bool, tabs: bool = False, sidebar: bool = False) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "channels.toggleForum",
            "channel": _as_input_channel(input_peer, "toggle_forum"),
            "enabled": enabled,
            "tabs": tabs,
            "sidebar": sidebar,
        })

    async def get_forum_topics(self, peer: str, limit: int = 100) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getForumTopics",
            "peer": input_peer,
            "offset_date": 0,
            "offset_id": 0,
            "offset_topic": 0,
            "limit": limit,
        })
        return result.get("topics", []) if isinstance(result, dict) else []

    async def create_forum_topic(self, peer: str, title: str,
                                  icon_color: int | None = None,
                                  icon_emoji_id: int | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        req: dict = {
            "_": "messages.createForumTopic",
            "peer": input_peer,
            "title": title,
            "random_id": random.randint(0, 2**63 - 1),
        }
        if icon_color is not None:
            req["icon_color"] = icon_color
        if icon_emoji_id is not None:
            req["icon_emoji_id"] = icon_emoji_id
        await self._rpc(req)

    async def edit_forum_topic(self, peer: str, topic_id: int,
                                title: str | None = None,
                                closed: bool | None = None,
                                hidden: bool | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        req: dict = {"_": "messages.editForumTopic", "peer": input_peer, "topic_id": topic_id}
        if title is not None:
            req["title"] = title
        if closed is not None:
            req["closed"] = closed
        if hidden is not None:
            req["hidden"] = hidden
        await self._rpc(req)

    async def delete_forum_topic_history(self, peer: str, top_msg_id: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.deleteTopicHistory", "peer": input_peer, "top_msg_id": top_msg_id})

    async def edit_chat_photo(self, peer: str, path: str) -> None:
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        t = input_peer.get("_", "")
        if "Channel" in t:
            await self._rpc({
                "_": "channels.editPhoto",
                "channel": input_peer,
                "photo": {"_": "inputChatUploadedPhoto", "file": file_input},
            })
        else:
            await self._rpc({
                "_": "messages.editChatPhoto",
                "chat_id": input_peer.get("chat_id", 0),
                "photo": {"_": "inputChatUploadedPhoto", "file": file_input},
            })

    async def get_chat_photos(self, peer: str, limit: int = 100) -> list[tuple[int, int, int]]:
        """Photo/avatar history for a group or channel (get_profile_photos only works for users).

        The current photo comes from the chat's full info, so it's returned
        even if every photo-change message has been deleted. Older photos
        come from `messageActionChatEditPhoto` service messages, so those
        are lost if the underlying messages were deleted; there's no other
        way to recover them.
        """
        input_peer = await self._resolve_peer(peer)
        photos: list[tuple[int, int, int]] = []
        seen_id: int | None = None

        t = input_peer.get("_", "")
        try:
            if "Channel" in t:
                full_result = await self._rpc({"_": "channels.getFullChannel", "channel": input_peer})
            else:
                full_result = await self._rpc({"_": "messages.getFullChat", "chat_id": input_peer.get("chat_id", 0)})
            full = full_result.get("full_chat", {}) if isinstance(full_result, dict) else {}
            current = full.get("chat_photo")
            if isinstance(current, dict) and current.get("_") == "photo":
                seen_id = current.get("id", 0)
                photos.append((current.get("id", 0), current.get("access_hash", 0), current.get("dc_id", 0)))
        except Exception as exc:
            # current photo is a nice-to-have; fall through to history regardless
            self._log.debug("get_chat_photos() current-photo lookup failed: %s", exc)

        result = await self._rpc({
            "_": "messages.search",
            "peer": input_peer,
            "q": "",
            "filter": {"_": "inputMessagesFilterChatPhotos"},
            "min_date": 0,
            "max_date": 0,
            "offset_id": 0,
            "add_offset": 0,
            "limit": limit,
            "max_id": 0,
            "min_id": 0,
            "hash": 0,
        })
        messages = result.get("messages", []) if isinstance(result, dict) else []
        for m in messages:
            action = m.get("action", {}) if isinstance(m, dict) else {}
            if action.get("_") != "messageActionChatEditPhoto":
                continue
            photo = action.get("photo", {})
            if not isinstance(photo, dict) or photo.get("_") != "photo":
                continue
            pid = photo.get("id", 0)
            if pid == seen_id:
                continue
            photos.append((pid, photo.get("access_hash", 0), photo.get("dc_id", 0)))

        return photos

    async def get_broadcast_stats(self, peer: str, dark: bool = False) -> dict:
        channel = await self._resolve_peer(peer)
        return await self._rpc({"_": "stats.getBroadcastStats", "channel": channel, "dark": dark})

    async def get_megagroup_stats(self, peer: str, dark: bool = False) -> dict:
        channel = await self._resolve_peer(peer)
        return await self._rpc({"_": "stats.getMegagroupStats", "channel": channel, "dark": dark})

    async def get_chat_full(self, peer: str) -> tuple[int, str, int | None]:
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if "Channel" in t:
            result = await self._rpc({"_": "channels.getFullChannel", "channel": input_peer})
        else:
            result = await self._rpc({"_": "messages.getFullChat", "chat_id": input_peer.get("chat_id", 0)})
        full = result.get("full_chat", {}) if isinstance(result, dict) else {}
        return full.get("id", 0), full.get("about", ""), full.get("participants_count")
