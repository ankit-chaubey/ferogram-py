# Dispatcher event wrappers.

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

support.install()

from ferogram import updates as U  # noqa: E402


def test_every_registered_event_type_wraps_empty_input():
    # A malformed or sparse update must never crash the dispatcher.
    assert U._UPDATE_FACTORIES
    for event_type, factory in U._UPDATE_FACTORIES.items():
        wrapped = U.wrap_update(event_type, {})
        assert wrapped is not None, event_type
        assert isinstance(wrapped, factory), event_type


def test_unknown_event_types_become_raw_updates():
    raw = {"_": "updateWalletState"}
    wrapped = U.wrap_update("definitely_not_registered", raw)
    assert isinstance(wrapped, U.RawUpdate)


def test_known_event_types_are_not_raw():
    for event_type in ("message", "callback_query", "inline_query", "user_status"):
        assert not isinstance(U.wrap_update(event_type, {}), U.RawUpdate), event_type


def test_registered_factories_all_have_from_tl():
    for event_type, factory in U._UPDATE_FACTORIES.items():
        assert callable(getattr(factory, "from_tl", None)), event_type
