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


"""Invite links."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._internal import (
    _extract_invite_hash,
)

if TYPE_CHECKING:
    pass


class InviteMethods:
    """Invite links."""

    async def invite_links(self, peer: str, *, primary_only: bool = False, revoked: bool = False, limit: int = 100):
        input_peer = await self._resolve_peer(peer)
        if primary_only:
            return await self._rpc({"_": "messages.exportChatInvite", "peer": input_peer})
        me = await self.get_me()
        return await self._rpc({
            "_": "messages.getExportedChatInvites",
            "peer": input_peer,
            "admin_id": {"_": "inputUser", "user_id": me.get("id", 0), "access_hash": self._peer_cache.get_user(me.get("id", 0)) or 0},
            "revoked": revoked,
            "limit": limit,
        })

    async def iter_invite_links(self, peer: str, *, revoked: bool = False):
        result = await self.invite_links(peer, revoked=revoked, limit=100)
        invites = result.get("invites", []) if isinstance(result, dict) else []
        for link in invites:
            yield link

    async def iter_invite_link_members(self, peer: str, link: str, *, requested: bool = False):
        input_peer = await self._resolve_peer(peer)
        result = await self._rpc({
            "_": "messages.getChatInviteImporters",
            "peer": input_peer,
            "link": link,
            "requested": requested,
            "offset_date": 0,
            "offset_user": {"_": "inputUserEmpty"},
            "limit": 100,
        })
        importers = result.get("importers", []) if isinstance(result, dict) else []
        for m in importers:
            yield m

    async def edit_invite_link(self, peer: str, link: str, *, expire_date: int | None = None,
                                usage_limit: int | None = None, request_needed: bool | None = None,
                                title: str | None = None):
        input_peer = await self._resolve_peer(peer)
        req: dict = {"_": "messages.editExportedChatInvite", "peer": input_peer, "link": link}
        if expire_date is not None:
            req["expire_date"] = expire_date
        if usage_limit is not None:
            req["usage_limit"] = usage_limit
        if request_needed is not None:
            req["request_needed"] = request_needed
        if title is not None:
            req["title"] = title
        return await self._rpc(req)

    async def revoke_invite_link(self, peer: str, link: str):
        input_peer = await self._resolve_peer(peer)
        return await self._rpc({"_": "messages.editExportedChatInvite", "peer": input_peer, "link": link, "revoked": True})

    async def delete_invite_link(self, peer: str, link: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.deleteExportedChatInvite", "peer": input_peer, "link": link})

    async def clear_revoked_invite_links(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        me = await self.get_me()
        ah = self._peer_cache.get_user(me.get("id", 0)) or 0
        await self._rpc({
            "_": "messages.deleteRevokedExportedChatInvites",
            "peer": input_peer,
            "admin_id": {"_": "inputUser", "user_id": me.get("id", 0), "access_hash": ah},
        })

    async def resolve_invite_link(self, link: str):
        return await self._rpc({"_": "messages.checkChatInvite", "hash": _extract_invite_hash(link)})

    async def join_invite_link(self, link: str) -> dict:
        """Import a chat invite link.

        Returns the raw `messages.ChatInviteJoinResult` dict as-is - either
        `messages.chatInviteJoinResultOk` (`{"updates": ...}`) or
        `messages.chatInviteJoinResultWebView` (`{"bot_id", "query_id",
        "users"}`, no Updates - join isn't complete without driving that bot
        flow). Use `join_chat()` for a version that resolves this down to an
        InputPeer or None.
        """
        result = await self._rpc({"_": "messages.importChatInvite", "hash": _extract_invite_hash(link)})
        if isinstance(result, dict) and result.get("_") == "messages.chatInviteJoinResultOk":
            self._populate_cache(result.get("updates") or {})
        return result
