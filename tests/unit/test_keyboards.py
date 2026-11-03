# Keyboard builders must emit constructors that exist in the current TL schema.
#
# Runs without the compiled Rust extension (same loading trick as
# test_tl_roundtrip.py). For every button kind this checks that each emitted
# dict only uses known constructors and fields, that no required field is
# missing, and that the bytes parse back into the same constructors.

from __future__ import annotations

import importlib
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()


def _load():
    tl = importlib.import_module("ferogram.raw.tl")
    schema = importlib.import_module("ferogram.raw.generated._tl_schema")
    kb = importlib.import_module("ferogram.keyboards")
    return tl, schema, kb


tl, schema, kb = _load()
SCHEMA = schema._SCHEMA
BY_CID = schema._SCHEMA_BY_CID


def _check_schema(obj):
    """Recursively validate a dict built by a keyboard against the schema."""
    if isinstance(obj, list):
        for item in obj:
            _check_schema(item)
        return
    if not isinstance(obj, dict) or "_" not in obj:
        return
    name = obj["_"]
    assert name in SCHEMA, f"unknown constructor {name!r}"
    fields = {f[0]: f for f in SCHEMA[name][1]}
    for key in obj:
        if key != "_":
            assert key in fields, f"{name}: unknown field {key!r}"
    for fname, ftype, flag in SCHEMA[name][1]:
        if flag is None and ftype != "#":
            assert fname in obj, f"{name}: missing required field {fname!r}"
    for key, val in obj.items():
        if key != "_":
            _check_schema(val)


def _roundtrip(obj):
    data = tl.serialize_object(obj, SCHEMA)
    return tl.deserialize(data, BY_CID)


INLINE_EXPECTED = {
    "callback": ("inlineButtonTypeCallback", lambda: kb.InlineButton.callback("a", b"x")),
    "url": ("inlineButtonTypeUrl", lambda: kb.InlineButton.url("a", "https://example.com")),
    "switch_inline": ("inlineButtonTypeSwitchInline", lambda: kb.InlineButton.switch_inline("a", "q")),
    "switch_elsewhere": ("inlineButtonTypeSwitchInline", lambda: kb.InlineButton.switch_elsewhere("a", "q")),
    "copy_text": ("inlineButtonTypeCopy", lambda: kb.InlineButton.copy_text("a", "code")),
    "mini_app": ("inlineButtonTypeWebView", lambda: kb.InlineButton.mini_app("a", "https://example.com")),
    "game": ("inlineButtonTypeGame", lambda: kb.InlineButton.game("a")),
    "buy": ("inlineButtonTypeBuy", lambda: kb.InlineButton.buy("a")),
}

REPLY_EXPECTED = {
    "text": ("buttonTypeDefault", lambda: kb.ReplyButton.text("a")),
    "request_phone": ("buttonTypeRequestPhone", lambda: kb.ReplyButton.request_phone("a")),
    "request_geo": ("buttonTypeRequestGeoLocation", lambda: kb.ReplyButton.request_geo("a")),
    "request_poll": ("buttonTypeRequestPoll", lambda: kb.ReplyButton.request_poll("a")),
    "request_quiz": ("buttonTypeRequestPoll", lambda: kb.ReplyButton.request_quiz("a")),
    "mini_app_simple": ("buttonTypeSimpleWebView", lambda: kb.ReplyButton.mini_app_simple("a", "https://example.com")),
}


def test_inline_buttons_match_schema():
    for kind, (type_name, make) in INLINE_EXPECTED.items():
        d = make().to_dict()
        assert d["_"] == "keyboardInlineButton", kind
        assert d["type"]["_"] == type_name, kind
        _check_schema(d)
        parsed = _roundtrip(d)
        assert parsed["_"] == "keyboardInlineButton", kind
        assert parsed["text"] == "a", kind
        assert parsed["type"]["_"] == type_name, kind


def test_reply_buttons_match_schema():
    for kind, (type_name, make) in REPLY_EXPECTED.items():
        d = make().to_dict()
        assert d["_"] == "keyboardButton", kind
        assert d["type"]["_"] == type_name, kind
        _check_schema(d)
        parsed = _roundtrip(d)
        assert parsed["_"] == "keyboardButton", kind
        assert parsed["type"]["_"] == type_name, kind


def test_switch_inline_same_peer_flag_survives():
    same = _roundtrip(kb.InlineButton.switch_inline("a", "q").to_dict())["type"]
    elsewhere = _roundtrip(kb.InlineButton.switch_elsewhere("a", "q").to_dict())["type"]
    assert same["same_peer"] is True
    assert not elsewhere.get("same_peer")


def test_poll_and_quiz_differ():
    poll = _roundtrip(kb.ReplyButton.request_poll("a").to_dict())["type"]
    quiz = _roundtrip(kb.ReplyButton.request_quiz("a").to_dict())["type"]
    assert poll["quiz"] is False
    assert quiz["quiz"] is True


def test_inline_keyboard_markup():
    k = kb.InlineKeyboard()
    k.add_row([kb.InlineButton.callback("a", b"1"), kb.InlineButton.url("b", "https://example.com")])
    k.add_row([kb.InlineButton.game("c")])
    d = k.to_dict()
    assert d["_"] == "replyInlineMarkup"
    _check_schema(d)
    parsed = _roundtrip(d)
    assert parsed["_"] == "replyInlineMarkup"
    assert len(parsed["rows"]) == 2
    assert parsed["rows"][0]["_"] == "keyboardInlineButtonRow"
    assert len(parsed["rows"][0]["buttons"]) == 2
    assert parsed["rows"][0]["buttons"][0]["type"]["data"] == b"1"


def test_reply_keyboard_markup():
    k = kb.ReplyKeyboard(resize=True, single_use=True, placeholder="pick one")
    k.add_row([kb.ReplyButton.text("a"), kb.ReplyButton.request_phone("b")])
    d = k.to_dict()
    assert d["_"] == "replyKeyboardMarkup"
    _check_schema(d)
    parsed = _roundtrip(d)
    assert parsed["rows"][0]["_"] == "keyboardButtonRow"
    assert parsed["placeholder"] == "pick one"
    assert parsed["resize"] is True


def test_other_markups_match_schema():
    _check_schema(kb.RemoveKeyboard(selective=True).to_dict())
    _check_schema(kb.ForceReply(single_use=True, placeholder="x").to_dict())


def test_false_true_flags_are_not_sent():
    # `true` flags carry no wire value; False must mean "not set".
    cb = _roundtrip(kb.InlineButton.callback("a", b"x").to_dict())["type"]
    assert not cb.get("requires_password")

    rk = _roundtrip(kb.ReplyKeyboard().to_dict())
    for flag in ("resize", "single_use", "selective", "persistent"):
        assert not rk.get(flag), flag

    # An unknown extra key forces the generic (non-generated) serializer path.
    generic = {"_": "inlineButtonTypeSwitchInline", "query": "q", "same_peer": False, "bogus": 1}
    assert not _roundtrip(generic).get("same_peer")
    generic["same_peer"] = True
    assert _roundtrip(generic).get("same_peer") is True


def test_inline_mini_app_simple_is_gone():
    # layer 229 only offers the simple web view for reply keyboards
    assert not hasattr(kb.InlineButton, "mini_app_simple")


if __name__ == "__main__":
    ran = 0
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            ran += 1
    print(f"{ran} keyboard tests passed")
