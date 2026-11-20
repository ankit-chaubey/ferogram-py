from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
import os
import pathlib
import struct
import sys
import tempfile
import tracemalloc
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()

tl = importlib.import_module("ferogram.raw.tl")
schema = importlib.import_module("ferogram.raw.generated._tl_schema")
types = importlib.import_module("ferogram.raw.generated.types")
functions = importlib.import_module("ferogram.raw.generated.functions")
errors = importlib.import_module("ferogram.errors")
filters = importlib.import_module("ferogram.filters")
keyboards = importlib.import_module("ferogram.keyboards")
updates = importlib.import_module("ferogram.updates")
proxy = importlib.import_module("ferogram.raw.proxy")
media = importlib.import_module("ferogram.methods.media")
from ferogram.client import Client  # noqa: E402

SCHEMA = schema._SCHEMA
BY_CID = schema._SCHEMA_BY_CID
PEER = {"_": "inputPeerUser", "user_id": 1, "access_hash": 2}


def run(coro):
    return asyncio.run(coro)


def make_client():
    c = Client.__new__(Client)
    c._log = logging.getLogger("ferogram-test")
    c._migrate_lock = asyncio.Lock()
    c._dropped_updates = 0
    c._diff_failures = 0
    c._me_username = None
    c._seen_entities = set()
    c._event_by_cid = {}
    c._handlers = {}
    return c


def test_vector_long_items_are_eight_bytes():
    assert len(functions.messages.GetChats(id=[1, 2]).to_bytes()) == 4 + 4 + 4 + 16
    assert len(functions.contacts.EditCloseFriends(id=[111, 222]).to_bytes()) == 4 + 4 + 4 + 16
    assert len(tl._serialize_field([1, 2, 3], "Vector<long>", SCHEMA)) == 4 + 4 + 24
    wire = tl.serialize_object({"_": "messages.getChats", "id": [1, 2]}, SCHEMA)
    assert wire == functions.messages.GetChats(id=[1, 2]).to_bytes()


def test_int_vector_overflow_raises():
    with pytest.raises(Exception):
        tl.serialize_object({"_": "messages.deleteMessages", "id": [2**31], "revoke": True}, SCHEMA)
    with pytest.raises(Exception):
        functions.messages.DeleteMessages(id=[2**31], revoke=True).to_bytes()


def test_missing_required_and_unknown_fields_raise():
    base = {"_": "messages.sendMessage", "peer": PEER, "random_id": 5}
    with pytest.raises(tl.TLEncodeError, match="message"):
        tl.serialize_object(base, SCHEMA)
    with pytest.raises(tl.TLEncodeError, match="silnt"):
        tl.serialize_object(dict(base, message="hi", silnt=True), SCHEMA)
    assert len(tl.serialize_object(dict(base, message="hi"), SCHEMA)) == 40


def test_filter_constructors_carry_required_fields():
    for name in ("channelParticipantsKicked", "channelParticipantsContacts"):
        assert len(tl.serialize_object({"_": name, "q": ""}, SCHEMA)) == 8
        with pytest.raises(tl.TLEncodeError):
            tl.serialize_object({"_": name}, SCHEMA)


def test_reader_rejects_malformed_input():
    with pytest.raises(tl.TLDecodeError):
        tl._read_bytes(bytes([10]) + b"abc", 0)
    with pytest.raises(tl.TLDecodeError):
        tl._read_bytes(b"", 0)
    wire = types.UpdateShortMessage(id=1, user_id=2, message="hello world", pts=1, pts_count=1, date=3).to_bytes()
    for cut in range(5, len(wire)):
        with pytest.raises(tl.TLDecodeError):
            tl.deserialize(wire[:cut], BY_CID)
    huge = struct.pack("<II", 0x1cb5c415, 0xFFFFFFFF)
    with pytest.raises(tl.TLDecodeError):
        tl.deserialize(huge, BY_CID)


def test_unknown_constructor_handling():
    top = tl.deserialize(struct.pack("<I", 0xDEADBEEF) + b"\x01\x02\x03\x04", BY_CID)
    assert top["_cid"] == "0xdeadbeef" and top["_raw"] == b"\x01\x02\x03\x04"
    nested = struct.pack("<II", 0x1cb5c415, 1) + struct.pack("<I", 0xDEADBEEF) + b"\x00" * 8
    with pytest.raises(tl.TLDecodeError, match="unknown constructor"):
        tl.deserialize(nested, BY_CID)


