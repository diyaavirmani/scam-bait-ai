"""Scammer networks: exact matches on normalised identifiers, merged with union-find."""
import csv
import io
import sqlite3

import httpx
import pytest
from fastapi import FastAPI

import app.networks as networks
import app.web as web
import app.web.export as export
from app.config import Settings
from app.events import Bus
from app.models import Event
from app.runtime import Runtime, set_runtime
from app.store import Store

PW = "pw-test-only"


def test_normalise():
    assert networks.normalise("upi", "  Fraudster.Demo@OKAXIS ") == "fraudster.demo@okaxis"
    assert networks.normalise("phone", "+91 90000 00002") == "9000000002"
    assert networks.normalise("phone", "09000000002") == "9000000002"
    assert networks.normalise("bank_account", "0001-2345 6789") == "000123456789"
    assert networks.normalise("url", "HTTPS://Evil.Example/Pay/?ref=abc") == "evil.example/Pay"
    assert networks.normalise("url", "evil.example/pay") == "evil.example/pay"


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    networks._last_sent.clear()
    store = Store(str(tmp_path / "n.db"))
    await store.init()
    bus = Bus(store)
    seen = []
    orig = bus.emit

    async def spy(event):
        seen.append(event)
        return await orig(event)

    bus.emit = spy
    rt = Runtime(settings=Settings(dashboard_password=PW, public_base_url=""), store=store, bus=bus)
    set_runtime(rt)
    a = FastAPI()
    a.include_router(web.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=a), base_url="http://test") as client:
        await client.post("/login", data={"password": PW})
        yield rt, client, seen
    await store.close()


async def _case(rt, ext, items, scam_type="upi_collect"):
    case = await rt.store.new_case("telegram", ext)
    await rt.store.update_case(case["id"], scam_type=scam_type)
    mid = await rt.store.add_message(case["id"], "scammer", "pay now")
    for kind, value in items:
        await rt.store.add_intel(case["id"], kind, value, mid)
        await rt.bus.emit(Event(case_id=case["id"], channel="telegram", type="intel.extracted",
                                data={"kind": kind, "value": value, "message_id": mid, "source": "regex"}))
    return case["id"]


async def test_union_find_groups_and_excludes_loners(env):
    rt, client, seen = env
    a = await _case(rt, "tg:1", [("upi", "fraudster.demo@okaxis")])
    b = await _case(rt, "tg:2", [("upi", " Fraudster.Demo@OKAXIS "), ("phone", "+91 90000 00002")], "kyc_phishing")
    c = await _case(rt, "tg:3", [("phone", "9000000002")])  # shares only a phone with case 2
    d = await _case(rt, "tg:4", [("upi", "loner@ybl"), ("phone", "+91 90000 00009")])
    nets = await networks.compute_networks(rt.store)
    assert len(nets) == 1
    net = nets[0]
    assert set(net["case_ids"]) == {a, b, c} and d not in net["case_ids"]
    assert {(s["field"], s["value"], s["case_count"]) for s in net["shared"]} == {
        ("upi", "fraudster.demo@okaxis", 2), ("phone", "9000000002", 2)}
    assert net["scam_types"] == ["kyc_phishing", "upi_collect"] and net["network_id"] == "net_" + a[2:]
    assert net["first_seen"] <= net["last_seen"]

    # live: network.updated was emitted when case 2 linked to case 1, and again when case 3 joined
    updates = [e for e in seen if e.type == "network.updated"]
    assert [sorted(u.data["case_ids"]) for u in updates] == [sorted([a, b]), sorted([a, b, c])]
    stored = [e for e in await rt.store.events_after(0) if e.type == "network.updated"]
    assert len(stored) == 2  # replayable over SSE

    r = await client.get("/api/networks")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["network_id"] == net["network_id"] and set(body[0]["case_ids"]) == {a, b, c}
    assert set(body[0]) == {"network_id", "case_ids", "shared", "first_seen", "last_seen", "scam_types"}

    rows = list(csv.DictReader(io.StringIO((await client.get(f"/api/v1/cases/{a}/export.csv")).text)))
    assert rows and all(row["network_id"] == net["network_id"] for row in rows)
    rows_d = list(csv.DictReader(io.StringIO((await client.get(f"/api/v1/cases/{d}/export.csv")).text)))
    assert all(row["network_id"] == "" for row in rows_d)
    pack = await export.build_pack(c)
    assert pack["network"]["network_id"] == net["network_id"]
    assert (await client.get(f"/api/v1/cases/{c}/export.pdf")).status_code == 200


async def test_generic_fields_never_link(env):
    rt, _client, _seen = env
    await _case(rt, "tg:5", [("organisation", "SEBI"), ("amount", "10000"), ("ifsc", "ABCD0001234")])
    await _case(rt, "tg:6", [("organisation", "sebi"), ("amount", "10000"), ("ifsc", "ABCD0001234")])
    assert await networks.compute_networks(rt.store) == []


async def test_networks_api_requires_login(env):
    _rt, client, _seen = env
    client.cookies.clear()
    assert (await client.get("/api/networks")).status_code == 401


async def test_old_database_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE intel_items (id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL, kind TEXT NOT NULL,"
        " value TEXT NOT NULL, message_id INTEGER, first_seen TEXT NOT NULL, UNIQUE(case_id, kind, value));"
        "INSERT INTO intel_items (case_id, kind, value, first_seen) VALUES ('c_1', 'phone', '+919000000002', 't');")
    con.commit()
    con.close()
    store = Store(path)
    await store.init()
    try:
        async with store.db.execute("SELECT norm FROM intel_items") as cur:
            assert (await cur.fetchone())[0] == "9000000002"
    finally:
        await store.close()
