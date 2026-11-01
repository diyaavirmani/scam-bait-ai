"""Track C, commit 18: open dashboard pages (no login), case API, no mock data in the static files."""
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

DIST = Path(web.__file__).parent / "dist"
SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"


def _app():
    a = FastAPI()
    a.include_router(events.router)
    a.include_router(web.router)
    return a


@pytest.fixture
async def env(tmp_path):
    store = Store(str(tmp_path / "w.db"))
    await store.init()
    rt = Runtime(settings=Settings(public_base_url="https://sb.example"), store=store, bus=Bus(store))
    set_runtime(rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as client:
        yield rt, client
    await store.close()


async def _login(client):
    """The dashboard is open; kept so the tests below read the same."""
    return None


@pytest.mark.parametrize("path", ["/", "/chats", "/calls", "/intel", "/networks", "/cases", "/export", "/system"])
async def test_pages_open_without_login(env, path):
    _, client = env
    r = await client.get(path)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and 'id="root"' in r.text


@pytest.mark.parametrize("path", ["/api/v1/cases", "/api/networks"])
async def test_api_open_without_login(env, path):
    _, client = env
    assert (await client.get(path)).status_code == 200


async def test_login_routes_removed(env):
    _, client = env
    assert (await client.get("/login")).status_code == 404
    assert (await client.post("/login", data={"password": "x"})).status_code in (404, 405)


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
    name = next((DIST / "assets").glob("*.js")).name
    r = await client.get(f"/assets/{name}")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert (await client.get("/assets/..%2F..%2Fpages.py")).status_code == 404
    assert (await client.get("/assets/nope.js")).status_code == 404


def test_dashboard_has_no_sample_values_or_banned_chars():
    banned = ["+91", "@paytm", "@okaxis", "@ybl", "9000000", "Rahul", "GOLD77", "lorem", "Math.random",
              "INITIAL_", "MOCK_", "c_0", "CA0"]
    files = [f for f in SRC.rglob("*") if f.is_file()]
    assert files
    for f in files:
        text = f.read_text(encoding="utf-8")
        for b in banned:
            assert b not in text, f"{f.name} contains sample value {b!r}"
    for f in [DIST / "index.html", *(DIST / "assets").iterdir()]:
        assert not re.search("[\u2014\U0001F300-\U0001FAFF\u2600-\u27BF]", f.read_text(encoding="utf-8")), f.name
