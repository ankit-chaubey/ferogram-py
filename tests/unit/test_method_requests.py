# Requests built by Client methods: the right constructor, the right fields, and
# bytes the real serializer accepts. A fake transport records each request.

from __future__ import annotations

import asyncio
import importlib
import pathlib
import struct
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()

tl = importlib.import_module("ferogram.raw.tl")
SCHEMA = importlib.import_module("ferogram.raw.generated._tl_schema")._SCHEMA
participants = importlib.import_module("ferogram.methods.participants")
Client = importlib.import_module("ferogram.client").Client
types = importlib.import_module("ferogram.types")
keyboards = importlib.import_module("ferogram.keyboards")

CHANNEL = {"_": "inputPeerChannel", "channel_id": 5, "access_hash": 9}
USER = {"_": "inputPeerUser", "user_id": 3, "access_hash": 4}


def make_client(peer=CHANNEL):
    client = Client.__new__(Client)
    client.calls = []

    async def rpc(obj, **_kwargs):
        tl.serialize(obj, SCHEMA)          # must be encodable, like the real _rpc
        client.calls.append(obj)
        return {}

    async def resolve_peer(_peer):
        return peer

    client._rpc = rpc
    client._resolve_peer = resolve_peer
    client._peer_cache = SimpleNamespace(get_user=lambda _uid: 123)
    return client


def run(coro):
    return asyncio.run(coro)


def wire(obj):
    return tl.serialize(obj, SCHEMA)


# ---- forums -----------------------------------------------------------------

def test_toggle_forum_sends_an_input_channel():
    c = make_client()
    run(c.toggle_forum("x", True))
    req = c.calls[0]
    assert req["_"] == "channels.toggleForum"
    assert req["channel"] == {"_": "inputChannel", "channel_id": 5, "access_hash": 9}
    assert req["enabled"] is True and req["tabs"] is False


def test_toggle_forum_tabs_changes_the_bytes():
    c = make_client()
    run(c.toggle_forum("x", True))
    run(c.toggle_forum("x", True, tabs=True))
    assert wire(c.calls[0]) != wire(c.calls[1])


def test_toggle_forum_rejects_non_channels():
    with pytest.raises(ValueError, match="channel or supergroup"):
        run(make_client(USER).toggle_forum("x", True))


def test_forum_topic_requests_use_messages_namespace_with_a_peer():
    c = make_client()
    run(c.get_forum_topics("x", limit=7))
    run(c.create_forum_topic("x", "News", icon_color=1, icon_emoji_id=2))
    run(c.edit_forum_topic("x", 4, title="Renamed", closed=True, hidden=False))
    run(c.delete_forum_topic_history("x", 4))
    names = [r["_"] for r in c.calls]
    assert names == ["messages.getForumTopics", "messages.createForumTopic",
                     "messages.editForumTopic", "messages.deleteTopicHistory"]
    for req in c.calls:
        assert req["peer"] == CHANNEL and "channel" not in req
    assert c.calls[0]["limit"] == 7
    assert c.calls[1]["title"] == "News" and c.calls[1]["icon_color"] == 1
    assert c.calls[2]["closed"] is True and c.calls[2]["hidden"] is False
    assert c.calls[3]["top_msg_id"] == 4


# ---- ownership transfer -------------------------------------------------------

def test_transfer_ownership_uses_edit_chat_creator():
    c = make_client()
    run(c.transfer_chat_ownership("x", 77))
    req = c.calls[0]
    assert req["_"] == "messages.editChatCreator"
    assert req["peer"] == CHANNEL
    assert req["user_id"] == {"_": "inputUser", "user_id": 77, "access_hash": 123}
    assert req["password"] == {"_": "inputCheckPasswordEmpty"}


def test_transfer_ownership_with_password_fetches_srp(monkeypatch):
    srp = {"_": "inputCheckPasswordSRP", "srp_id": 1, "A": b"a", "M1": b"m"}
    seen = {}

    def fake_srp(info, password):
        seen["password"] = password
        return srp

    monkeypatch.setattr(participants, "_srp_answer", fake_srp)
    c = make_client()
    run(c.transfer_chat_ownership("x", 77, password="hunter2"))
    assert [r["_"] for r in c.calls] == ["account.getPassword", "messages.editChatCreator"]
    assert c.calls[1]["password"] == srp
    assert seen["password"] == "hunter2"


# ---- inline queries -------------------------------------------------------------

def _without(req, key):
    return {k: v for k, v in req.items() if k != key}


