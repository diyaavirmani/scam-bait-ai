"""Dashboard pages (/chats, /calls, /cases, /export) plus their static assets. Open, no login. Track C."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response


router = APIRouter()

STATIC = Path(__file__).parent / "static"
ASSET_RE = re.compile(r"^[a-z0-9_-]{1,40}\.(js|css)$")
PAGES = ("chats", "calls", "cases", "export")
NO_STORE = {"Cache-Control": "no-store"}


def _page(name: str) -> Response:
    return FileResponse(STATIC / f"{name}.html", media_type="text/html", headers=NO_STORE)



def _make_page_route(name: str):
    async def handler(request: Request) -> Response:
        return _page(name)
    handler.__name__ = f"page_{name}"
    return handler


for _name in PAGES:
    router.add_api_route(f"/{_name}", _make_page_route(_name), methods=["GET"], include_in_schema=False)


@router.get("/dashboard/assets/{name}", include_in_schema=False)
async def asset(name: str) -> Response:
    """Static JS/CSS for the pages."""
    if not ASSET_RE.match(name) or not (STATIC / name).is_file():
        raise HTTPException(status_code=404)
    media = "text/javascript" if name.endswith(".js") else "text/css"
    return FileResponse(STATIC / name, media_type=media, headers={"Cache-Control": "no-cache"})
