"""Minimal Telegram Bot API client (httpx). Track B, commit 12.

The bot token is part of every request URL, so it is never logged: log lines carry the method name and
the HTTP status only, errors are logged by exception type only, and the httpx request logger (which
prints full URLs at INFO) is raised to WARNING here.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

log = logging.getLogger("scambait.telegram")
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs full request URLs (with the token) at INFO

API_BASE = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 4096  # Telegram sendMessage limit


class TelegramAPI:
    def __init__(self, token: str, client: Optional[httpx.AsyncClient] = None, timeout: float = 15.0) -> None:
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @property
    def configured(self) -> bool:
        return bool(self._token)

    async def call(self, method: str, payload: dict[str, Any]) -> Optional[dict]:
        """POST one Bot API method. Returns the parsed JSON body, or None on any error (logged, never raised)."""
        if not self._token:
            log.error("telegram %s skipped: TELEGRAM_BOT_TOKEN is not set", method)
            return None
        try:
            resp = await self._client.post(f"{API_BASE}/bot{self._token}/{method}", json=payload)
        except Exception as exc:  # network error; str(exc) may contain the URL, so log the type only
            log.warning("telegram %s failed: %s", method, type(exc).__name__)
            return None
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code != 200 or not isinstance(body, dict) or not body.get("ok"):
            desc = body.get("description", "") if isinstance(body, dict) else ""
            log.warning("telegram %s status=%s %s", method, resp.status_code, str(desc)[:200])
            return body if isinstance(body, dict) else None
        log.debug("telegram %s status=%s", method, resp.status_code)
        return body

    async def send_message(self, chat_id: int | str, text: str) -> Optional[dict]:
        return await self.call("sendMessage", {"chat_id": chat_id, "text": text[:MAX_MESSAGE_CHARS]})

    async def send_chat_action(self, chat_id: int | str, action: str = "typing") -> Optional[dict]:
        return await self.call("sendChatAction", {"chat_id": chat_id, "action": action})

    async def set_webhook(self, url: str, secret_token: str, drop_pending_updates: bool = False,
                          allowed_updates: Optional[list[str]] = None) -> Optional[dict]:
        """Used only by scripts/set_telegram_webhook.py."""
        return await self.call("setWebhook", {
            "url": url,
            "secret_token": secret_token,
            "drop_pending_updates": drop_pending_updates,
            "allowed_updates": allowed_updates if allowed_updates is not None else ["message"],
        })

    async def aclose(self) -> None:
        await self._client.aclose()
