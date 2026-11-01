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


"""Bot API style helpers: commands, inline queries, callbacks, mini apps, invoices."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..types import (
    InlineMessageId, InlineArticle, InlinePhoto, InlineDocument,
    _inline_result_to_tuple,
)
from .._internal import (
    _inline_message_id_to_tl,
    _inline_tuple_to_tl,
    _markup_to_dict,
)

if TYPE_CHECKING:
    pass


class BotMethods:
    """Bot API style helpers: commands, inline queries, callbacks, mini apps, invoices."""

    async def set_bot_commands(self, commands: list[tuple[str, str]], lang_code: str = "") -> None:
        await self._rpc({
            "_": "bots.setBotCommands",
            "scope": {"_": "botCommandScopeDefault"},
            "lang_code": lang_code,
            "commands": [{"_": "botCommand", "command": c, "description": d} for c, d in commands],
        })

    async def delete_bot_commands(self, lang_code: str = "") -> None:
        await self._rpc({
            "_": "bots.resetBotCommands",
            "scope": {"_": "botCommandScopeDefault"},
            "lang_code": lang_code,
        })

    async def set_bot_info(self, name: str | None = None, about: str | None = None,
                           description: str | None = None, lang_code: str = "") -> None:
        req: dict = {"_": "bots.setBotInfo", "lang_code": lang_code}
        if name is not None:
            req["name"] = name
        if about is not None:
            req["about"] = about
        if description is not None:
            req["description"] = description
        await self._rpc(req)

    async def get_bot_info(self, lang_code: str = "") -> dict:
        return await self._rpc({"_": "bots.getBotInfo", "lang_code": lang_code})

    async def answer_callback_query(self, query_id: int, text: str | None = None,
                                    alert: bool = False, cache_time: int = 0) -> None:
        req: dict = {
            "_": "messages.setBotCallbackAnswer",
            "query_id": query_id,
            "alert": alert,
            "cache_time": cache_time,
        }
        if text:
            req["message"] = text
        await self._rpc(req)

    async def answer_inline_query(self, query_id: int,
                                   results: "list[InlineArticle | InlinePhoto | InlineDocument | tuple]",
                                   cache_time: int = 300, is_personal: bool = False,
                                   next_offset: str | None = None,
                                   switch_pm: "tuple[str, str] | None" = None) -> None:
        raw = [_inline_result_to_tuple(r) for r in results]
        tl_results = [_inline_tuple_to_tl(r) for r in raw]
        req: dict = {
            "_": "messages.setInlineBotResults",
            "query_id": query_id,
            "results": tl_results,
            "cache_time": cache_time,
            "private": is_personal,
        }
        if next_offset is not None:
            req["next_offset"] = next_offset
        if switch_pm:
            req["switch_pm"] = {"_": "inlineBotSwitchPM", "text": switch_pm[0], "start_param": switch_pm[1]}
        await self._rpc(req)

    async def answer_inline_query_articles(self, query_id: int, articles: "list[tuple[str, str, str]]",
                                            cache_time: int = 300, is_personal: bool = False,
                                            next_offset: str | None = None) -> None:
        tl_results = [
            {"_": "inputBotInlineResult",
             "id": str(i),
             "type": "article",
             "title": title,
             "description": desc,
             "send_message": {"_": "inputBotInlineMessageText", "message": text}}
            for i, (title, desc, text) in enumerate(articles)
        ]
        req: dict = {
            "_": "messages.setInlineBotResults",
            "query_id": query_id,
            "results": tl_results,
            "cache_time": cache_time,
            "private": is_personal,
        }
        if next_offset:
            req["next_offset"] = next_offset
        await self._rpc(req)

    async def edit_inline_message(self, msg_id: "InlineMessageId | tuple[int, bytes] | dict",
                                   new_text: str, reply_markup=None,
                                   no_webpage: bool = True) -> bool:
        req: dict = {
            "_": "messages.editInlineBotMessage",
            "id": _inline_message_id_to_tl(msg_id),
            "message": new_text,
        }
        if no_webpage:
            req["no_webpage"] = True
        if reply_markup is not None:
            req["reply_markup"] = _markup_to_dict(reply_markup)
        await self._rpc(req)
        return True

    async def open_mini_app(self, peer: str, app_type: str = "main", app_value: str = "") -> dict:
        input_peer = await self._resolve_peer(peer)
        return await self._rpc({
            "_": "messages.requestWebView",
            "peer": input_peer,
            "bot": input_peer,
            "platform": "android",
        })

    async def get_game_high_scores(self, peer: str, msg_id: int, user_id: int) -> list[tuple[int, int, int]]:
        input_peer = await self._resolve_peer(peer)
        ah = self._peer_cache.get_user(user_id) or 0
        result = await self._rpc({
            "_": "messages.getGameHighScores",
            "peer": input_peer,
            "id": msg_id,
            "user_id": {"_": "inputUser", "user_id": user_id, "access_hash": ah},
        })
        scores = result.get("scores", []) if isinstance(result, dict) else []
        return [(s.get("pos", 0), s.get("user_id", 0), s.get("score", 0)) for s in scores]

    async def send_invoice(self, peer: str, title: str, description: str, payload: str,
                           currency: str, prices: list[tuple[str, int]],
                           photo_url: str | None = None, need_name: bool = False,
                           need_phone: bool = False, need_email: bool = False,
                           need_shipping_address: bool = False, is_flexible: bool = False,
                           test: bool = False) -> dict:
        input_peer = await self._resolve_peer(peer)
        invoice: dict = {
            "_": "invoice",
            "currency": currency,
            "prices": [{"_": "labeledPrice", "label": l, "amount": a} for l, a in prices],
            "test": test,
            "name_requested": need_name,
            "phone_requested": need_phone,
            "email_requested": need_email,
            "shipping_address_requested": need_shipping_address,
            "flexible": is_flexible,
        }
        media: dict = {
            "_": "inputMediaInvoice",
            "title": title,
            "description": description,
            "invoice": invoice,
            "payload": payload.encode(),
            "provider": "",
            "provider_data": {"_": "dataJSON", "data": "{}"},
        }
        if photo_url:
            media["photo"] = {"_": "inputWebDocument", "url": photo_url, "size": 0, "mime_type": "image/jpeg", "attributes": []}
        return await self._rpc({
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": media,
            "message": "",
            "random_id": random.randint(-(2**63), 2**63 - 1),
        })
