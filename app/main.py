"""FastAPI entry point. Run with: uvicorn app.main:app --workers 1 (one process: in-process memory and locks)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.events import Bus
from app.events.sse import router as events_router
from app.runtime import Runtime, get_runtime, set_runtime
from app.store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("scambait")

_selftest: dict = {"ok": False, "detail": "not run"}


async def start_runtime(settings: Settings) -> Runtime:
    """Open the store, build clients, run the startup self-test. Raises (loudly) on missing config or models."""
    missing = settings.missing_required()
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)} (see .env.example)")
    store = Store(settings.db_path)
    await store.init()
    rt = Runtime(settings=settings, store=store, bus=Bus(store))
    set_runtime(rt)
    return rt


def create_app(settings: Settings | None = None, *, run_startup: bool = True) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_startup:
            await start_runtime(settings)
        yield
        if run_startup:
            await get_runtime().store.close()

    app = FastAPI(title="SCAM-BAIT AI", version="2.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(events_router)

    @app.get("/health")
    async def health():
        """Real checks (A-04): database ping and the model self-test result."""
        try:
            db_ok = await get_runtime().store.ping()
        except Exception:
            db_ok = False
        ok = db_ok and _selftest["ok"]
        body = {"status": "ok" if ok else "degraded", "checks": {"database": db_ok, "models": _selftest}}
        return JSONResponse(body, status_code=200 if ok else 503)

    return app


app = create_app()
