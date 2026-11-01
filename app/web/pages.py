"""Dashboard SPA (React build in app/web/dist) served on the same origin as the API. Open, no login.

GET /, /chats, /calls, /intel, /networks, /cases, /export, /system and /overview return the SPA index.html;
GET /assets/{name} serves the hashed JS and CSS. Build with: cd dashboard && npm ci && npm run build.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response

router = APIRouter()

DIST = Path(__file__).parent / "dist"
SPA_ROUTES = ("/", "/overview", "/chats", "/calls", "/intel", "/networks", "/cases", "/export", "/system")
ASSET_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}\.(js|css)$")
NO_STORE = {"Cache-Control": "no-store"}


async def spa_index() -> Response:
    index = DIST / "index.html"
    if not index.is_file():
        return PlainTextResponse("Dashboard not built. Run: cd dashboard && npm ci && npm run build", status_code=503)
    return FileResponse(index, media_type="text/html", headers=NO_STORE)


for _path in SPA_ROUTES:
    router.add_api_route(_path, spa_index, methods=["GET"], include_in_schema=False,
                         name="spa_" + (_path.strip("/") or "root"))


@router.get("/assets/{name}", include_in_schema=False)
async def asset(name: str) -> Response:
    """Hashed build assets; names are checked so nothing outside dist/assets can be read."""
    path = DIST / "assets" / name
    if not ASSET_RE.match(name) or not path.is_file():
        raise HTTPException(status_code=404)
    media = "text/javascript" if name.endswith(".js") else "text/css"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "public, max-age=31536000, immutable"})
