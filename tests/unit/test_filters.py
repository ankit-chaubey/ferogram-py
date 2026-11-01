# Message, callback and composite filters, checked on plain stand-in objects.

from __future__ import annotations

import pathlib
import re
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()

from ferogram import filters as F  # noqa: E402


def msg(text="", chat_id=1, sender_id=7, **kw):
    return NS(text=text, chat_id=chat_id, sender_id=sender_id, **kw)


def wrapped(inner):
    """Dispatcher events wrap the message as `.message`."""
    return NS(message=inner)


def test_chat_kind_filters():
    assert F.private(msg(chat_id=5))
    assert not F.private(msg(chat_id=-5))
    assert F.group(msg(chat_id=-5))
    assert not F.group(msg(chat_id=5))
    # channel posts have a negative chat id and no sender
    assert F.channel(msg(chat_id=-5, sender_id=None))
    assert not F.channel(msg(chat_id=-5, sender_id=7))


def test_text_presence_and_wrapped_events():
    assert F.text(msg("hi"))
    assert not F.text(msg(""))
    assert F.text(wrapped(msg("hi")))
    assert not F.text(wrapped(msg("")))


def test_command_matching():
    f = F.command("start", "help")
    assert f(msg("/start"))
    assert f(msg("/START"))
    assert f(msg("/help me please"))
    assert f(msg("/start@my_bot payload"))
    assert not f(msg("/stop"))
    assert not f(msg("start"))
    assert not f(msg(""))


def test_command_with_custom_prefix():
    f = F.command("go", prefix="!")
    assert f(msg("!go"))
    assert not f(msg("/go"))


def test_command_ignores_bare_prefix():
    # A message that is only the prefix must not raise.
    f = F.command("start")
    assert f(msg("/")) is False
    assert f(msg("/ ")) is False
    assert f(msg("/   ")) is False


def test_text_matching_filters():
    assert F.regex(r"^\d+$")(msg("12345"))
    assert not F.regex(r"^\d+$")(msg("12a45"))
    assert F.regex(re.compile("hello", re.I))(msg("Say HELLO"))
    assert F.text_contains("ping")(msg("PING!"))
    assert not F.text_contains("ping", case_sensitive=True)(msg("PING!"))
    assert F.startswith("ab")(msg("abc"))
    assert not F.startswith("ab")(msg("cab"))
    assert F.endswith("bc")(msg("abc"))


def test_sender_and_chat_filters():
    assert F.user(7, 8)(msg(sender_id=8))
    assert not F.user(7, 8)(msg(sender_id=9))
    assert F.chat(-100)(msg(chat_id=-100))
    assert not F.chat(-100)(msg(chat_id=100))


def test_message_flag_filters():
    assert F.outgoing(msg(out=True))
    assert not F.outgoing(msg(out=False))
    assert F.incoming(msg(out=False))
    assert not F.incoming(msg(out=True))
    assert F.reply(msg(reply_to_msg_id=3))
    assert not F.reply(msg(reply_to_msg_id=None))
    assert F.forwarded(msg(forward_from_id=3))
    assert F.album(msg(grouped_id=11))
    assert not F.album(msg(grouped_id=None))
    assert F.mentioned(msg(mentioned=True))
    assert F.pinned(msg(pinned=True))
    assert F.via_bot(msg(via_bot_id=4))
    assert F.photo(msg(has_photo=True))
    assert F.document(msg(has_document=True))
    assert F.media(msg(media={"_": "messageMediaPhoto"}))
    assert not F.media(msg(media=None))


def test_composition():
    is_text = F.text
    is_cmd = F.command("start")
    both = F.and_(is_text, is_cmd)
    either = F.or_(F.command("a"), F.command("b"))
    assert both(msg("/start"))
    assert not both(msg("hello"))
    assert either(msg("/b"))
    assert not either(msg("/c"))
    assert F.not_(F.text)(msg(""))
    assert F.AND is F.and_ and F.OR is F.or_ and F.NOT is F.not_
    assert F.and_()(msg())          # empty AND is vacuously true
    assert not F.or_()(msg())       # empty OR is false


def test_callback_data_filters():
    q_bytes = NS(data=b"page:2")
    q_str = NS(data="page:2")
    q_none = NS(data=None)
    assert F.data("page:2")(q_bytes)
    assert F.data("page:2")(q_str)
    assert not F.data("page:2")(q_none)
    assert F.data_startswith("page:")(q_bytes)
    assert F.data_regex(r"^page:\d+$")(q_bytes)
    assert not F.data_regex(r"^page:\d+$")(NS(data=b"other"))


def test_callback_data_survives_invalid_utf8():
    assert not F.data("x")(NS(data=b"\xff\xfe"))


def test_inline_filter():
    assert F.inline()(NS(query="anything"))
    assert F.inline(r"^cat")(NS(query="cats"))
    assert not F.inline(r"^cat")(NS(query="dog"))
    assert not F.inline(r"^cat")(NS(query=None))


def test_presence_and_action_filters():
    assert F.online(NS(online=True))
    assert F.offline(NS(online=False))
    assert F.status("recently")(NS(status="recently"))
    assert F.typing(NS(action="typing"))
    assert not F.typing(NS(action="uploading"))
    assert F.action("recording")(NS(action="recording"))
    assert F.participant_status("kicked", "left")(NS(status="left"))
    assert not F.participant_status("kicked")(NS(status="joined"))


def test_reaction_and_poll_filters():
    assert F.reaction("👍", "🔥")(NS(new_reactions=["🔥"]))
    assert not F.reaction("👍")(NS(new_reactions=["🔥"]))
    assert not F.reaction("👍")(NS(new_reactions=[]))
    assert F.vote_position(1)(NS(positions=[0, 1]))
    assert not F.vote_position(2)(NS(positions=[0, 1]))


def test_raw_update_filters():
    assert F.constructor(0xDEADBEEF)(NS(constructor_id=0xDEADBEEF))
    assert not F.constructor(1)(NS(constructor_id=2))
    assert F.update_type("updateWalletState")(NS(type_name="updateWalletState"))


def test_length_filters():
    assert F.min_length(3)(NS(text="abc"))
    assert not F.min_length(4)(NS(text="abc"))
    assert F.max_length(3)(NS(text="abc"))
    assert not F.max_length(2)(NS(text="abc"))
    assert F.max_length(0)(NS(text=None))


def test_bot_filters():
    assert F.bot(NS(sender=NS(bot=True)))
    assert F.no_bot(NS(sender=NS(bot=False)))
    assert F.no_bot(NS(sender=None))
    assert not F.bot(NS(sender=None))
