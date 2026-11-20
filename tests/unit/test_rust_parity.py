from __future__ import annotations

import asyncio
import importlib
import pathlib
import random
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import support  # noqa: E402

support.install()

import tl_reference as ref  # noqa: E402

CTORS = ref.parse_tl(str(HERE.parent.parent / "schema" / "api.tl"))
REF = ref.Schema(CTORS)
ROOTS = {"User": "users", "Chat": "chats", "Message": "new_messages",
         "Update": "other_updates", "EncryptedMessage": "new_encrypted_messages"}
STATE = {"_": "updates.state", "pts": 150, "qts": 6, "date": 1700000500, "seq": 8, "unread_count": 0}


def rust():
    if support.uses_stub():
        pytest.skip("needs the compiled extension")
    return importlib.import_module("ferogram._ferogram")


async def primed(mod, channel=False):
    mb = mod.MessageBox()
    await mb.set_state(100, 5, 1700000000, 7)
    if channel:
        await mb.try_set_channel_state(777, 40)
        gap = {"_": "updateShort", "update": {"_": "updateChannelTooLong", "channel_id": 777, "pts": 90}, "date": 1700000700}
        await mb.process_raw(ref.enc_obj(REF, gap))
        await mb.next_channel_diff()
    else:
        await mb.mark_gap()
        await mb.check_deadline_secs()
        await mb.get_difference_bytes()
    return mb


def adjust(obj):
    if obj["_"] in REF.by_name and any(f[0] == "qts" for f in REF.by_name[obj["_"]].fields):
        obj["qts"] = 7
    return obj


def identical(root, obj, ups, users, chats):
    raw = ref.enc_obj(REF, obj)
    if root == "User":
        return bool(users) and users[0] == raw
    if root == "Chat":
        return bool(chats) and chats[0] == raw
    if root in ("Message", "EncryptedMessage"):
        return any(u[4:4 + len(raw)] == raw for u in ups)
    return any(u == raw for u in ups)


def test_rust_get_difference_bytes_match_python_reference():
    mod = rust()
    r = random.Random(3)

    async def go():
        for _ in range(60):
            pts, qts = r.choice([1, 2**31 - 1, r.randint(1, 2**31 - 1)]), r.randint(0, 2**31 - 1)
            date, seq = r.randint(1, 2**31 - 1), r.randint(0, 2**31 - 1)
            mb = mod.MessageBox()
            await mb.set_state(pts, qts, date, seq)
            await mb.mark_gap()
            await mb.check_deadline_secs()
            want = ref.enc_obj(REF, {"_": "updates.getDifference", "pts": pts, "date": date, "qts": qts})
            assert await mb.get_difference_bytes() == want

    asyncio.run(go())


def test_rust_codec_round_trips_every_constructor_it_can_reach():
    mod = rust()
    r = random.Random(5)
    parent = ref.reach_paths(REF, list(ROOTS))
    targets = [c for c in CTORS if not c.is_func and c.result in parent]
    assert len(targets) > 800

    async def go():
        failures, returned = [], 0
        for c in targets:
            root, steps = ref.path_to(parent, c.result)
            obj = adjust(ref.gen_forced(REF, r, steps, c) if steps else ref.gen_obj(REF, r, c, 0))
            lists = {"new_messages": [], "new_encrypted_messages": [], "other_updates": [], "chats": [], "users": []}
            lists[ROOTS[root]] = [obj]
            body = ref.enc_obj(REF, {"_": "updates.difference", **lists, "state": STATE})
            mb = await primed(mod)
            try:
                ups, users, chats = await mb.apply_difference(body)
            except Exception as e:
                failures.append((c.name, str(e)[:80]))
                continue
            if ups or users or chats:
                returned += 1
                if not identical(root, obj, ups, users, chats):
                    failures.append((c.name, "different bytes"))
        assert not failures, failures[:10]
        assert returned > len(targets) * 0.95

    asyncio.run(go())


def test_rust_channel_difference_and_pushed_containers_match():
    mod = rust()
    r = random.Random(9)
    roots = {"Message": "new_messages", "Update": "other_updates", "Chat": "chats", "User": "users"}

    async def go():
        failures = []
        for c in [c for c in CTORS if not c.is_func and c.result in roots]:
            obj = adjust(ref.gen_obj(REF, r, c, 0))
            lists = {"new_messages": [], "other_updates": [], "chats": [], "users": []}
            lists[roots[c.result]] = [obj]
            body = ref.enc_obj(REF, {"_": "updates.channelDifference", "pts": 95, **lists})
            mb = await primed(mod, channel=True)
            try:
                ups, users, chats = await mb.apply_channel_difference(body)
            except Exception as e:
                failures.append((c.name, str(e)[:80]))
                continue
            if (ups or users or chats) and not identical(c.result, obj, ups, users, chats):
                failures.append((c.name, "different bytes"))
        plain = [c for c in CTORS if not c.is_func and c.result == "Update"
                 and not any(f[0] in ("pts", "pts_count", "qts", "channel_id", "channel") for f in c.fields)]
        for c in plain:
            obj = ref.gen_obj(REF, r, c, 0)
            user = ref.gen_obj(REF, r, REF.by_name["user"], 0)
            chat = ref.gen_obj(REF, r, REF.by_name["channel"], 0)
            container = {"_": "updates", "updates": [obj], "users": [user], "chats": [chat], "date": 1700000700, "seq": 0}
            mb = mod.MessageBox()
            await mb.set_state(100, 5, 1700000000, 7)
            res = await mb.process_raw(ref.enc_obj(REF, container))
            if res is None or res[0] != [ref.enc_obj(REF, obj)] or res[1] != [ref.enc_obj(REF, user)] or res[2] != [ref.enc_obj(REF, chat)]:
                failures.append((c.name, "pushed container"))
        assert not failures, failures[:10]

    asyncio.run(go())