def test_is_personal_maps_to_the_private_flag():
    c = make_client()
    run(c.answer_inline_query_articles(1, [("T", "D", "body")], is_personal=False))
    run(c.answer_inline_query_articles(1, [("T", "D", "body")], is_personal=True))
    off, on = c.calls
    assert "is_personal" not in off and "is_personal" not in on
    assert wire(off) == wire(_without(off, "private"))      # False means absent
    assert wire(on) != wire(off)


def test_answer_inline_query_with_article_dataclass():
    c = make_client()
    kb = keyboards.InlineKeyboard()
    kb.add_row([keyboards.InlineButton.url("open", "https://example.com")])
    article = types.InlineArticle(id="a1", title="Title", message_text="Body", description="Desc",
                                  url="https://example.com", thumb_url="https://example.com/t.jpg",
                                  reply_markup=kb)
    run(c.answer_inline_query(9, [article], next_offset="2"))
    req = c.calls[0]
    assert req["_"] == "messages.setInlineBotResults" and req["query_id"] == 9
    assert req["next_offset"] == "2"
    result = req["results"][0]
    assert result["_"] == "inputBotInlineResult" and result["type"] == "article"
    assert (result["id"], result["title"], result["description"]) == ("a1", "Title", "Desc")
    assert result["url"] == "https://example.com"
    assert result["thumb"]["_"] == "inputWebDocument"
    assert result["send_message"]["message"] == "Body"
    assert result["send_message"]["reply_markup"]["_"] == "replyInlineMarkup"


def test_answer_inline_query_with_short_tuple():
    c = make_client()
    run(c.answer_inline_query(9, [("article", 3, "T", "D", "body")]))
    result = c.calls[0]["results"][0]
    assert result["id"] == "3" and result["title"] == "T" and result["description"] == "D"
    assert result["send_message"]["message"] == "body"


def test_photo_result_is_url_based_and_sent_as_media():
    c = make_client()
    photo = types.InlinePhoto(id="p1", title="T", message_text="caption", photo_url="https://x/y.jpg",
                              photo_width=640, photo_height=480, description="D")
    run(c.answer_inline_query(9, [photo]))
    result = c.calls[0]["results"][0]
    assert result["type"] == "photo" and result["description"] == "D"
    assert result["content"] == {
        "_": "inputWebDocument", "url": "https://x/y.jpg", "size": 0, "mime_type": "image/jpeg",
        "attributes": [{"_": "documentAttributeImageSize", "w": 640, "h": 480}],
    }
    assert result["thumb"]["url"] == "https://x/y.jpg"          # falls back to the photo itself
    assert result["send_message"] == {"_": "inputBotInlineMessageMediaAuto", "message": "caption"}


def test_photo_result_without_size_has_no_size_attribute():
    c = make_client()
    photo = types.InlinePhoto(id="p", title="T", message_text="", photo_url="https://x/y.jpg",
                              thumb_url="https://x/t.jpg")
    run(c.answer_inline_query(9, [photo]))
    result = c.calls[0]["results"][0]
    assert result["content"]["attributes"] == []
    assert result["thumb"]["url"] == "https://x/t.jpg"


def test_document_result_is_a_file_with_its_mime_type():
    c = make_client()
    kb = keyboards.InlineKeyboard()
    kb.add_row([keyboards.InlineButton.url("open", "https://example.com")])
    doc = types.InlineDocument(id="d1", title="Report", message_text="here", document_url="https://x/r.pdf",
                               mime_type="application/pdf", reply_markup=kb)
    run(c.answer_inline_query(9, [doc]))
    result = c.calls[0]["results"][0]
    assert result["type"] == "file"
    assert result["content"]["url"] == "https://x/r.pdf"
    assert result["content"]["mime_type"] == "application/pdf"
    assert "thumb" not in result
    assert result["send_message"]["_"] == "inputBotInlineMessageMediaAuto"
    assert result["send_message"]["reply_markup"]["_"] == "replyInlineMarkup"


def test_mixed_result_kinds_in_one_answer():
    c = make_client()
    results = [types.InlineArticle(id="a", title="A", message_text="a"),
               types.InlinePhoto(id="p", title="P", message_text="", photo_url="https://x/y.jpg"),
               types.InlineDocument(id="d", title="D", message_text="", document_url="https://x/d.zip",
                                    mime_type="application/zip")]
    run(c.answer_inline_query(9, results))
    assert [r["type"] for r in c.calls[0]["results"]] == ["article", "photo", "file"]


