# Wire-level behaviour of the hand-written TL serializer in ferogram.raw.tl.

from __future__ import annotations

import importlib
import pathlib
import struct
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()

tl = importlib.import_module("ferogram.raw.tl")
schema = importlib.import_module("ferogram.raw.generated._tl_schema")
SCHEMA = schema._SCHEMA
BY_CID = schema._SCHEMA_BY_CID


def roundtrip(obj):
    return tl.deserialize(tl.serialize_object(obj, SCHEMA), BY_CID)


def test_schema_constructor_ids_are_unique_and_indexed():
    ids = [entry[0] for entry in SCHEMA.values()]
    assert len(ids) == len(set(ids)), "two constructors share one id"
    for cid, (name, _fields) in BY_CID.items():
        assert SCHEMA[name][0] == cid, name


def test_layer_matches_schema_header():
    header = (support.ROOT / "schema" / "api.tl").read_text(encoding="utf8").splitlines()[0]
    assert header.strip() == f"// LAYER {schema.LAYER}"


def test_fixed_layout_constructor_serializes_to_expected_bytes():
    # inputPeerUser#dde8a54c user_id:long access_hash:long = InputPeer
    data = tl.serialize_object({"_": "inputPeerUser", "user_id": 5, "access_hash": -3}, SCHEMA)
    assert data == struct.pack("<Iqq", 0xDDE8A54C, 5, -3)
    # inputPeerSelf#7da07ec9 has no fields
    assert tl.serialize_object({"_": "inputPeerSelf"}, SCHEMA) == struct.pack("<I", 0x7DA07EC9)


def test_bool_and_long_fields_round_trip():
    obj = roundtrip({"_": "inputPeerUser", "user_id": 2**40 + 7, "access_hash": -(2**50)})
    assert obj["user_id"] == 2**40 + 7
    assert obj["access_hash"] == -(2**50)


def test_string_and_bytes_padding_for_all_lengths():
    for n in (0, 1, 3, 4, 5, 253, 254, 255, 256, 1000):
        text = "x" * n
        blob = bytes(range(256)) * 4
        blob = blob[:n]
        msg = roundtrip({"_": "inputBotInlineMessageText", "message": text})
        assert msg["message"] == text, n
        cb = roundtrip({"_": "inlineButtonTypeCallback", "data": blob, "requires_password": False})
        assert cb["data"] == blob, n


def test_unicode_strings_survive():
    text = "héllo 🌍 世界"
    got = roundtrip({"_": "inputBotInlineMessageText", "message": text})
    assert got["message"] == text


def test_vectors_round_trip():
    obj = {"_": "replyInlineMarkup", "rows": []}
    assert roundtrip(obj)["rows"] == []
    row = {"_": "keyboardInlineButtonRow", "buttons": []}
    assert roundtrip({"_": "replyInlineMarkup", "rows": [row, row]})["rows"] == [row, row]


def test_optional_flag_fields_absent_and_present():
    bare = roundtrip({"_": "inputPeerChannel", "channel_id": 1, "access_hash": 2})
    assert bare["channel_id"] == 1
    flagged = roundtrip({"_": "inputBotInlineMessageText", "message": "a", "no_webpage": True})
    assert flagged["no_webpage"] is True
    plain = roundtrip({"_": "inputBotInlineMessageText", "message": "a"})
    assert not plain.get("no_webpage")


def test_true_flag_false_means_absent():
    # Regression: an explicit False on a `true` flag used to set the bit.
    explicit_false = {"_": "inputBotInlineMessageText", "message": "a", "no_webpage": False}
    omitted = {"_": "inputBotInlineMessageText", "message": "a"}
    assert tl.serialize_object(explicit_false, SCHEMA) == tl.serialize_object(omitted, SCHEMA)
    # still holds on the generic path (an unknown extra key forces it)
    generic = dict(explicit_false, bogus=1)
    assert tl.serialize_object(generic, SCHEMA) == tl.serialize_object(omitted, SCHEMA)


def test_bool_valued_flag_keeps_false():
    # `Bool` (not `true`) flags carry a value, so False is meaningful.
    on = tl.serialize_object({"_": "buttonTypeRequestPoll", "quiz": True}, SCHEMA)
    off = tl.serialize_object({"_": "buttonTypeRequestPoll", "quiz": False}, SCHEMA)
    none = tl.serialize_object({"_": "buttonTypeRequestPoll"}, SCHEMA)
    assert len({on, off, none}) == 3


