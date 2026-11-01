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


"""Dialog list, pinning, archiving and history deletion."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    pass


class DialogMethods:
    """Dialog list, pinning, archiving and history deletion."""

    async def get_dialogs(self, limit: int = 100) -> list[dict]:
        result = await self._rpc({
            "_": "messages.getDialogs",
            "offset_date": 0,
            "offset_id": 0,
            "offset_peer": {"_": "inputPeerEmpty"},
            "limit": limit,
            "hash": 0,
            "exclude_pinned": False,
        })
        if not isinstance(result, dict):
            return []
        self._populate_cache(result)
        dialogs = result.get("dialogs", []) or []
        chat_map = {c.get("id"): c for c in (result.get("chats") or []) if isinstance(c, dict) and c.get("id") is not None}
        for d in dialogs:
            if not isinstance(d, dict):
                continue
            # dialogCommunity has no `peer` field - it's addressed by
            # `community_id` instead, since there is no Peer::Community on
            # the wire. Attach the resolved chat under "chat" either way so
            # callers don't need to branch on the dialog's `_` type.
            if d.get("_") == "dialogCommunity":
                d["chat"] = chat_map.get(d.get("community_id"))
            else:
                peer = d.get("peer") or {}
                cid = peer.get("user_id") or peer.get("chat_id") or peer.get("channel_id")
                d["chat"] = chat_map.get(cid)
        return dialogs

    async def get_pinned_dialogs(self, folder_id: int = 0) -> list[int]:
        result = await self._rpc({"_": "messages.getPinnedDialogs", "folder_id": folder_id})
        dialogs = result.get("dialogs", []) if isinstance(result, dict) else []
        out = []
        for d in dialogs:
            if not isinstance(d, dict):
                continue
            if d.get("_") == "dialogCommunity":
                cid = d.get("community_id")
                if cid:
                    out.append(-(1_000_000_000 + cid))
                continue
            peer = d.get("peer", {})
            if isinstance(peer, dict):
                out.append(peer.get("user_id") or peer.get("chat_id") or peer.get("channel_id") or 0)
        return out

    async def archive_chat(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "folders.editPeerFolders",
            "folder_peers": [{"_": "inputFolderPeer", "peer": input_peer, "folder_id": 1}],
        })

    async def unarchive_chat(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({
            "_": "folders.editPeerFolders",
            "folder_peers": [{"_": "inputFolderPeer", "peer": input_peer, "folder_id": 0}],
        })

    async def pin_dialog(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.toggleDialogPin", "peer": {"_": "inputDialogPeer", "peer": input_peer}, "pinned": True})

    async def unpin_dialog(self, peer: str) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.toggleDialogPin", "peer": {"_": "inputDialogPeer", "peer": input_peer}, "pinned": False})

    async def delete_dialog(self, peer: str) -> None:
        await self.delete_chat_history(peer, max_id=0, revoke=False)

    async def delete_chat_history(self, peer: str, max_id: int = 0, revoke: bool = False) -> None:
        input_peer = await self._resolve_peer(peer)
        await self._rpc({"_": "messages.deleteHistory", "peer": input_peer, "max_id": max_id, "revoke": revoke})

    async def iter_dialogs(self, *, limit: int | None = None):
        fetch_limit = limit if limit is not None else 5000
        dialogs = await self.get_dialogs(fetch_limit)
        for d in dialogs:
            yield d
