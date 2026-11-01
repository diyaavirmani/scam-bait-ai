"""Point the Telegram bot at PUBLIC_BASE_URL/telegram/webhook. Run manually, only after the user agrees:

    .venv/bin/python scripts/set_telegram_webhook.py

Prints only the API's ok flag and description; never the token or the secret.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.channels.telegram_api import TelegramAPI  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main() -> int:
    s = get_settings()
    missing = [name for name, value in (("TELEGRAM_BOT_TOKEN", s.telegram_bot_token),
                                        ("TELEGRAM_WEBHOOK_SECRET", s.telegram_webhook_secret),
                                        ("PUBLIC_BASE_URL", s.public_base_url)) if not value]
    if missing:
        print("Missing settings: " + ", ".join(missing))
        return 1
    api = TelegramAPI(s.telegram_bot_token)
    try:
        body = await api.set_webhook(s.public_base_url + "/telegram/webhook", s.telegram_webhook_secret,
                                     drop_pending_updates=False, allowed_updates=["message"])
    finally:
        await api.aclose()
    if body is None:
        print("ok=False description=request failed (see log)")
        return 1
    print(f"ok={body.get('ok')} description={body.get('description', '')}")
    return 0 if body.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
