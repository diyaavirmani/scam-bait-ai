"""Login and dashboard pages (/login, /chats, /calls, /cases, /export) plus their static assets. Track C."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app.web.auth import (COOKIE_NAME, SESSION_TTL_S, get_settings, is_authed, login_redirect, make_cookie,
                          password_ok, safe_next)

router = APIRouter()

STATIC = Path(__file__).parent / "static"
ASSET_RE = re.compile(r"^[a-z0-9_-]{1,40}\.(js|css)$")
PAGES = ("chats", "calls", "cases", "export")
NO_STORE = {"Cache-Control": "no-store"}


def _page(name: str) -> Response:
    return FileResponse(STATIC / f"{name}.html", media_type="text/html", headers=NO_STORE)


@router.get("/login", include_in_schema=False)
async def login_page(request: Request) -> Response:
    if is_authed(request):
        return RedirectResponse(safe_next(request.query_params.get("next")), status_code=303)
    return _page("login")


@router.post("/login", include_in_schema=False)
async def login_submit(request: Request) -> Response:
    form = await request.form()
    pw = str(form.get("password") or "")[:200]
    nxt = safe_next(str(form.get("next") or ""))
    settings = get_settings(request)
    if not settings.dashboard_password:
        return RedirectResponse("/login?error=disabled", status_code=303)
    if not password_ok(settings.dashboard_password, pw):
        await asyncio.sleep(0.5)  # slow down guessing
        return RedirectResponse("/login?error=1&next=" + _q(nxt), status_code=303)
    resp = RedirectResponse(nxt, status_code=303)
    resp.set_cookie(COOKIE_NAME, make_cookie(settings.dashboard_password), max_age=SESSION_TTL_S, httponly=True,
                    samesite="lax", secure=request.url.scheme == "https", path="/")
    return resp


@router.post("/logout", include_in_schema=False)
async def logout() -> Response:
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


def _q(value: str) -> str:
    from urllib.parse import quote
    return quote(value, safe="")


def _make_page_route(name: str):
    async def handler(request: Request) -> Response:
        if not is_authed(request):
            return login_redirect(request)
        return _page(name)
    handler.__name__ = f"page_{name}"
    return handler


for _name in PAGES:
    router.add_api_route(f"/{_name}", _make_page_route(_name), methods=["GET"], include_in_schema=False)


@router.get("/dashboard/assets/{name}", include_in_schema=False)
async def asset(name: str) -> Response:
    """Static JS/CSS for the pages. No data in them, so no login needed (the login page uses app.css)."""
    if not ASSET_RE.match(name) or not (STATIC / name).is_file():
        raise HTTPException(status_code=404)
    media = "text/javascript" if name.endswith(".js") else "text/css"
    return FileResponse(STATIC / name, media_type=media, headers={"Cache-Control": "no-cache"})
