"""Side-by-side dashboard (/alt): auth, real-data snapshot API, export hashes and NCRP fields, no mock data."""
import hashlib
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.events import Bus
from app.models import Event
from app.runtime import Runtime, set_runtime
from app.store import Store
from app.web.auth import COOKIE_NAME, make_cookie
from app.web_alt import NCRP_BANNED, router

STATIC = Path("app/web_alt/static")
PASSWORD = "test-dash-pass"


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", PASSWORD)
    store = Store(str(tmp_path / "alt.db"))
    await store.init()
    bus = Bus(store)
    set_runtime(Runtime(settings=Settings(), store=store, bus=bus))
    case = await store.new_case("telegram", "tg:42")
    cid = case["id"]
    m1 = await store.add_message(cid, "scammer", "Hello sir, I am Rahul Mehta from Mumbai, SEBI registered advisor. Your referral code is GOLD77.")
    await store.add_message(cid, "persona", "Who is this? I do not understand.")
    m3 = await store.add_message(cid, "scammer", "Pay to UPI fakeinvest.demo@okaxis and send screenshot. <script>alert(1)</script>")
    await store.add_intel(cid, "upi", "fakeinvest.demo@okaxis", m3)
    await store.add_intel(cid, "phone", "+919000000001", m1)
    for ev in [
        Event(case_id=cid, channel="telegram", type="scam.detected",
              data={"stage": "fast", "p_cerebras": 0.91, "p_decisions": None, "verdict": "scam", "decisions_available": True}),
        Event(case_id=cid, channel="telegram", type="scam.detected",
              data={"stage": "final", "p_cerebras": 0.91, "p_decisions": 0.88, "verdict": "scam", "decided_by": "cerebras"}),
        Event(case_id=cid, channel="telegram", type="metrics.speed",
              data={"step": "persona", "provider": "cerebras", "model": "gpt-oss-120b", "ms": 640, "tokens_per_s": 2900}),
        Event(case_id=cid, channel="telegram", type="case.summary",
              data={"summary": "Investment scam: fake SEBI advisor asks for UPI payment.", "status": "engaged", "final": False}),
    ]:
        await bus.emit(ev)
    await store.update_case(cid, verdict="scam", status="engaged", scam_type="investment_trading")
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    yield client, store, cid
    await store.close()


def authed(client):
    client.cookies.set(COOKIE_NAME, make_cookie(PASSWORD))
    return client


def test_pages_and_api_require_login(env):
    client, _, cid = env
    r = client.get("/alt/chats", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert client.get("/alt/api/cases").status_code == 401
    assert client.get(f"/alt/api/cases/{cid}/export.csv").status_code == 401


def test_pages_render_with_panels(env):
    client, _, _ = env
    authed(client)
    html = client.get("/alt/chats").text
    for panel in ["cases", "thread", "detect", "casebox", "summary", "intel", "speed", "limits"]:
        assert f'id="{panel}"' in html
    for page in ["calls", "cases", "export"]:
        assert client.get(f"/alt/{page}").status_code == 200
    assert client.get("/alt/nope").status_code == 404


def test_snapshot_api_is_real_data(env):
    client, _, cid = env
    authed(client)
    cases = client.get("/alt/api/cases?channel=chat").json()["cases"]
    assert [c["id"] for c in cases] == [cid] and cases[0]["turn"] == 2 and cases[0]["max_turns"] == 20
    assert client.get("/alt/api/cases?channel=call").json()["cases"] == []
    v = client.get(f"/alt/api/cases/{cid}").json()
    assert [m["role"] for m in v["messages"]] == ["scammer", "persona", "scammer"]
    upi = next(i for i in v["intel"] if i["kind"] == "upi")
    assert "fakeinvest.demo@okaxis" in upi["source_text"]
    stages = [e["data"]["stage"] for e in v["events"] if e["type"] == "scam.detected"]
    assert stages == ["fast", "final"] and v["last_event_id"] > 0
    assert client.get("/alt/api/cases/../../etc").status_code in (400, 404)
    assert client.get("/alt/api/cases/c_zzzz").status_code == 400
    assert client.get("/alt/api/stream-cursor").json()["last_id"] == v["last_event_id"]


def test_export_hashes_match_evidence_and_ncrp_rules(env):
    client, store, cid = env
    authed(client)
    res = client.post(f"/alt/api/cases/{cid}/export").json()
    for kind in ("csv", "pdf", "transcript"):
        body = Path(res["paths"][kind]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == res["hashes"][f"{kind}_sha256"]
    assert Path(res["paths"]["pdf"]).read_bytes().startswith(b"%PDF")
    details = res["ncrp"]["incident_details"]
    assert len(details) >= 200 and not any(ch in details for ch in NCRP_BANNED)
    assert res["ncrp"]["suspect_upi_ids"] == "fakeinvest.demo@okaxis"
    assert res["ncrp"]["suspect_mobile_numbers"] == "+919000000001"
    assert "IST" in res["ncrp"]["incident_datetime_ist"]
    csv_text = Path(res["paths"]["csv"]).read_text(encoding="utf-8")
    assert csv_text.count("\n") == 3  # header + one row per intel item
    r = client.get(f"/alt/api/cases/{cid}/export.csv")
    assert r.status_code == 200 and r.headers["x-sha256"] == hashlib.sha256(r.content).hexdigest()


def test_static_has_no_mock_data_or_banned_chars_or_html_injection():
    banned = re.compile("[\u2014\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F000-\U0001F2FF\uFE0F]")
    for f in STATIC.iterdir():
        text = f.read_text(encoding="utf-8")
        assert not banned.search(text), f
        for mock in ("+91", "@paytm", "Math.random", "HDFC", "9876"):
            assert mock not in text, (f, mock)
    js = (STATIC / "alt.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "dangerously" not in js
