"""POST /telegram/webhook. Track B, commit 12.

- The X-Telegram-Bot-Api-Secret-Token header must equal TELEGRAM_WEBHOOK_SECRET (constant-time compare);
  403 on mismatch or when the secret is not set.
- Idempotency key tg:<update_id> (store.mark_seen): a redelivered update is acknowledged and skipped.
- The route answers 200 at once and processes the update in a background task, so Telegram never
  retries because of a slow model call.
- Only update.message is handled. Text goes to the orchestrator; /start opens a fresh case. Non-text
  messages (APK documents, photos, voice notes, stickers, contacts) become a short note such as
  "[sent a document: StockPro.apk]" so they are part of the case and the persona answers in character.
- While the orchestrator works, sendChatAction "typing" is sent at once and every TYPING_INTERVAL seconds.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import app.orchestrator as orchestrator
from app.channels.telegram_api import TelegramAPI
from app.runtime import get_runtime

log = logging.getLogger("scambait.telegram")
router = APIRouter()

START_REPLY = "Hello? Who is this?"
FALLBACK_REPLY = "Sorry, my phone is acting up. Can you send that again?"
TYPING_INTERVAL = 4.0  # Telegram shows "typing" for about 5 s per action
START_RE = re.compile(r"^/start(@\w+)?(\s|$)")

_api: Optional[TelegramAPI] = None
_tasks: set[asyncio.Task] = set()  # strong references so background tasks are not garbage collected


def get_api() -> TelegramAPI:
    global _api
    if _api is None:
        _api = TelegramAPI(get_runtime().settings.telegram_bot_token)
    return _api


def set_api(api: Optional[TelegramAPI]) -> None:
    """Tests install a TelegramAPI backed by httpx.MockTransport."""
    global _api
    _api = api


async def close_api() -> None:
    """Optional, for the app lifespan shutdown."""
    global _api
    if _api is not None:
        await _api.aclose()
        _api = None


async def drain() -> None:
    """Wait for all in-flight update tasks (tests and graceful shutdown)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def _ok() -> JSONResponse:
    return JSONResponse({"ok": True})


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> JSONResponse:
    try:
        rt = get_runtime()
    except RuntimeError:
        return JSONResponse({"ok": False, "error": "service starting"}, status_code=503)
    secret = rt.settings.telegram_webhook_secret or ""
    got = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not secret or not hmac.compare_digest(got.encode("utf-8"), secret.encode("utf-8")):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    try:
        update = await request.json()
    except ValueError:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)
    update_id = update.get("update_id") if isinstance(update, dict) else None
    if not isinstance(update_id, int):
        return JSONResponse({"ok": False, "error": "missing update_id"}, status_code=400)

    if not await rt.store.mark_seen(f"tg:{update_id}"):
        return _ok()  # duplicate delivery, already processed
    _spawn(process_update(update))
    return _ok()


def describe_message(msg: dict[str, Any]) -> Optional[str]:
    """The text to hand to the orchestrator, or None for service messages with no content."""
    text = msg.get("text")
    if isinstance(text, str) and text.strip():
        return text
    note: Optional[str] = None
    if msg.get("animation"):
        note = "[sent a GIF]"
    elif isinstance(msg.get("document"), dict):
        name = str(msg["document"].get("file_name") or "").strip()
        note = f"[sent a document: {name}]" if name else "[sent a document]"
    elif msg.get("photo"):
        note = "[sent a photo]"
    elif msg.get("voice"):
        note = "[sent a voice note]"
    elif msg.get("video_note"):
        note = "[sent a video message]"
    elif msg.get("video"):
        note = "[sent a video]"
    elif isinstance(msg.get("audio"), dict):
        name = str(msg["audio"].get("file_name") or "").strip()
        note = f"[sent an audio file: {name}]" if name else "[sent an audio file]"
    elif msg.get("sticker"):
        note = "[sent a sticker]"
    elif isinstance(msg.get("contact"), dict):
        c = msg["contact"]
        parts = [str(c.get(k) or "").strip() for k in ("first_name", "last_name", "phone_number")]
        details = " ".join(p for p in parts if p)
        note = f"[shared a contact: {details}]" if details else "[shared a contact]"
    elif msg.get("location"):
        note = "[shared a location]"
    elif msg.get("poll"):
        note = "[sent a poll]"
    if note is None:
        return None
    caption = msg.get("caption")
    if isinstance(caption, str) and caption.strip():
        note = f"{note} {caption.strip()}"
    return note


async def _keep_typing(api: TelegramAPI, chat_id: Any, stop: asyncio.Event) -> None:
    """Send "typing" at once (even if stop is already set), then every TYPING_INTERVAL s until stop."""
    while True:
        await api.send_chat_action(chat_id, "typing")
        try:
            await asyncio.wait_for(stop.wait(), timeout=TYPING_INTERVAL)
            return
        except asyncio.TimeoutError:
            continue


async def process_update(update: dict[str, Any]) -> None:
    """Background handler for one update. Never raises."""
    try:
        msg = update.get("message")
        if not isinstance(msg, dict):
            return  # edited_message, channel_post, callback_query, ...: ignored
        chat_id = (msg.get("chat") or {}).get("id")
        if chat_id is None:
            return
        text = describe_message(msg)
        if text is None:
            return
        api = get_api()
        store = get_runtime().store
        external_id = f"tg:{chat_id}"

        if START_RE.match(text.strip()):
            case = await store.new_case("telegram", external_id)
            log.info("telegram /start opened case %s", case.get("id"))
            await api.send_message(chat_id, START_REPLY)
            return

        case = await store.get_or_create_case("telegram", external_id)
        stop = asyncio.Event()
        typing = asyncio.create_task(_keep_typing(api, chat_id, stop))
        try:
            reply = await orchestrator.handle_message(case["id"], "telegram", text)
        except Exception:
            log.exception("orchestrator failed for case %s", case.get("id"))
            reply = None
        finally:
            stop.set()
            # Let the in-flight typing action finish so it never lands after the reply.
            await asyncio.gather(typing, return_exceptions=True)

        if reply is None:
            await api.send_message(chat_id, FALLBACK_REPLY)  # in character; the error is logged above
            return
        if reply.coalesced or not reply.text.strip():
            return  # another task answers this burst
        await api.send_message(chat_id, reply.text)
    except Exception:
        log.exception("telegram update processing failed")
