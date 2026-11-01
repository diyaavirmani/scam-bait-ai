"""Track C, commit 19: CSV and PDF evidence export with SHA-256 recorded in the evidence table."""
import csv
import hashlib
import io
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import app.web as web
import app.web.export as export
from app.config import Settings
from app.events import Bus
from app.models import Event
from app.runtime import Runtime, set_runtime
from app.store import Store

PW = "pw-test-only"
HINDI = "नमस्ते बेटा"  # Devanagari, not Latin-1


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    store = Store(str(tmp_path / "x.db"))
    await store.init()
    rt = Runtime(settings=Settings(dashboard_password=PW, public_base_url=""), store=store, bus=Bus(store))
    set_runtime(rt)
    a = FastAPI()
    a.include_router(web.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=a), base_url="http://test") as client:
        await client.post("/login", data={"password": PW})
        yield rt, client
    await store.close()


async def _case(rt):
    s = rt.store
    case = await s.new_case("telegram", "tg:42")
    cid = case["id"]
    m1 = await s.add_message(cid, "scammer", "Hello, I am from the bank.")
    await s.add_message(cid, "persona", HINDI)
    m2 = await s.add_message(cid, "scammer", "Pay to UPI test.user@okfake now! Mail x@y.example")
    await rt.bus.emit(Event(case_id=cid, channel="telegram", type="scam.detected", data={
        "stage": "final", "p_cerebras": 0.9, "p_decisions": 0.8, "verdict": "scam", "scam_type": "kyc",
        "risk": "high", "decisions_available": False, "decided_by": "cerebras", "recheck": False}))
    for kind, value in [("upi", "test.user@okfake"), ("email", "x@y.example"), ("url", "https://a.example/x")]:
        await s.add_intel(cid, kind, value, m2)
        await rt.bus.emit(Event(case_id=cid, channel="telegram", type="intel.extracted",
                                data={"kind": kind, "value": value, "message_id": m2, "source": "regex"}))
    await s.update_case(cid, summary="KYC #scam: pay $10 @ UPI | urgent! it's `bad` ~ ^*", verdict="scam", scam_type="kyc")
    await rt.bus.emit(Event(case_id=cid, channel="telegram", type="case.summary",
                            data={"summary": "x", "status": "closed", "final": True, "report": {"title": "KYC scam " + HINDI}}))
    return cid, m1


async def test_csv_export_hash_matches_evidence_and_ncrp_fields(env):
    rt, client = env
    cid, _ = await _case(rt)
    r = await client.get(f"/api/v1/cases/{cid}/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    body = r.content
    assert r.headers["x-sha256"] == _sha(body)
    ev = {e["kind"]: e for e in await rt.store.list_evidence(cid)}
    assert ev["csv"]["sha256"] == _sha(body) == _sha(Path(ev["csv"]["path"]).read_bytes())
    assert ev["transcript"]["sha256"] == _sha(Path(ev["transcript"]["path"]).read_bytes())
    assert HINDI in Path(ev["transcript"]["path"]).read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
    assert len(rows) == 3 and {r["intel_kind"] for r in rows} == {"upi", "email", "url"}
    details = rows[0]["incident_details"]
    assert len(details) >= 200
    assert not set(details) & set("#$@^*`'~|!’")
    assert rows[0]["suspect_upi"] == "test.user@okfake" and rows[0]["suspect_email"] == "x@y.example"
    assert rows[0]["suspect_urls"] == "https://a.example/x" and rows[0]["case_id"] == cid
    assert rows[0]["incident_datetime_ist"].endswith("IST") and rows[0]["generated_at_ist"].endswith("IST")
    assert rows[0]["intel_source_message"].startswith("Pay to UPI")


async def test_pdf_export_hashes_match_evidence(env):
    rt, client = env
    cid, _ = await _case(rt)
    r = await client.get(f"/api/v1/cases/{cid}/export.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    ev = {e["kind"]: e for e in await rt.store.list_evidence(cid)}
    assert ev["pdf"]["sha256"] == r.headers["x-sha256"] == _sha(r.content) == _sha(Path(ev["pdf"]["path"]).read_bytes())
    assert r.headers["x-csv-sha256"] == ev["csv"]["sha256"] == _sha(Path(ev["csv"]["path"]).read_bytes())
    assert r.headers["x-transcript-sha256"] == ev["transcript"]["sha256"]
    assert Path(ev["pdf"]["path"]).parent.name == cid


async def test_pdf_without_unicode_font_transliterates(env, monkeypatch):
    rt, _ = env
    cid, _ = await _case(rt)
    monkeypatch.setattr(export, "_find_font", lambda: None)
    pack = await export.build_pack(cid)
    pdf = export.render_pdf(pack, "a" * 64, "b" * 64)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000


def test_details_padding_and_csv_injection_guard():
    d = export.incident_details({"id": "c_x", "channel": "api", "summary": "Short! #1"}, [], 0)
    assert len(d) >= 200 and "!" not in d and "#" not in d
    assert export._csv_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert export._csv_cell("+919000000001") == "+919000000001"


async def test_export_unknown_case_404(env):
    _, client = env
    assert (await client.get("/api/v1/cases/c_ffffffffffff/export.csv")).status_code == 404
    assert (await client.get("/api/v1/cases/nope/export.pdf")).status_code == 404


async def test_export_requires_login(env):
    rt, client = env
    cid, _ = await _case(rt)
    client.cookies.clear()
    for ext in ("csv", "pdf"):
        assert (await client.get(f"/api/v1/cases/{cid}/export.{ext}")).status_code == 401
    assert await rt.store.list_evidence(cid) == []
