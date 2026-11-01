# High-level wrappers built from raw TL dicts.

from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()

from ferogram import types as T  # noqa: E402


def test_peer_to_id_users_chats_and_channels():
    assert T._peer_to_id({"_": "peerUser", "user_id": 42}) == 42
    assert T._peer_to_id({"_": "peerChat", "chat_id": 9}) == -9
    channel = T._peer_to_id({"_": "peerChannel", "channel_id": 123})
    assert channel < 0
    # users, chats and channels never collide for the same numeric id
    assert len({T._peer_to_id({"_": "peerUser", "user_id": 5}),
                T._peer_to_id({"_": "peerChat", "chat_id": 5}),
                T._peer_to_id({"_": "peerChannel", "channel_id": 5})}) == 3


def test_peer_to_id_handles_missing_and_empty_values():
    assert T._peer_to_id(None) is None
    assert T._peer_to_id({}) is None
    assert T._peer_to_id("not a peer") is None
    assert T._peer_to_id({"_": "peerUser", "user_id": 0}) is None


def test_scalar_helpers_coerce_missing_values():
    assert T._int({}, "x") == 0
    assert T._int({"x": None}, "x", 5) == 5
    assert T._int({"x": "7"}, "x") == 7
    assert T._str({}, "x") == ""
    assert T._str({"x": 3}, "x") == "3"
    assert T._bool({}, "x") is False
    assert T._bool({"x": True}, "x") is True


def test_user_from_tl():
    u = T.User.from_tl({
        "_": "user", "id": 11, "first_name": "Ada", "last_name": "Lovelace",
        "username": "ada", "bot": True, "premium": True, "access_hash": 99,
    })
    assert u.id == 11
    assert u.full_name == "Ada Lovelace"
    assert u.username == "ada"
    assert u.is_bot and u.is_premium and not u.is_verified
    assert u.access_hash == 99


def test_user_full_name_without_last_name():
    u = T.User.from_tl({"id": 1, "first_name": "Ada"})
    assert u.full_name == "Ada"
    assert u.username is None


def test_user_username_falls_back_to_usernames_list():
    u = T.User.from_tl({"id": 1, "usernames": [{"username": "alt", "active": True}]})
    assert u.username == "alt"


def test_chat_kinds():
    channel = T.Chat.from_tl({"_": "channel", "id": 1, "title": "News", "broadcast": True})
    mega = T.Chat.from_tl({"_": "channel", "id": 2, "title": "Chat", "megagroup": True})
    basic = T.Chat.from_tl({"_": "chat", "id": 3, "title": "Small"})
    assert channel.is_channel and channel.is_broadcast and not channel.is_megagroup
    assert mega.is_channel and mega.is_megagroup
    assert not basic.is_channel and not basic.is_community
    assert repr(basic) == "Chat(id=3, title='Small')"


def test_message_from_tl():
    m = T.Message.from_tl({
        "_": "message", "id": 5, "message": "hello", "date": 1700000000,
        "peer_id": {"_": "peerUser", "user_id": 77},
        "from_id": {"_": "peerUser", "user_id": 77},
        "reply_to": {"_": "messageReplyHeader", "reply_to_msg_id": 4},
        "out": True, "silent": True,
    })
    assert (m.id, m.text, m.date) == (5, "hello", 1700000000)
    assert m.sender_id == 77
    assert m.chat_id == 77
    assert m.reply_to_msg_id == 4
    assert m.out and m.silent and not m.pinned and not m.mentioned
    assert m.forward_from_id is None


def test_message_from_tl_tolerates_sparse_input():
    m = T.Message.from_tl({"_": "message", "id": 1})
    assert m.text == ""
    assert m.chat_id == 0
    assert m.entities == []
    assert m.reply_to_msg_id is None


def test_message_methods_need_a_bound_client():
    m = T.Message.from_tl({"_": "message", "id": 1, "peer_id": {"_": "peerUser", "user_id": 2}})
    with pytest.raises(RuntimeError, match="isn't bound to a client"):
        asyncio.run(m.reply("hi"))


def test_message_reply_and_respond_route_through_client():
    calls = []

    class FakeClient:
        async def send_message(self, chat_id, text, **kwargs):
            calls.append((chat_id, text, kwargs))

    m = T.Message.from_tl({"_": "message", "id": 9, "peer_id": {"_": "peerUser", "user_id": 2}})
    m._client = FakeClient()
    asyncio.run(m.reply("quoted"))
    asyncio.run(m.respond("plain"))
    assert calls[0][:2] == (2, "quoted")
    assert calls[0][2]["reply_to"] == 9
    assert calls[1][:2] == (2, "plain")
    assert "reply_to" not in calls[1][2]