def test_unknown_constructor_is_an_error():
    with pytest.raises(Exception):
        tl.serialize_object({"_": "thisConstructorDoesNotExist"}, SCHEMA)


def test_namespaced_functions_and_newer_layer_types_are_present():
    for name in ("messages.sendMessage", "channels.joinChannel", "wallet.userAddresses",
                 "keyboardInlineButton", "inlineButtonTypeCallback"):
        assert name in SCHEMA, name


# ---- peer constructors in typed fields -----------------------------------------

def _fields(name):
    return [(f[0], f[1]) for f in SCHEMA[name][1]]


def test_peer_coercion_table_only_swaps_constructors_with_identical_fields():
    for declared, table in tl._PEER_COERCE.items():
        for source, target in table.items():
            assert source in SCHEMA and target in SCHEMA, (declared, source, target)
            assert _fields(source) == _fields(target), (source, target)


# One request per declared type that has exactly that single peer field.
_ANCHORS = {
    "InputChannel": ("channels.leaveChannel", "channel"),
    "InputUser": ("users.getFullUser", "id"),
    "InputPeer": ("messages.getPeerSettings", "peer"),
}


def _sample(name):
    """A value of constructor `name` with every field filled with a harmless dummy."""
    value = {"_": name}
    for fname, ftype, _flag in SCHEMA[name][1]:
        value[fname] = {"_": "inputPeerEmpty"} if ftype == "InputPeer" else 0
    return value


def test_every_mapped_peer_constructor_is_serialized_as_its_target():
    for declared, table in tl._PEER_COERCE.items():
        func, field = _ANCHORS[declared]
        for source, target in table.items():
            sample = _sample(source)
            sent = tl.serialize({"_": func, field: sample}, SCHEMA)
            expected = tl.serialize({"_": func, field: {**sample, "_": target}}, SCHEMA)
            assert sent == expected, (declared, source, target)
            if source != target:
                # and it really changed something compared to sending the source as is
                assert struct.pack("<I", SCHEMA[target][0]) in sent
                assert struct.pack("<I", SCHEMA[source][0]) not in sent


def test_constructors_of_the_declared_type_are_untouched():
    for declared, (func, field) in _ANCHORS.items():
        own = {"InputChannel": "inputChannel", "InputUser": "inputUser", "InputPeer": "inputPeerUser"}[declared]
        sample = _sample(own)
        req = {"_": func, field: sample}
        assert tl._coerce_peer_fields(req, SCHEMA[func][1]) is req


def test_peer_coercion_handles_vectors_and_typed_objects():
    peer = {"_": "inputPeerUser", "user_id": 1, "access_hash": 2}
    via_peer = tl.serialize({"_": "channels.inviteToChannel",
                             "channel": {"_": "inputPeerChannel", "channel_id": 5, "access_hash": 9},
                             "users": [peer, {"_": "inputPeerSelf"}]}, SCHEMA)
    explicit = tl.serialize({"_": "channels.inviteToChannel",
                             "channel": {"_": "inputChannel", "channel_id": 5, "access_hash": 9},
                             "users": [{"_": "inputUser", "user_id": 1, "access_hash": 2},
                                       {"_": "inputUserSelf"}]}, SCHEMA)
    assert via_peer == explicit


def test_peer_coercion_converts_in_the_other_direction_too():
    channel = {"_": "inputChannel", "channel_id": 5, "access_hash": 9}
    got = tl.serialize({"_": "messages.getHistory", "peer": channel, "offset_id": 0, "offset_date": 0,
                        "add_offset": 0, "limit": 1, "max_id": 0, "min_id": 0, "hash": 0}, SCHEMA)
    want = tl.serialize({"_": "messages.getHistory", "peer": {**channel, "_": "inputPeerChannel"},
                         "offset_id": 0, "offset_date": 0, "add_offset": 0, "limit": 1,
                         "max_id": 0, "min_id": 0, "hash": 0}, SCHEMA)
    assert got == want


def test_peer_coercion_leaves_correct_input_alone():
    req = {"_": "channels.leaveChannel", "channel": {"_": "inputChannel", "channel_id": 5, "access_hash": 9}}
    assert tl._coerce_peer_fields(req, SCHEMA["channels.leaveChannel"][1]) is req
