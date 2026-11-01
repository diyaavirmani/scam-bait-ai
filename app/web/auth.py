"""Dashboard cookie auth (A-03). Track C, commit 18.

One shared password (DASHBOARD_PASSWORD). A successful login sets an HttpOnly, SameSite=Lax cookie
`sb_session = <session id>.<issued unix time>.<HMAC-SHA256>`, signed with a key derived from the password.
Changing the password invalidates every cookie. An empty password refuses all logins.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

COOKIE_NAME = "sb_session"
SESSION_TTL_S = 12 * 3600


def get_settings(request: Optional[Request] = None):
    """Settings from the runtime (contract), falling back to app.state.settings."""
    try:
        from app.runtime import get_runtime
        return get_runtime().settings
    except RuntimeError:
        if request is not None and getattr(request.app.state, "settings", None) is not None:
            return request.app.state.settings
        from app.config import get_settings as _gs
        return _gs()


def _key(password: str) -> bytes:
    return hashlib.sha256(b"scambait-dashboard-cookie-v1\x00" + password.encode("utf-8")).digest()


def _sign(password: str, payload: str) -> str:
    return hmac.new(_key(password), payload.encode("ascii"), hashlib.sha256).hexdigest()


def make_cookie(password: str, now: Optional[float] = None) -> str:
    sid = secrets.token_hex(16)
    issued = str(int(now if now is not None else time.time()))
    payload = f"{sid}.{issued}"
    return f"{payload}.{_sign(password, payload)}"


def cookie_valid(password: str, value: Optional[str], now: Optional[float] = None) -> bool:
    if not password or not value or len(value) > 200:
        return False
    parts = value.split(".")
    if len(parts) != 3:
        return False
    sid, issued, sig = parts
    if not issued.isdigit():
        return False
    try:
        expected = _sign(password, f"{sid}.{issued}")
    except UnicodeEncodeError:
        return False
    if not hmac.compare_digest(expected, sig):
        return False
    age = (now if now is not None else time.time()) - int(issued)
    return -60 <= age <= SESSION_TTL_S


def password_ok(password: str, attempt: str) -> bool:
    if not password:
        return False  # A-03: never accept logins when no password is configured
    return hmac.compare_digest(password.encode("utf-8"), (attempt or "").encode("utf-8"))


def is_authed(request: Request) -> bool:
    return cookie_valid(get_settings(request).dashboard_password, request.cookies.get(COOKIE_NAME))


async def require_api(request: Request) -> None:
    """Dependency for JSON and SSE routes: 401 JSON when the cookie is missing or bad."""
    if not is_authed(request):
        raise HTTPException(status_code=401, detail="login required")
    _check_origin(request)


def _check_origin(request: Request) -> None:
    """If the browser sends an Origin, it must be this site (public URL or the Host it called)."""
    origin = request.headers.get("origin")
    if not origin:
        return
    allowed = {f"{request.url.scheme}://{request.headers.get('host', '')}"}
    base = get_settings(request).public_base_url
    if base:
        allowed.add(base.rstrip("/"))
    if origin.rstrip("/") not in allowed:
        raise HTTPException(status_code=403, detail="origin not allowed")


def login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)


def safe_next(value: Optional[str]) -> str:
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/chats"
