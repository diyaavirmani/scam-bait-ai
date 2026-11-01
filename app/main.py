"""FastAPI entry point. Run with: uvicorn app.main:app --workers 1 (one process: in-process memory and locks)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.channels import router as channels_router
from app.channels import telegram as telegram_channel
from app.config import Settings, get_settings
from app.events import Bus
from app.events.sse import router as events_router
from app.logs import setup_logging
from app.providers import build_clients
from app.voice import router as voice_router
from app.web import router as web_router
from app.web_alt import router as alt_router
from app.runtime import Runtime, get_runtime, set_runtime
from app.store import Store

setup_logging()
log = logging.getLogger("scambait")

_selftest: dict = {"ok": False, "detail": "not run"}


async def start_runtime(settings: Settings) -> Runtime:
    """Open the store, build clients, run the startup self-test. Raises (loudly) on missing config or models."""
    missing = settings.missing_required()
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)} (see .env.example)")
    store = Store(settings.db_path)
    await store.init()
    cerebras, openai_client = build_clients(settings)
    rt = Runtime(settings=settings, store=store, bus=Bus(store), cerebras=cerebras, openai=openai_client)
    set_runtime(rt)
    # M-01: fail loudly at startup if the pinned models are not served
    _selftest.update(await cerebras.self_test())
    _selftest["detail"] = "ok"
    log.info("model self-test ok: %s", _selftest.get("models"))
    await register_telegram_webhook(settings)
    return rt


async def register_telegram_webhook(settings: Settings) -> None:
    """Point the bot at PUBLIC_BASE_URL/telegram/webhook on startup so the deployed URL and secret always match.
    Logs only the ok flag and description, never the token or the secret. Set TELEGRAM_AUTO_WEBHOOK=0 to skip."""
    import os
    if os.getenv("TELEGRAM_AUTO_WEBHOOK", "1") == "0":
        return
    missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
                              ("TELEGRAM_WEBHOOK_SECRET", settings.telegram_webhook_secret),
                              ("PUBLIC_BASE_URL", settings.public_base_url)) if not v]
    if missing:
        log.warning("telegram webhook not registered, missing: %s", ", ".join(missing))
        return
    from app.channels.telegram_api import TelegramAPI
    api = TelegramAPI(settings.telegram_bot_token)
    try:
        body = await api.set_webhook(settings.public_base_url + "/telegram/webhook",
                                     settings.telegram_webhook_secret, allowed_updates=["message"])
        if body is None:
            log.warning("telegram webhook register: request failed")
        else:
            log.info("telegram webhook register: ok=%s description=%s", body.get("ok"), body.get("description", ""))
    except Exception as exc:  # never block startup on Telegram
        log.warning("telegram webhook register error: %s", type(exc).__name__)
    finally:
        await api.aclose()


def create_app(settings: Settings | None = None, *, run_startup: bool = True) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_startup:
            await start_runtime(settings)
        yield
        if run_startup:
            await telegram_channel.drain()
            await telegram_channel.close_api()
            rt = get_runtime()
            for closer in (getattr(rt.cerebras, "client", None), getattr(rt.openai, "client", None)):
                if closer is not None:
                    await closer.close()
            if getattr(rt.openai, "http", None) is not None:
                await rt.openai.http.aclose()
            await rt.store.close()

    app = FastAPI(title="SCAM-BAIT AI", version="2.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(events_router)
    app.include_router(voice_router)
    app.include_router(channels_router)
    app.include_router(web_router)
    app.include_router(alt_router)

    @app.get("/health")
    async def health():
        """Real checks (A-04): database ping and the model self-test result."""
        try:
            db_ok = await get_runtime().store.ping()
        except Exception:
            db_ok = False
        from app.detection.decisions import decisions_status
        ok = db_ok and _selftest["ok"]
        body = {"status": "ok" if ok else "degraded",
                "checks": {"database": db_ok, "models": _selftest, "decisions": decisions_status()}}
        return JSONResponse(body, status_code=200 if ok else 503)

    return app


app = create_app()
