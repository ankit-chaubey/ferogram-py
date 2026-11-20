# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0

from __future__ import annotations

import re

_NAME = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")
_CODE = re.compile(r"\b([1-5]\d\d)\b")
_VALUE = re.compile(r"\(value: (\d+)\)")
_FLOOD = ("FLOOD_WAIT", "FLOOD_PREMIUM_WAIT", "SLOWMODE_WAIT", "FLOOD_TEST_PHONE_WAIT")


class RpcError(RuntimeError):
    def __init__(self, message: str, code: int | None = None,
                 name: str = "", value: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.name = name
        self.value = value

    @classmethod
    def from_runtime(cls, exc: BaseException) -> RuntimeError:
        msg = str(exc)
        m = _NAME.search(msg)
        if m is None:
            return exc if isinstance(exc, RuntimeError) else RuntimeError(msg)
        token = m.group(1)
        name, value = token, None
        tail = re.match(r"^(.*)_(\d+)$", token)
        if tail:
            name, value = tail.group(1), int(tail.group(2))
        v = _VALUE.search(msg)
        if v:
            value = int(v.group(1))
        c = _CODE.search(msg)
        code = int(c.group(1)) if c else None
        if name in _FLOOD:
            return FloodWait(msg, code, name, value)
        return cls(msg, code, name, value)


class FloodWait(RpcError):
    @property
    def seconds(self) -> int:
        return self.value or 0
