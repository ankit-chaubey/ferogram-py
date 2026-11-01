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


"""Users, contacts, profile, privacy, notifications and peer resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..types import (
    PrivacyKey, PrivacyRule,
    User,
)

if TYPE_CHECKING:
    pass


class UserMethods:
    """Users, contacts, profile, privacy, notifications and peer resolution."""

    async def get_me(self) -> dict:
        result = await self._rpc({"_": "users.getUsers", "id": [{"_": "inputUserSelf"}]})
        users = result if isinstance(result, list) else []
        return users[0] if users else {}

    async def get_users_by_id(self, user_ids: list[int]) -> list[dict | None]:
        ids = [{"_": "inputUser", "user_id": uid, "access_hash": self._peer_cache.get_user(uid) or 0}
               for uid in user_ids]
        result = await self._rpc({"_": "users.getUsers", "id": ids})
        return result if isinstance(result, list) else []

    async def get_user_full(self, user_id: int) -> dict:
        peer = await self._resolve_peer(user_id)
        return await self._rpc({"_": "users.getFullUser", "id": peer})

    async def get_user(self, user_id: int) -> "User | None":
        from ..types import User as _User
        peers = await self.get_users_by_id([user_id])
        raw = peers[0] if peers else None
        if not raw:
            return None
        return _User.from_tl(raw)

    async def get_contacts(self) -> list[dict]:
        result = await self._rpc({"_": "contacts.getContacts", "hash": 0})
        return result.get("users", []) if isinstance(result, dict) else []

    async def delete_profile_photos(self) -> None:
        result = await self._rpc({"_": "photos.getUserPhotos", "user_id": {"_": "inputUserSelf"}, "offset": 0, "max_id": 0, "limit": 100})
        photos = result.get("photos", []) if isinstance(result, dict) else []
        if photos:
            ids = [{"_": "inputPhoto", "id": p.get("id", 0), "access_hash": p.get("access_hash", 0), "file_reference": p.get("file_reference", b"")} for p in photos]
            await self._rpc({"_": "photos.deletePhotos", "id": ids})

    async def get_profile_photos(self, peer: str, limit: int = 100) -> list[tuple[int, int, int]]:
        user_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "photos.getUserPhotos", "user_id": user_peer, "offset": 0, "max_id": 0, "limit": limit})
        photos = result.get("photos", []) if isinstance(result, dict) else []
        return [(p.get("id", 0), p.get("access_hash", 0), p.get("dc_id", 0)) for p in photos]

    async def block_user(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "contacts.block", "id": input_peer})

    async def unblock_user(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "contacts.unblock", "id": input_peer})

    async def get_blocked_users(self, limit: int = 100, my_stories_from: bool = False) -> list[int]:
        result = await self._rpc({"_": "contacts.getBlocked", "my_stories_from": my_stories_from, "offset": 0, "limit": limit})
        blocked = result.get("blocked", []) if isinstance(result, dict) else []
        return [b.get("peer_id", {}).get("user_id", 0) for b in blocked]

    async def add_contact(self, user_id: int, first_name: str, last_name: str = "", phone: str = "",
                          add_phone_privacy_exception: bool = False) -> None:
        ah = self._peer_cache.get_user(user_id) or 0
        await self._rpc({
            "_": "contacts.addContact",
            "add_phone_privacy_exception": add_phone_privacy_exception,
            "id": {"_": "inputUser", "user_id": user_id, "access_hash": ah},
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
        })

    async def delete_contacts(self, user_ids: list[int]) -> None:
        ids = [{"_": "inputUser", "user_id": uid, "access_hash": self._peer_cache.get_user(uid) or 0} for uid in user_ids]
        await self._rpc({"_": "contacts.deleteContacts", "id": ids})

    async def get_common_chats(self, user_id: int, limit: int = 100) -> list[dict]:
        ah = self._peer_cache.get_user(user_id) or 0
        result = await self._rpc({
            "_": "messages.getCommonChats",
            "user_id": {"_": "inputUser", "user_id": user_id, "access_hash": ah},
            "max_id": 0,
            "limit": limit,
        })
        return result.get("chats", []) if isinstance(result, dict) else []

    async def search_peer(self, query: str) -> list[str]:
        result = await self._rpc({"_": "contacts.search", "q": query, "limit": 20})
        out = []
        for u in result.get("users", []) if isinstance(result, dict) else []:
            out.append(u.get("username") or str(u.get("id", "")))
        return out

    async def resolve_peer(self, peer: str) -> int:
        result = await self._resolve_peer(peer)
        return result.get("user_id") or result.get("channel_id") or result.get("chat_id") or 0

    async def resolve_username(self, username: str) -> int:
        uname = username.lstrip("@")
        result = await self._rpc({"_": "contacts.resolveUsername", "username": uname})
        peer = result.get("peer", {}) if isinstance(result, dict) else {}
        return peer.get("user_id") or peer.get("channel_id") or peer.get("chat_id") or 0

    async def resolve(self, peer: Any) -> dict:
        return await self._resolve_peer(peer)

    async def warm_peer_cache_from_dialogs(self) -> None:
        await self.get_dialogs(limit=500)

    async def set_profile(self, first_name: str | None = None, last_name: str | None = None, about: str | None = None) -> None:
        req: dict = {"_": "account.updateProfile"}
        if first_name is not None:
            req["first_name"] = first_name
        if last_name is not None:
            req["last_name"] = last_name
        if about is not None:
            req["about"] = about
        await self._rpc(req)

    async def set_username(self, username: str) -> None:
        await self._rpc({"_": "account.updateUsername", "username": username})

    async def set_online(self) -> None:
        await self._rpc({"_": "account.updateStatus", "offline": False})

    async def set_offline(self) -> None:
        await self._rpc({"_": "account.updateStatus", "offline": True})

    async def get_privacy(self, key: "PrivacyKey | str") -> list[str]:
        key_map = {
            "status_timestamp": "inputPrivacyKeyStatusTimestamp",
            "phone": "inputPrivacyKeyPhoneNumber",
            "bio": "inputPrivacyKeyAbout",
            "profile_photo": "inputPrivacyKeyProfilePhoto",
            "forwards": "inputPrivacyKeyForwards",
            "voice_call": "inputPrivacyKeyPhoneCall",
            "groups": "inputPrivacyKeyChatInvite",
        }
        tl_key = key_map.get(str(key), str(key))
        result = await self._rpc({"_": "account.getPrivacy", "key": {"_": tl_key}})
        rules = result.get("rules", []) if isinstance(result, dict) else []
        return [r.get("_", "") for r in rules]

    async def set_privacy(self, key: "PrivacyKey | str", rule: "PrivacyRule | str") -> None:
        key_map = {
            "status_timestamp": "inputPrivacyKeyStatusTimestamp",
            "phone": "inputPrivacyKeyPhoneNumber",
        }
        rule_map = {
            "allow_all": "inputPrivacyValueAllowAll",
            "allow_contacts": "inputPrivacyValueAllowContacts",
            "disallow_all": "inputPrivacyValueDisallowAll",
        }
        tl_key  = key_map.get(str(key), str(key))
        tl_rule = rule_map.get(str(rule), str(rule))
        await self._rpc({"_": "account.setPrivacy", "key": {"_": tl_key}, "rules": [{"_": tl_rule}]})

    async def mute_chat(self, peer: str, mute_until: int) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "account.updateNotifySettings",
            "peer": {"_": "inputNotifyPeer", "peer": input_peer},
            "settings": {"_": "inputPeerNotifySettings", "mute_until": mute_until},
        })

    async def unmute_chat(self, peer: str) -> None:
        await self.mute_chat(peer, 0)

    async def get_notify_settings(self, peer: str) -> dict:
        input_peer = await self._resolve_peer(peer)
        return await self._rpc({"_": "account.getNotifySettings", "peer": {"_": "inputNotifyPeer", "peer": input_peer}})

    async def update_notify_settings(self, peer: str, mute_until: int | None = None,
                                      silent: bool | None = None, show_previews: bool | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        settings: dict = {"_": "inputPeerNotifySettings"}
        if mute_until is not None:
            settings["mute_until"] = mute_until
        if silent is not None:
            settings["silent"] = silent
        if show_previews is not None:
            settings["show_previews"] = show_previews
        await self._rpc({"_": "account.updateNotifySettings", "peer": {"_": "inputNotifyPeer", "peer": input_peer}, "settings": settings})
