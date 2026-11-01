"""Track C dashboard: login, pages (/chats, /calls, /cases, /export), JSON API and exports.

`router` includes everything; app/main.py does `app.include_router(app.web.router)`.
"""
from fastapi import APIRouter

from app.web import api, pages

router = APIRouter()
router.include_router(pages.router)
router.include_router(api.router)

__all__ = ["router"]
