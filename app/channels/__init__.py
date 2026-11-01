"""Track B channels (see docs/CONTRACTS.md): POST /api/v1/honeypot and POST /telegram/webhook."""
from fastapi import APIRouter

from app.channels.honeypot import router as honeypot_router
from app.channels.telegram import router as telegram_router

router = APIRouter()
router.include_router(honeypot_router)
router.include_router(telegram_router)

__all__ = ["router"]
