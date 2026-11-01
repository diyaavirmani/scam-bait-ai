"""FastAPI entry point. Run with: uvicorn app.main:app --workers 1"""
from __future__ import annotations

from fastapi import FastAPI

from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SCAM-BAIT AI", version="2.0.0")
    app.state.settings = settings

    @app.get("/health")
    async def health() -> dict:
        return {"status": "starting", "checks": {}}

    return app


app = create_app()