def test_invalid_utf8_string_stays_a_string():
    wire = types.UpdateShortMessage(id=1, user_id=2, message="aaaa", pts=1, pts_count=1, date=3).to_bytes()
    wire = wire.replace(b"aaaa", b"\xff\xfe\xfd\xfc")
    assert isinstance(tl.deserialize(wire, BY_CID)["message"], str)


def test_oversized_bytes_value_raises():
    with pytest.raises(tl.TLEncodeError):
        tl._pack_bytes(b"x" * (1 << 24))
    assert len(tl._pack_bytes(b"x" * ((1 << 24) - 1))) >= (1 << 24)


def test_markdown_offsets_are_utf16_units():
    text, ents = tl.parse_markdown("\U0001F600 **bold**")
    assert text == "\U0001F600 bold"
    assert (ents[0]["offset"], ents[0]["length"]) == (3, 4)
    _, ents = tl.parse_markdown("**\U0001F600 hi**")
    assert (ents[0]["offset"], ents[0]["length"]) == (0, 5)


def test_html_offsets_use_unescaped_utf16_text():
    text, ents = tl.parse_html("&amp;lt; <b>x</b>")
    assert text == "&lt; x"
    assert (ents[0]["offset"], ents[0]["length"]) == (5, 1)
    text, ents = tl.parse_html("&#128512; <i>e</i>")
    assert text == "\U0001F600 e"
    assert (ents[0]["offset"], ents[0]["length"]) == (3, 1)
    text, ents = tl.parse_html("\U0001F600<b>x</b>")
    assert ents[0]["offset"] == 2


def test_rpc_error_parsing():
    flood = errors.RpcError.from_runtime(RuntimeError("rpc error 420 FLOOD_WAIT_30 (value: 30)"))
    assert isinstance(flood, errors.FloodWait) and flood.seconds == 30 and flood.code == 420
    other = errors.RpcError.from_runtime(RuntimeError("400 PEER_ID_INVALID"))
    assert isinstance(other, errors.RpcError) and other.name == "PEER_ID_INVALID" and other.code == 400
    assert isinstance(other, RuntimeError)
    plain = RuntimeError("socket closed")
    assert errors.RpcError.from_runtime(plain) is plain


class FakeRpcConn:
    def __init__(self, err=None, resp=b""):
        self.err, self.resp, self.calls = err, resp, 0

    async def rpc_call(self, b):
        self.calls += 1
        if self.err:
            raise RuntimeError(self.err)
        return self.resp


def test_redirect_loop_is_capped_and_migration_is_serialized():
    c = make_client()
    migrations = []

    async def migrate(dc, reason=""):
        migrations.append(dc)
        await asyncio.sleep(0.01)
        c._conn = FakeRpcConn(err="rpc error 303 NETWORK_MIGRATE_3 (value: 3)")

    c._migrate = migrate
    c._populate_cache = lambda r: None
    c._conn = FakeRpcConn(err="rpc error 303 NETWORK_MIGRATE_3 (value: 3)")

    async def go():
        with pytest.raises(errors.RpcError):
            await c._rpc({"_": "help.getConfig"})

    run(go())
    assert len(migrations) <= 3

    c2 = make_client()
    ok = types.UpdateShortSentMessage(id=1, pts=1, pts_count=1, date=1).to_bytes()
    seen = []

    async def migrate2(dc, reason=""):
        seen.append(dc)
        await asyncio.sleep(0.01)
        c2._conn = FakeRpcConn(resp=ok)

    c2._migrate = migrate2
    c2._populate_cache = lambda r: None
    c2._conn = FakeRpcConn(err="rpc error 303 FILE_MIGRATE_4 (value: 4)")

    async def go2():
        await asyncio.gather(*[c2._rpc({"_": "help.getConfig"}) for _ in range(3)])

    run(go2())
    assert seen == [4]