def test_unknown_inline_result_kind_fails_clearly():
    c = make_client()
    with pytest.raises(ValueError, match="unknown inline result kind"):
        run(c.answer_inline_query(9, [("sticker", "1", "t", "m", "d", None, None, None, 0, 0, None, None)]))
    with pytest.raises(ValueError, match="5 or 12"):
        run(c.answer_inline_query(9, [("article", "1")]))


# ---- editing inline messages -------------------------------------------------

def test_edit_inline_message_accepts_the_dict_from_updates():
    c = make_client()
    raw = {"_": "inputBotInlineMessageID64", "dc_id": 2, "owner_id": 5, "id": 6, "access_hash": 7}
    run(c.edit_inline_message(raw, "new"))
    assert c.calls[0]["_"] == "messages.editInlineBotMessage"
    assert c.calls[0]["id"] == raw


def test_edit_inline_message_decodes_64_bit_ids():
    c = make_client()
    run(c.edit_inline_message(types.InlineMessageId(2, struct.pack("<qiq", 11, 22, 33)), "t"))
    assert c.calls[0]["id"] == {"_": "inputBotInlineMessageID64", "dc_id": 2,
                                "owner_id": 11, "id": 22, "access_hash": 33}


def test_edit_inline_message_decodes_old_ids():
    c = make_client()
    run(c.edit_inline_message((3, struct.pack("<qq", 44, 55)), "t"))
    assert c.calls[0]["id"] == {"_": "inputBotInlineMessageID", "dc_id": 3, "id": 44, "access_hash": 55}


def test_edit_inline_message_rejects_bad_ids():
    c = make_client()
    with pytest.raises(ValueError, match="16 or 20"):
        run(c.edit_inline_message((2, b"short"), "t"))
    with pytest.raises(ValueError, match="not an inline message id"):
        run(c.edit_inline_message({"_": "inputPeerSelf"}, "t"))


# ---- polls --------------------------------------------------------------------

def test_send_poll_fills_the_required_poll_fields():
    c = make_client()
    run(c.send_poll("x", "Q?", ["a", "b"], quiz=True, correct_index=1,
                    shuffle_answers=True, hide_results_until_close=True))
    req = c.calls[0]
    assert req["_"] == "messages.sendMedia"
    poll = req["media"]["poll"]
    assert poll["hash"] == 0
    assert poll["quiz"] is True
    assert poll["shuffle_answers"] is True and poll["hide_results_until_close"] is True
    assert req["media"]["correct_answers"] == [1]


def test_multiple_choice_is_ignored_for_quizzes():
    c = make_client()
    run(c.send_poll("x", "Q?", ["a", "b"], quiz=True, correct_index=0, multiple_choice=True))
    run(c.send_poll("x", "Q?", ["a", "b"], multiple_choice=True))
    assert c.calls[0]["media"]["poll"]["multiple_choice"] is False
    assert c.calls[1]["media"]["poll"]["multiple_choice"] is True


def test_send_poll_options_that_are_off_are_not_sent():
    c = make_client()
    run(c.send_poll("x", "Q?", ["a", "b"]))
    poll = c.calls[0]["media"]["poll"]
    assert wire(poll) == wire({k: v for k, v in poll.items()
                               if k not in ("shuffle_answers", "hide_results_until_close",
                                            "quiz", "multiple_choice", "public_voters")})


def test_get_poll_results_forwards_the_hash():
    c = make_client()
    run(c.get_poll_results("x", 5))
    run(c.get_poll_results("x", 5, poll_hash=99))
    assert c.calls[0]["poll_hash"] == 0
    assert c.calls[1]["poll_hash"] == 99


def test_get_poll_stats_uses_the_current_public_forwards_request():
    c = make_client()
    run(c.get_poll_stats("x", 5))
    req = c.calls[0]
    assert req["_"] == "stats.getMessagePublicForwards"
    assert req["channel"]["_"] == "inputChannel"
    assert req["offset"] == "" and req["limit"] == 100
    with pytest.raises(ValueError, match="channel or supergroup"):
        run(make_client(USER).get_poll_stats("x", 5))


# ---- peers in typed fields ------------------------------------------------------

def test_methods_that_pass_a_raw_peer_still_put_an_input_channel_on_the_wire():
    # leave_chat hands the resolved peer to channels.leaveChannel as is; the serializer
    # must send the constructor the field's type requires.
    c = make_client()
    run(c.leave_chat("x"))
    sent = c.calls[0]
    assert sent["_"] == "channels.leaveChannel"
    correct = {**sent, "channel": {"_": "inputChannel", "channel_id": 5, "access_hash": 9}}
    assert wire(sent) == wire(correct)
    assert struct.unpack("<I", wire(sent)[4:8])[0] == 0xF35AEC28
