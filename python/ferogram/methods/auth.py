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


"""Login, sign-in, sessions and QR login."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._internal import (
    SignInCodeInvalid,
    _srp_answer,
    _is_bot_token,
)

if TYPE_CHECKING:
    pass


class AuthMethods:
    """Login, sign-in, sessions and QR login."""

    async def _interactive_login(self) -> None:
        identifier = self._phone
        if identifier is None:
            identifier = input("Phone number (e.g. +91XXXXXXXXXX) or bot token: ").strip()

        if _is_bot_token(identifier):
            await self.bot_sign_in(identifier)
            self._log.info("signed in as bot")
            print("\nPlease ensure your usage complies with Telegram's API Terms of Service.")
            return

        sent = await self.request_login_code(identifier)
        if sent.get("_") == "auth.sentCodeSuccess":
            # Fast re-auth via a stored future_auth_token; no code needed.
            self._log.info("signed in as user (fast re-auth, no code needed)")
            print("\nPlease ensure your usage complies with Telegram's API Terms of Service.")
            return

        pw_token = None
        for attempt in range(3):
            try:
                pw_token = await self.sign_in(sent, input("Code: "))
                break
            except SignInCodeInvalid as e:
                if e.expired:
                    print("Code expired, requesting a new one...")
                    sent = await self.resend_code(sent)
                    if sent.get("_") == "auth.sentCodeSuccess":
                        self._log.info("signed in as user (fast re-auth, no code needed)")
                        print("\nPlease ensure your usage complies with Telegram's API Terms of Service.")
                        return
                elif attempt < 2:
                    print("Invalid code, try again.")
                else:
                    raise
        if pw_token is not None:
            hint = pw_token.get("hint", "")
            pwd  = self._password or input(f"2FA password (hint: {hint}): " if hint else "2FA password: ")
            await self.check_password(pw_token, pwd)
        self._log.info("signed in as user")
        print("\nPlease ensure your usage complies with Telegram's API Terms of Service.")

    async def is_authorized(self) -> bool:
        try:
            result = await self._rpc({"_": "users.getUsers", "id": [{"_": "inputUserSelf"}]})
            users = result if isinstance(result, list) else result.get("users", [])
            return bool(users)
        except Exception as exc:
            self._log.debug("is_authorized() check failed: %s", exc)
            return False

    async def _handle_sent_code(self, result: dict, phone: str) -> dict:
        """Shared post-processing for auth.sendCode / auth.resendCode
        responses. Mirrors ferogram's Rust `handle_sent_code`, reused by
        both `request_login_code` and `resend_code` since Telegram returns
        the same `auth.SentCode` shape for both.
        """
        if result.get("_") == "auth.sentCodeSuccess":
            # Telegram authorized the session outright; the token was
            # single-use, so drop it rather than risk replaying a stale one.
            await self._require_conn().set_future_auth_token(None)
            authorization = result.get("authorization", {})
            user = authorization.get("user") if isinstance(authorization, dict) else None
            if isinstance(user, dict):
                self._populate_cache({"users": [user]})
            return result
        # auth.sentCode does not carry phone_number back, so stash it
        # for sign_in()/resend_code() which need it.
        result["phone_number"] = phone
        return result

    async def request_login_code(self, phone: str) -> dict:
        """Ask Telegram to send a login code.

        If a previous `sign_out()` on this session captured a
        `future_auth_token`, it's replayed automatically here so Telegram
        can skip code entry and authorize the session immediately
        (`auth.sentCodeSuccess`). In that case the returned dict has
        `"_": "auth.sentCodeSuccess"` and no code needs to be entered -
        check for that before prompting the user.
        """
        api_id, api_hash = self._require_creds()
        code_settings: dict = {"_": "codeSettings"}
        stored_token = await self._require_conn().get_future_auth_token()
        if stored_token is not None:
            code_settings["logout_tokens"] = [stored_token]

        result = await self._rpc({
            "_": "auth.sendCode",
            "phone_number": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "settings": code_settings,
        })
        return await self._handle_sent_code(result, phone)

    async def resend_code(self, sent_code: dict, reason: str | None = None) -> dict:
        """Ask Telegram to resend the login code via a different delivery
        method (e.g. SMS -> call), using `sent_code["next_type"]` as the
        next method Telegram already told you it'll try.

        `sent_code` is whatever `request_login_code`/`resend_code` last
        returned. `reason` is an optional client-side diagnostic string
        Telegram may log (e.g. "user did not receive code").

        Like `request_login_code`, this can return an `auth.sentCodeSuccess`
        dict instead of a new code - check `result["_"]` before prompting.
        """
        phone = sent_code.get("phone_number", "")
        phone_code_hash = sent_code.get("phone_code_hash", "")
        req: dict = {
            "_": "auth.resendCode",
            "phone_number": phone,
            "phone_code_hash": phone_code_hash,
        }
        if reason is not None:
            req["reason"] = reason
        result = await self._rpc(req)
        return await self._handle_sent_code(result, phone)

    async def sign_in(self, sent_code: dict, code: str) -> dict | None:
        """Submit a login code. Returns None on success (no 2FA), or a
        password-info dict if 2FA is required - pass that to
        `check_password()`.

        Raises `SignInCodeInvalid` if Telegram rejects the code
        (`.expired=True` means the code timed out - call `resend_code()`
        before trying again; `.expired=False` means it was just wrong -
        re-prompt and retry with the same `sent_code`).
        """
        phone = sent_code.get("phone_number", "")
        phone_code_hash = sent_code.get("phone_code_hash", "")
        try:
            result = await self._rpc({
                "_": "auth.signIn",
                "phone_number": phone,
                "phone_code_hash": phone_code_hash,
                "phone_code": code,
            })
        except RuntimeError as e:
            msg = str(e)
            if "PHONE_CODE_EXPIRED" in msg:
                raise SignInCodeInvalid(msg, expired=True) from e
            if "PHONE_CODE_INVALID" in msg or "PHONE_CODE_EMPTY" in msg:
                raise SignInCodeInvalid(msg, expired=False) from e
            raise
        if result.get("_") == "auth.authorizationSignUpRequired":
            raise RuntimeError("Sign-up required - account does not exist.")
        if result.get("_") == "auth.authorization":
            return None  # success, no 2FA
        # SESSION_PASSWORD_NEEDED
        if result.get("_") == "rpc_error" or "error_code" in result:
            if result.get("error_message") == "SESSION_PASSWORD_NEEDED":
                return await self._rpc({"_": "account.getPassword"})
        return None

    async def check_password(self, pw_info: dict, password: str) -> None:
        srp = _srp_answer(pw_info, password)
        await self._rpc({"_": "auth.checkPassword", "password": srp})

    async def bot_sign_in(self, token: str) -> None:
        api_id, api_hash = self._require_creds()
        await self._rpc({
            "_": "auth.importBotAuthorization",
            "flags": 0,
            "api_id": api_id,
            "api_hash": api_hash,
            "bot_auth_token": token,
        })

    async def sign_out(self) -> None:
        try:
            result = await self._rpc({"_": "auth.logOut"})
            if isinstance(result, dict) and result.get("_") == "auth.loggedOut":
                token = result.get("future_auth_token")
                if isinstance(token, (bytes, bytearray)):
                    await self._require_conn().set_future_auth_token(bytes(token))
        except Exception as exc:
            self._log.warning("sign_out() RPC failed, local state may be stale: %s", exc)

    async def login_bot(self, token: str) -> None:
        await self.bot_sign_in(token)
        await self._require_conn().save_session()

    async def export_session_string(self) -> str:
        return await self._require_conn().export_string()

    async def get_authorizations(self) -> list[dict]:
        result = await self._rpc({"_": "account.getAuthorizations"})
        return result.get("authorizations", []) if isinstance(result, dict) else []

    async def terminate_session(self, hash: int) -> None:
        await self._rpc({"_": "account.resetAuthorization", "hash": hash})

    async def export_login_token(self) -> tuple[bytes, int]:
        api_id, api_hash = self._require_creds()
        result = await self._rpc({"_": "auth.exportLoginToken", "api_id": api_id, "api_hash": api_hash, "except_ids": []})
        return bytes(result.get("token", b"")), result.get("expires", 0)

    async def check_qr_login(self, token: bytes) -> str | None:
        try:
            result = await self._rpc({"_": "auth.acceptLoginToken", "token": token})
            return result.get("user", {}).get("username")
        except Exception as exc:
            self._log.debug("check_qr_login() poll failed (expected while waiting): %s", exc)
            return None