def good_update(i):
    m = types.Message(id=i, peer_id=types.PeerUser(user_id=1), from_id=types.PeerUser(user_id=1), date=1, message=f"hello {i}")
    return types.UpdateNewMessage(message=m, pts=i, pts_count=1).to_bytes()


def test_bad_update_does_not_abort_the_batch():
    c = make_client()
    c._handlers = {"message": {0: [(lambda cl, m: None, [])]}}
    c._populate_cache = lambda r: None
    got = []

    async def enqueue(item):
        got.append(item[1].id)

    c._enqueue_update = enqueue
    run(c._dispatch_raw_batch([good_update(1), good_update(2)[:30], good_update(3)], [], []))
    assert got == [1, 3]


def test_dropped_updates_are_counted_and_logged():
    c = make_client()
    c.update_overflow = "drop_oldest"
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    c._log.addHandler(handler)
    c._log.setLevel(logging.DEBUG)

    async def go():
        c._update_queue = asyncio.Queue(maxsize=2)
        for i in range(5):
            await c._enqueue_update(("message", i))

    run(go())
    c._log.removeHandler(handler)
    assert c._dropped_updates == 3
    assert any("dropped" in r.getMessage() for r in records)


def test_routing_of_short_and_previously_unrouted_updates():
    c = make_client()
    kind, ev = c._route_update({"_": "updateShortMessage", "id": 1, "user_id": 2, "message": "hi", "pts": 1, "pts_count": 1, "date": 1})
    msg = updates.wrap_update(kind, ev).message
    assert kind == "message" and msg.text == "hi" and msg.chat_id == 2
    kind, ev = c._route_update({"_": "updateShortChatMessage", "id": 1, "from_id": 3, "chat_id": 9, "message": "yo", "pts": 1, "pts_count": 1, "date": 1})
    assert updates.wrap_update(kind, ev).message.chat_id == -9
    assert c._route_update({"_": "updateDeleteChannelMessages", "channel_id": 5, "messages": [1], "pts": 1, "pts_count": 1})[0] == "message_deleted"
    kind, ev = c._route_update({"_": "updateBotChatInviteRequester", "peer": {"_": "peerChannel", "channel_id": 7}, "date": 1, "user_id": 2, "about": "", "invite": {}, "qts": 1})
    jr = updates.wrap_update(kind, ev)
    assert kind == "join_request" and jr.channel_id == 7 and jr.user_id == 2
    assert c._route_update({"_": "updateBotMessageReaction"})[0] == "message_reaction"
    assert "updateBotJoinRequest" not in Client._SIMPLE_ROUTE_MAP


def test_inline_callback_query_does_not_crash():
    q = updates.CallbackQuery.from_tl({"_": "updateInlineBotCallbackQuery", "query_id": 1, "user_id": 2,
                                        "msg_id": {"_": "inputBotInlineMessageID", "dc_id": 2, "id": 5, "access_hash": 7},
                                        "chat_instance": 1, "data": b"x"})
    assert q.message_id == 0 and q.inline_message_id["id"] == 5
    plain = updates.CallbackQuery.from_tl({"_": "updateBotCallbackQuery", "query_id": 1, "user_id": 2, "peer": {"_": "peerUser", "user_id": 2}, "msg_id": 8, "chat_instance": 1})
    assert plain.message_id == 8 and plain.inline_message_id is None


class FakePeerClient:
    def __init__(self):
        self._peer_cache = proxy.PeerCache()
        self.calls = []

    async def invoke(self, req):
        self.calls.append(req)
        return {"chats": []}


def test_bot_api_channel_ids_resolve_and_miss_uses_channel_method():
    c = FakePeerClient()
    c._peer_cache.store_chat_entity({"_": "channel", "id": 1234567890, "access_hash": 99})
    expected = {"_": "inputPeerChannel", "channel_id": 1234567890, "access_hash": 99}
    assert run(proxy.resolve_peer(c, -1001234567890)) == expected
    assert run(proxy.resolve_peer(c, -2234567890)) == expected
    c2 = FakePeerClient()
    with pytest.raises(ValueError):
        run(proxy.resolve_peer(c2, -1009999999999))
    assert c2.calls[0]["_"] == "channels.getChannels"
    assert c2.calls[0]["id"][0]["channel_id"] == 9999999999


