from __future__ import annotations

import importlib
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import support  # noqa: E402

support.install()

import tl_reference as ref  # noqa: E402

tl = importlib.import_module("ferogram.raw.tl")
schema = importlib.import_module("ferogram.raw.generated._tl_schema")

SCHEMA_FILE = HERE.parent.parent / "schema" / "api.tl"
CTORS = ref.parse_tl(str(SCHEMA_FILE))
REF = ref.Schema(CTORS)
SKIP_DECODE = {"boolTrue", "boolFalse"}


def canon(o):
    if isinstance(o, dict):
        return {k: canon(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [canon(x) for x in o]
    return o


def test_constructor_ids_match_definition_checksums():
    bad = [c.name for c in CTORS if ref.infer_id(c.text) != c.cid]
    assert not bad, bad[:10]


def test_parsed_schema_matches_independent_parse():
    for c in CTORS:
        if c.name not in schema._SCHEMA:
            continue
        cid, fields = schema._SCHEMA[c.name]
        want = [f for f in c.fields if f[1] != "#"]
        assert cid == c.cid, c.name
        assert [tuple(f) for f in fields] == want, c.name


def test_every_codec_path_matches_reference_on_every_constructor():
    r = random.Random(20260101)
    dispatch = tl._ensure_serialize_dispatch()
    failures: list[str] = []
    for c in CTORS:
        if c.name not in schema._SCHEMA:
            continue
        cid, fields = schema._SCHEMA[c.name]
        for _ in range(3):
            try:
                obj = ref.gen_obj(REF, r, c, 0)
            except KeyError:
                break
            want = ref.enc_obj(REF, obj)
            if tl.serialize_object(obj, schema._SCHEMA) != want:
                failures.append(f"serialize_object {c.name}")
            if tl._serialize_generic(obj, cid, fields, schema._SCHEMA) != want:
                failures.append(f"generic writer {c.name}")
            cls = dispatch.get(c.name)
            if cls is not None:
                kw = {(k + "_" if k in tl._PY_KEYWORDS else k): v for k, v in obj.items() if k != "_"}
                if cls(**kw).to_bytes() != want:
                    failures.append(f"to_bytes {c.name}")
            if not c.is_func and c.name not in SKIP_DECODE:
                if canon(tl.deserialize(want, schema._SCHEMA_BY_CID)) != canon(obj):
                    failures.append(f"from_bytes {c.name}")
                if canon(tl._read_value(want, 0, schema._SCHEMA_BY_CID)[0]) != canon(obj):
                    failures.append(f"generic reader {c.name}")
    assert not failures, failures[:10]


def test_generated_packages_load_lazily_and_keep_both_import_styles():
    types = importlib.import_module("ferogram.raw.generated.types")
    functions = importlib.import_module("ferogram.raw.generated.functions")
    assert functions.GetHistory is functions.messages.GetHistory
    assert types.Message.__name__ == "Message"
    assert "Message" in dir(types) and "messages" in dir(functions)
    assert importlib.import_module("ferogram.raw.generated.types").InputPeerUser._CID == 0xdde8a54c
    try:
        types.DoesNotExist
    except AttributeError:
        pass
    else:
        raise AssertionError("unknown names must raise AttributeError")
