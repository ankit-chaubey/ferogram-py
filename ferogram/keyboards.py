# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# ferogram is a high-performance Telegram MTProto framework written in Rust.
# ferogram-py is a Python MTProto library powered by ferogram, delivering
# native Rust performance through a clean and Pythonic API for building
# Telegram clients, bots, and applications.
#
# Rust: https://github.com/ankit-chaubey/ferogram
# Python: https://github.com/ankit-chaubey/ferogram-py
#
# If you use or modify this code, keep this notice at the top of the file
# and include the LICENSE-MIT or LICENSE-APACHE file from this repository.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "InlineButton", "InlineKeyboard",
    "ReplyButton", "ReplyKeyboard",
    "RemoveKeyboard", "ForceReply",
]


@dataclass
class InlineButton:
    text: str
    _kind: str
    _data: Any = None

    # constructors

    @staticmethod
    def callback(text: str, data: bytes) -> "InlineButton":
        return InlineButton(text=text, _kind="callback", _data=data)

    @staticmethod
    def url(text: str, url: str) -> "InlineButton":
        return InlineButton(text=text, _kind="url", _data=url)

    @staticmethod
    def switch_inline(text: str, query: str) -> "InlineButton":
        return InlineButton(text=text, _kind="switch_inline", _data=query)

    @staticmethod
    def switch_elsewhere(text: str, query: str) -> "InlineButton":
        return InlineButton(text=text, _kind="switch_elsewhere", _data=query)

    @staticmethod
    def copy_text(text: str, copy_text: str) -> "InlineButton":
        return InlineButton(text=text, _kind="copy_text", _data=copy_text)

    @staticmethod
    def mini_app(text: str, url: str) -> "InlineButton":
        return InlineButton(text=text, _kind="mini_app", _data=url)

    @staticmethod
    def mini_app_simple(text: str, url: str) -> "InlineButton":
        return InlineButton(text=text, _kind="mini_app_simple", _data=url)

    @staticmethod
    def game(text: str) -> "InlineButton":
        return InlineButton(text=text, _kind="game")

    @staticmethod
    def buy(text: str) -> "InlineButton":
        return InlineButton(text=text, _kind="buy")

    def to_dict(self) -> dict:
        k = self._kind
        t = self.text
        if k == "callback":
            return {"_": "keyboardButtonCallback", "text": t, "data": self._data, "requires_password": False}
        if k == "url":
            return {"_": "keyboardButtonUrl", "text": t, "url": self._data}
        if k == "switch_inline":
            return {"_": "keyboardButtonSwitchInline", "text": t, "query": self._data, "same_peer": True}
        if k == "switch_elsewhere":
            return {"_": "keyboardButtonSwitchInline", "text": t, "query": self._data, "same_peer": False}
        if k == "copy_text":
            return {"_": "keyboardButtonCopy", "text": t, "copy_text": self._data}
        if k == "mini_app":
            return {"_": "keyboardButtonWebView", "text": t, "url": self._data}
        if k == "mini_app_simple":
            return {"_": "keyboardButtonSimpleWebView", "text": t, "url": self._data}
        if k == "game":
            return {"_": "keyboardButtonGame", "text": t}
        if k == "buy":
            return {"_": "keyboardButtonBuy", "text": t}
        return {"_": "keyboardButton", "text": t}

    def __repr__(self) -> str:
        return f"InlineButton({self.text!r}, kind={self._kind})"


class InlineKeyboard:
    def __init__(self) -> None:
        self._rows: list[list[InlineButton]] = []

    def add_row(self, buttons: list[InlineButton]) -> None:
        if not buttons:
            raise ValueError("row must contain at least one button")
        self._rows.append(list(buttons))

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def to_dict(self) -> dict:
        return {
            "_": "replyInlineMarkup",
            "rows": [
                {"_": "keyboardButtonRow", "buttons": [b.to_dict() for b in row]}
                for row in self._rows
            ],
        }

    def __repr__(self) -> str:
        return f"InlineKeyboard(rows={len(self._rows)})"


@dataclass
class ReplyButton:
    text: str
    _kind: str = "text"

    @staticmethod
    def text(label: str) -> "ReplyButton":
        return ReplyButton(text=label, _kind="text")

    @staticmethod
    def request_phone(label: str) -> "ReplyButton":
        return ReplyButton(text=label, _kind="request_phone")

    @staticmethod
    def request_geo(label: str) -> "ReplyButton":
        return ReplyButton(text=label, _kind="request_geo")

    @staticmethod
    def request_poll(label: str) -> "ReplyButton":
        return ReplyButton(text=label, _kind="request_poll")

    @staticmethod
    def request_quiz(label: str) -> "ReplyButton":
        return ReplyButton(text=label, _kind="request_quiz")

    def to_dict(self) -> dict:
        k = self._kind
        t = self.text
        if k == "request_phone":
            return {"_": "keyboardButtonRequestPhone", "text": t}
        if k == "request_geo":
            return {"_": "keyboardButtonRequestGeoLocation", "text": t}
        if k in ("request_poll", "request_quiz"):
            return {"_": "keyboardButtonRequestPoll", "text": t, "quiz": k == "request_quiz"}
        return {"_": "keyboardButton", "text": t}

    def __repr__(self) -> str:
        return f"ReplyButton({self.text!r})"


class ReplyKeyboard:
    def __init__(self, *, resize: bool = False, single_use: bool = False,
                 selective: bool = False, placeholder: str | None = None) -> None:
        self._rows: list[list[ReplyButton]] = []
        self.resize = resize
        self.single_use = single_use
        self.selective = selective
        self.placeholder = placeholder

    def add_row(self, buttons: list[ReplyButton]) -> None:
        if not buttons:
            raise ValueError("row must contain at least one button")
        self._rows.append(list(buttons))

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def to_dict(self) -> dict:
        d: dict = {
            "_": "replyKeyboardMarkup",
            "resize": self.resize,
            "single_use": self.single_use,
            "selective": self.selective,
            "persistent": False,
            "rows": [
                {"_": "keyboardButtonRow", "buttons": [b.to_dict() for b in row]}
                for row in self._rows
            ],
        }
        if self.placeholder:
            d["placeholder"] = self.placeholder
        return d

    def __repr__(self) -> str:
        return f"ReplyKeyboard(rows={len(self._rows)}, resize={self.resize}, single_use={self.single_use})"


class RemoveKeyboard:
    def __init__(self, selective: bool = False) -> None:
        self.selective = selective

    def to_dict(self) -> dict:
        return {"_": "replyKeyboardHide", "selective": self.selective}

    def __repr__(self) -> str:
        return f"RemoveKeyboard(selective={self.selective})"


class ForceReply:
    def __init__(self, *, single_use: bool = False, selective: bool = False,
                 placeholder: str | None = None) -> None:
        self.single_use = single_use
        self.selective = selective
        self.placeholder = placeholder

    def to_dict(self) -> dict:
        d: dict = {
            "_": "replyKeyboardForceReply",
            "single_use": self.single_use,
            "selective": self.selective,
        }
        if self.placeholder:
            d["placeholder"] = self.placeholder
        return d

    def __repr__(self) -> str:
        return f"ForceReply(single_use={self.single_use}, selective={self.selective})"