def test_filters_respect_bot_username_and_channel_posts():
    cmd = filters.command("start")
    other = NS(text="/start@OtherBot", chat_id=-5, sender_id=7, _client=NS(_me_username="mybot"))
    mine = NS(text="/start@MyBot x", chat_id=-5, sender_id=7, _client=NS(_me_username="mybot"))
    unknown = NS(text="/start@AnyBot", chat_id=-5, sender_id=7, _client=NS(_me_username=None))
    assert not cmd(other) and cmd(mine) and cmd(unknown)
    post = NS(text="x", chat_id=-1000000005, sender_id=None, peer_id={"_": "peerChannel", "channel_id": 5}, _raw={"post": True})
    supergroup = NS(text="x", chat_id=-1000000005, sender_id=7, peer_id={"_": "peerChannel", "channel_id": 5}, _raw={})
    assert filters.channel(post) and not filters.group(post)
    assert filters.group(supergroup) and not filters.channel(supergroup)


def test_keyboard_limits():
    with pytest.raises(ValueError):
        keyboards.InlineButton.callback("x", b"a" * 65)
    assert keyboards.InlineButton.callback("x", "abc").to_dict()["type"]["data"] == b"abc"
    kb = keyboards.InlineKeyboard()
    with pytest.raises(ValueError):
        kb.add_row([keyboards.InlineButton.callback("b", b"d")] * 9)
    for _ in range(12):
        kb.add_row([keyboards.InlineButton.callback("b", b"d")] * 8)
    with pytest.raises(ValueError):
        kb.add_row([keyboards.InlineButton.callback("b", b"d")] * 8)


def test_upload_part_sizes_are_valid_for_telegram():
    for size in (1, 10**6, 10**8, 1500 * 1024**2, 2 * 1024**3, int(3.5 * 1024**3), 4000 * 1024**2):
        ps, parts = Client._upload_part_size(size)
        assert ps % 1024 == 0 and 524288 % ps == 0 and ps * parts >= size and parts <= 8000
    with pytest.raises(ValueError):
        Client._upload_part_size(5 * 1024**3)


def _mime(head, name):
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "wb") as fh:
        fh.write(head + b"\0" * 64)
    return Client._detect_mime(path)


def test_mime_detection():
    assert _mime(b"OggS", "v.ogg") == "audio/ogg"
    assert _mime(b"\0\0\0\x20ftypM4A ", "a.m4a") == "audio/mp4"
    assert _mime(b"\0\0\0\x14ftypqt  ", "a.mov") == "video/quicktime"
    assert _mime(b"\0\0\0\x18ftypmp42", "a.mp4") == "video/mp4"
    assert _mime(b"RIFF\0\0\0\0AVI ", "a.avi") == "video/x-msvideo"
    assert _mime(b"RIFF\0\0\0\0WAVE", "a.wav") == "audio/wav"
    assert _mime(b"RIFF\0\0\0\0WEBPVP8 ", "a.webp") == "image/webp"
    assert _mime(b"\x1aE\xdf\xa3", "a.webm") == "video/webm"


CHUNK = 256 * 1024


class _Req:
    def __init__(self, b):
        self.b = b

    async def wait(self):
        return self.b


class _Sender:
    def __init__(self, conn):
        self.conn = conn

    async def enqueue(self, rb):
        return _Req(await self.conn.rpc_call(rb))

    async def call(self, rb):
        return await self.conn.rpc_call(rb)

    def is_alive(self):
        return True


