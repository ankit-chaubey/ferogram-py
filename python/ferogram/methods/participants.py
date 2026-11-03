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


"""Members, admins, bans, rights and join requests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from .._internal import _srp_answer

if TYPE_CHECKING:
    pass


class ParticipantMethods:
    """Members, admins, bans, rights and join requests."""

    async def get_chat_administrators(self, peer: str) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "channels.getParticipants",
            "channel": input_peer,
            "filter": {"_": "channelParticipantsAdmins"},
            "offset": 0,
            "limit": 200,
            "hash": 0,
        })
        return result.get("participants", []) if isinstance(result, dict) else []

    async def get_participants(self, peer: str, limit: int = 200) -> list[dict]:
        return await self.get_participants_filtered(peer, "recent", limit)

    async def get_participants_filtered(self, peer: str, filter: str = "recent", limit: int = 200) -> list[dict]:
        input_peer = await self._resolve_peer(peer)
        filter_map = {
            "recent": "channelParticipantsRecent",
            "admins": "channelParticipantsAdmins",
            "kicked": "channelParticipantsKicked",
            "bots": "channelParticipantsBots",
            "contacts": "channelParticipantsContacts",
        }
        tl_filter = filter_map.get(filter, "channelParticipantsRecent")
        result = await self._rpc({
            "_": "channels.getParticipants",
            "channel": input_peer,
            "filter": {"_": tl_filter},
            "offset": 0,
            "limit": limit,
            "hash": 0,
        })
        return result.get("participants", []) if isinstance(result, dict) else []

    async def kick_participant(self, peer: str, user: str) -> None:
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        # Kick = temporary ban then immediate unban so the user can rejoin.
        await self._rpc({
            "_": "channels.editBanned",
            "channel": channel,
            "participant": user_peer,
            "banned_rights": {
                "_": "chatBannedRights",
                "until_date": 0,
                "view_messages": True,
            },
        })
        await self._rpc({
            "_": "channels.editBanned",
            "channel": channel,
            "participant": user_peer,
            "banned_rights": {"_": "chatBannedRights", "until_date": 0},
        })

    async def ban_participant(self, peer: str, user: str) -> None:
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        await self._rpc({
            "_": "channels.editBanned",
            "channel": channel,
            "participant": user_peer,
            "banned_rights": {
                "_": "chatBannedRights",
                "until_date": 0,
                "view_messages": True,
            },
        })

    async def ban_participant_until(self, peer: str, user: str, until_date: int) -> None:
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        await self._rpc({
            "_": "channels.editBanned",
            "channel": channel,
            "participant": user_peer,
            "banned_rights": {
                "_": "chatBannedRights",
                "until_date": until_date,
                "view_messages": True,
            },
        })

    _DEFAULT_ADMIN_RIGHTS = (
        "change_info", "post_messages", "edit_messages", "delete_messages",
        "ban_users", "invite_users", "pin_messages", "manage_call", "manage_topics",
    )

    async def promote_participant(self, peer: str, user: str, rights: list[str] | None = None, *, title: str = "") -> None:
        """Promote a user to admin.

        `rights` is now exact, not additive: pass e.g. `["delete_messages"]`
        for a limited admin with only that permission. Omit it for the
        previous default (full admin) behavior. Valid right names: change_info,
        post_messages, edit_messages, delete_messages, ban_users, invite_users,
        pin_messages, add_admins, anonymous, manage_call, other, manage_topics,
        post_stories, edit_stories, delete_stories, manage_direct_messages,
        manage_ranks, manage_linked_peers.
        """
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        chosen = rights if rights is not None else self._DEFAULT_ADMIN_RIGHTS
        admin_rights: dict = {"_": "chatAdminRights", **{r: True for r in chosen}}
        await self._rpc({
            "_": "channels.editAdmin",
            "channel": channel,
            "user_id": user_peer,
            "admin_rights": admin_rights,
            "rank": title,
        })

    async def demote_participant(self, peer: str, user: str) -> None:
        channel = await self._resolve_peer(peer)
        user_peer = await self._resolve_peer(user)
        await self._rpc({
            "_": "channels.editAdmin",
            "channel": channel,
            "user_id": user_peer,
            "admin_rights": {"_": "chatAdminRights"},
            "rank": "",
        })

    async def invite_users(self, peer: str, user_ids: list[int]) -> None:
        input_peer = await self._resolve_peer(peer)
        t = input_peer.get("_", "")
        if "Channel" in t:
            for uid in user_ids:
                user_peer = {"_": "inputUser", "user_id": uid, "access_hash": self._peer_cache.get_user(uid) or 0}
                await self._rpc({"_": "channels.inviteToChannel", "channel": input_peer, "users": [user_peer]})
        else:
            for uid in user_ids:
                await self._rpc({"_": "messages.addChatUser", "chat_id": input_peer.get("chat_id", 0), "user_id": uid, "fwd_limit": 0})

    async def edit_chat_default_banned_rights(self, peer: str, restrictions: dict[str, bool]) -> None:
        input_peer = await self._resolve_peer(peer)
        banned_rights = {"_": "chatBannedRights", "until_date": 0}
        banned_rights.update({k: not v for k, v in restrictions.items()})
        await self._rpc({"_": "messages.editChatDefaultBannedRights", "peer": input_peer, "banned_rights": banned_rights})

    async def transfer_chat_ownership(self, peer: str, new_owner_id: int,
                                      password: str | None = None) -> None:
        """Hand the chat over to another user. Telegram requires the account's 2FA password."""
        input_peer = await self._resolve_peer(peer)
        new_owner = {"_": "inputUser", "user_id": new_owner_id, "access_hash": self._peer_cache.get_user(new_owner_id) or 0}
        if password is None:
            srp: dict = {"_": "inputCheckPasswordEmpty"}
        else:
            srp = _srp_answer(await self._rpc({"_": "account.getPassword"}), password)
        await self._rpc({
            "_": "messages.editChatCreator",
            "peer": input_peer,
            "user_id": new_owner,
            "password": srp,
        })

    async def get_admins_with_invites(self, peer: str) -> list[tuple[int, int]]:
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({"_": "messages.getAdminsWithInvites", "peer": input_peer})
        admins = result.get("admins", []) if isinstance(result, dict) else []
        return [(a.get("admin_id", 0), a.get("invites_count", 0)) for a in admins]

    async def join_request(self, peer: str, user_id: int, approve: bool) -> None:
        input_peer = await self._resolve_peer(peer)
        ah = self._peer_cache.get_user(user_id) or 0
        user = {"_": "inputUser", "user_id": user_id, "access_hash": ah}
        if approve:
            await self._rpc({"_": "messages.hideChatJoinRequest", "peer": input_peer, "user_id": user, "approved": True})
        else:
            await self._rpc({"_": "messages.hideChatJoinRequest", "peer": input_peer, "user_id": user, "approved": False})

    async def all_join_requests(self, peer: str, approve: bool, link: str | None = None) -> None:
        input_peer = await self._resolve_peer(peer)
        req: dict = {"_": "messages.hideAllChatJoinRequests", "peer": input_peer, "approved": approve}
        if link:
            req["link"] = link
        await self._rpc(req)
