"""Track C, commit 18: dashboard auth, pages, case API, no mock data in the static files."""
import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import app.events as events
import app.web as web
from app.config import Settings
from app.events import Bus
from app.models import Event
from app.runtime import Runtime, set_runtime
from app.store import Store
from app.web.auth import COOKIE_NAME, cookie_valid, make_cookie

PW = "pw-test-only"
STATIC = Path(web.__file__).parent / "static"


def _app():
    a = FastAPI()
    a.include_router(events.router)
    a.include_router(web.router)
    return a


@pytest.fixture
async def env(tmp_path):
    store = Store(str(tmp_path / "w.db"))
    await store.init()
    rt = Runtime(settings=Settings(dashboard_password=PW, public_base_url="https://sb.example"), store=store, bus=Bus(store))
    set_runtime(rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as client:
        yield rt, client
    await store.close()


async def _login(client):
    r = await client.post("/login", data={"password": PW, "next": "/calls"})
    assert r.status_code == 303 and r.headers["location"] == "/calls"
    return r


@pytest.mark.parametrize("path", ["/chats", "/calls", "/cases", "/export"])
async def test_pages_redirect_to_login(env, path):
    _, client = env
    r = await client.get(path)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")


@pytest.mark.parametrize("path", ["/api/v1/cases", "/api/v1/cases/c_000000000000", "/api/v1/events/stream"])
async def test_api_requires_login(env, path):
    _, client = env
    r = await client.get(path)
    assert r.status_code == 401 and r.json()["detail"] == "login required"


async def test_login_sets_httponly_lax_cookie_and_opens_pages(env):
    _, client = env
    bad = await client.post("/login", data={"password": "nope"})
    assert bad.status_code == 303 and "error=1" in bad.headers["location"] and COOKIE_NAME not in bad.cookies
    r = await _login(client)
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc
    for path in ["/chats", "/calls", "/cases", "/export"]:
        page = await client.get(path)
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert (await client.get("/api/v1/cases")).json()["cases"] == []
    await client.post("/logout")
    client.cookies.clear()
    assert (await client.get("/api/v1/cases")).status_code == 401


async def test_empty_password_refuses_login(env):
    rt, client = env
    set_runtime(Runtime(settings=Settings(dashboard_password="", public_base_url=""), store=rt.store, bus=rt.bus))
    r = await client.post("/login", data={"password": ""})
    assert r.status_code == 303 and "error=disabled" in r.headers["location"] and COOKIE_NAME not in r.cookies
    assert not cookie_valid("", make_cookie("x"))


def test_cookie_signature_and_expiry():
    c = make_cookie(PW, now=1000)
    assert cookie_valid(PW, c, now=1001)
    assert not cookie_valid("other", c, now=1001)
    assert not cookie_valid(PW, c[:-1] + ("0" if c[-1] != "0" else "1"), now=1001)
    assert not cookie_valid(PW, c, now=1000 + 13 * 3600)


async def test_foreign_origin_rejected(env):
    _, client = env
    await _login(client)
    assert (await client.get("/api/v1/cases", headers={"Origin": "https://evil.example"})).status_code == 403
    assert (await client.get("/api/v1/cases", headers={"Origin": "https://sb.example"})).status_code == 200


async def test_case_api_returns_real_data(env):
    rt, client = env
    case = await rt.store.new_case("telegram", "tg:1")
    mid = await rt.store.add_message(case["id"], "scammer", "pay now")
    await rt.store.add_message(case["id"], "persona", "which app?")
    await rt.store.add_intel(case["id"], "upi", "x.y@bank", mid)
    await rt.bus.emit(Event(case_id=case["id"], channel="telegram", type="intel.extracted",
                            data={"kind": "upi", "value": "x.y@bank", "message_id": mid, "source": "regex"}))
    other = await rt.store.new_case("call", "call:CA1")
    await _login(client)
    lst = (await client.get("/api/v1/cases", params={"channel": "telegram,api"})).json()
    assert [c["id"] for c in lst["cases"]] == [case["id"]] and lst["cases"][0]["turns"] == 1
    d = (await client.get(f"/api/v1/cases/{case['id']}")).json()
    assert d["turns"] == 1 and d["max_turns"] == 20 and len(d["messages"]) == 2
    assert d["intel"][0]["source"] == "regex" and d["events"][0]["type"] == "intel.extracted"
    assert (await client.get("/api/v1/cases/c_ffffffffffff")).status_code == 404
    assert (await client.get("/api/v1/cases/..%2Fetc")).status_code == 404
    assert (await client.get(f"/api/v1/cases/{other['id']}")).status_code == 200


async def test_assets_served_and_path_safe(env):
    _, client = env
    assert (await client.get("/dashboard/assets/common.js")).status_code == 200
    assert (await client.get("/dashboard/assets/..%2Fpages.py")).status_code == 404


def test_static_files_have_no_sample_values():
    banned = ["+91", "@paytm", "@okaxis", "@ybl", "9000000", "Rahul", "GOLD77", "lorem", "Math.random", "c_0", "CA0"]
    for f in STATIC.iterdir():
        text = f.read_text(encoding="utf-8")
        for b in banned:
            assert b not in text, f"{f.name} contains sample value {b!r}"
        assert not re.search("[\u2014\U0001F300-\U0001FAFF\u2600-\u27BF]", text), f.name