class WorkerConn:
    def __init__(self, total, empty=(), short=()):
        self.total, self.empty, self.short = total, set(empty), set(short)

    async def into_pipelined_sender(self):
        return _Sender(self)

    async def rpc_call(self, rb):
        offset = struct.unpack_from("<q", rb, len(rb) - 12)[0]
        idx = offset // CHUNK
        n = min(CHUNK, self.total - offset)
        if idx in self.empty:
            data = b""
        elif idx in self.short:
            data = bytes([idx % 251]) * (n // 2)
        else:
            data = bytes([idx % 251]) * n
        return types.upload.File(type=types.storage.FileUnknown(), mtime=0, bytes=data).to_bytes()


def _download(total, **kw):
    c = Client(api_id=1, api_hash="x" * 32)
    c._dc_id = 2
    c._log = logging.getLogger("ferogram-test")

    @contextlib.asynccontextmanager
    async def slot(dc):
        yield WorkerConn(total, **kw)

    c._worker_slot = slot
    c._require_conn = lambda: WorkerConn(total, **kw)
    doc = {"_": "document", "id": 1, "access_hash": 2, "file_reference": b"", "size": total, "dc_id": 2}
    path = os.path.join(tempfile.mkdtemp(), "out.bin")
    tracemalloc.start()
    try:
        run(c._download_media_object({"_": "messageMediaDocument", "document": doc}, path))
        error = None
    except RuntimeError as e:
        error = e
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return path, peak, error


def _expected(total):
    out = bytearray()
    for idx in range((total + CHUNK - 1) // CHUNK):
        out += bytes([idx % 251]) * min(CHUNK, total - idx * CHUNK)
    return bytes(out)


def test_parallel_download_is_exact_and_streams_to_disk():
    total = 40 * 1024 * 1024 + 12345
    path, peak, error = _download(total)
    assert error is None
    with open(path, "rb") as fh:
        assert fh.read() == _expected(total)
    assert peak < total // 2
    assert not os.path.exists(path + ".part")


def test_parallel_download_rejects_empty_and_short_parts():
    total = 40 * 1024 * 1024
    for kw in ({"empty": [7]}, {"short": [9]}):
        path, _, error = _download(total, **kw)
        assert isinstance(error, RuntimeError)
        assert not os.path.exists(path) and not os.path.exists(path + ".part")


def test_sequential_download_detects_truncation():
    total = 3 * CHUNK
    path, _, error = _download(total)
    assert error is None and os.path.getsize(path) == total
    path, _, error = _download(total, empty=[1])
    assert isinstance(error, RuntimeError)
    assert not os.path.exists(path) and not os.path.exists(path + ".part")


def test_photo_download_uses_largest_progressive_size():
    sizes = [
        {"_": "photoSize", "type": "m", "size": 5000},
        {"_": "photoSizeProgressive", "type": "y", "sizes": [1000, 5000, 20000]},
        {"_": "photoStrippedSize", "type": "i", "bytes": b"x"},
    ]
    assert media._photo_size_bytes(sizes[1]) == 20000
    assert media._photo_size_bytes(sizes[0]) == 5000
    assert media._photo_size_bytes(sizes[2]) == 0
    assert max(sizes, key=media._photo_size_bytes)["type"] == "y"


class PagedRpc:
    def __init__(self, total, key):
        self.total, self.key, self.requests = total, key, []

    async def __call__(self, req, **kw):
        self.requests.append(req)
        if req["_"] == "messages.getHistory":
            start = req["offset_id"] or (self.total + 1)
            ids = list(range(start - 1, max(start - 1 - req["limit"], 0), -1))
            return {"messages": [{"id": i} for i in ids]}
        have = req["offset"]
        n = max(0, min(req["limit"], self.total - have))
        return {"participants": [{"user_id": have + i} for i in range(n)]}


def test_history_and_participants_paginate_past_server_caps():
    c = make_client()

    async def resolve(p):
        return {"_": "inputPeerChannel", "channel_id": 5, "access_hash": 1}

    c._resolve_peer = resolve
    c._rpc = PagedRpc(1000, "messages")
    msgs = run(c.get_message_history("x", limit=250))
    assert len(msgs) == 250 and len({m["id"] for m in msgs}) == 250
    assert [r["limit"] for r in c._rpc.requests] == [100, 100, 50]
    c._rpc = PagedRpc(450, "participants")
    members = run(c.get_participants("x", limit=1000))
    assert len(members) == 450
    assert [r["offset"] for r in c._rpc.requests] == [0, 200, 400]


def test_participant_filters_are_valid():
    c = make_client()
    sent = []

    async def resolve(p):
        return {"_": "inputPeerChannel", "channel_id": 5, "access_hash": 1}

    async def rpc(req, **kw):
        sent.append(req)
        return {"participants": []}

    c._resolve_peer, c._rpc = resolve, rpc
    run(c.get_participants_filtered("x", "kicked"))
    run(c.get_participants_filtered("x", "contacts"))
    for req in sent:
        tl.serialize_object(req, SCHEMA)
        assert req["filter"]["q"] == ""
    with pytest.raises(ValueError):
        run(c.get_participants_filtered("x", "admin"))


def test_chat_actions_serialize():
    c = make_client()
    sent = []

    async def resolve(p):
        return PEER

    async def rpc(req, **kw):
        sent.append(req)

    c._resolve_peer, c._rpc = resolve, rpc
    for action in ("typing", "upload_photo", "upload_video", "upload_audio", "upload_document", "upload_video_note", "cancel"):
        run(c.send_chat_action("x", action))
    assert len(sent) == 7
    for req in sent:
        action = req["action"]
        want = 4 + 4 * len([f for f in SCHEMA[action["_"]][1] if f[2] is None])
        assert len(tl.serialize_object(action, SCHEMA)) == want


def test_mark_read_and_delete_route_channels_correctly():
    c = make_client()
    sent = []

    async def resolve(p):
        return {"_": "inputPeerChannel", "channel_id": 5, "access_hash": 1}

    async def rpc(req, **kw):
        sent.append(req)
        return {}

    c._resolve_peer, c._rpc = resolve, rpc
    run(c.mark_as_read("x"))
    assert sent[-1]["_"] == "channels.readHistory"
    tl.serialize_object(sent[-1], SCHEMA)
    routed = []

    async def delete_in(peer, ids, revoke=True):
        routed.append((peer, ids))

    c.delete_messages_in = delete_in
    run(c.delete_messages([1, 2], peer="chan"))
    run(c.delete_message(3, peer="chan"))
    assert routed == [("chan", [1, 2]), ("chan", [3])]


def test_fields_sharing_a_flag_bit_must_come_together():
    base = {"_": "channels.createChannel", "title": "t", "about": "a"}
    geo = {"_": "inputGeoPoint", "lat": 1.0, "long": 2.0}
    with pytest.raises(tl.TLEncodeError, match="together"):
        tl.serialize_object(dict(base, geo_point=geo), SCHEMA)
    with pytest.raises(tl.TLEncodeError, match="together"):
        tl.serialize_object(dict(base, address="x"), SCHEMA)
    both = tl.serialize_object(dict(base, geo_point=geo, address="x"), SCHEMA)
    assert both.startswith(struct.pack("<I", SCHEMA["channels.createChannel"][0]))
    tl.serialize_object(base, SCHEMA)
    with pytest.raises(tl.TLEncodeError):
        tl.serialize_object({"_": "phone.toggleGroupCallRecord", "call": {"_": "inputGroupCall", "id": 1, "access_hash": 2}, "video": True}, SCHEMA)


def test_generic_path_places_flag_words_at_their_schema_position():
    obj = {"_": "account.deleteAccount", "reason": "bye"}
    cid, fields = SCHEMA["account.deleteAccount"]
    assert tl._serialize_generic(obj, cid, fields, SCHEMA) == functions.account.DeleteAccount(reason="bye").to_bytes()
    user = {"_": "user", "id": 5, "self": True, "first_name": "A"}
    assert tl.deserialize(tl.serialize_object(user, SCHEMA), BY_CID)["self"] is True


def test_unhandled_updates_are_not_decoded_and_entities_decode_once(monkeypatch):
    c = make_client()
    calls = {"deserialize": 0, "populate": 0}
    real = tl.deserialize

    def counting(data, schema):
        calls["deserialize"] += 1
        return real(data, schema)

    monkeypatch.setattr(tl, "deserialize", counting)
    c._populate_cache = lambda r: calls.__setitem__("populate", calls["populate"] + 1)
    got = []

    async def enqueue(item):
        got.append(item)

    c._enqueue_update = enqueue
    run(c._dispatch_raw_batch([good_update(1), good_update(2)], [], []))
    assert got == [] and calls["deserialize"] == 0

    c._handlers = {"message": {0: [(lambda cl, m: None, [])]}}
    user = types.User(id=7, first_name="A").to_bytes()
    run(c._dispatch_raw_batch([good_update(1)], [user], []))
    run(c._dispatch_raw_batch([good_update(2)], [user], []))
    assert len(got) == 2
    assert calls["populate"] == 1
