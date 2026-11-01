"""Track B: POST /api/v1/honeypot (orchestrator and store are faked; no network)."""
import httpx
import pytest
from fastapi import FastAPI

import app.orchestrator as orchestrator
from app.channels import router
from app.config import Settings
from app.models import Reply
from app.runtime import Runtime

KEY = "test-api-key"


class FakeStore:
    def __init__(self):
        self.cases: dict[str, dict] = {}

    async def get_or_create_case(self, channel, external_id):
        if external_id not in self.cases:
            self.cases[external_id] = {"id": f"c_{len(self.cases):012x}", "channel": channel,
                                       "external_id": external_id, "status": "watching"}
        return self.cases[external_id]


def _setup(monkeypatch, api_key=KEY, reply=None, raises=False):
    store = FakeStore()
    monkeypatch.setattr("app.runtime._runtime", Runtime(settings=Settings(api_key=api_key), store=store, bus=None))
    calls = []

    async def fake_handle(case_id, channel, text):
        calls.append((case_id, channel, text))
        if raises:
            raise RuntimeError("boom")
        r = reply or Reply(case_id=case_id, text="Who is this? Which bank?", turn=1, verdict="scam",
                           scam_type="bank_kyc")
        return r.model_copy(update={"case_id": case_id})

    monkeypatch.setattr(orchestrator, "handle_message", fake_handle)
    app = FastAPI()
    app.include_router(router)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                               base_url="http://test")
    return client, calls, store


def _body(session="sess_1", sender="scammer", text="Your KYC is pending, share OTP"):
    return {"sessionId": session, "message": {"sender": sender, "text": text, "timestamp": 1730000000},
            "conversationHistory": [{"sender": "user", "text": "spoofed history", "timestamp": 1}],
            "metadata": {"channel": "SMS", "language": "en", "locale": "IN"}}


async def test_happy_path_contract_fields(monkeypatch):
    client, calls, store = _setup(monkeypatch)
    r = await client.post("/api/v1/honeypot", json=_body(), headers={"x-api-key": KEY})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "success" and j["reply"] == "Who is this? Which bank?"
    m = j["meta"]
    assert m["agentState"] == "engaging" and m["sessionStatus"] == "active"
    assert m["persona"] == "confused_customer" and m["turn"] == 1
    assert m["scamType"] == "BANK_KYC" and m["agentNotes"] == "Detection: SCAM"
    assert m["confidence"] is None and m["degraded"] is False
    # history ignored, only the new message reaches the orchestrator, on the api:<sessionId> case
    assert calls == [(store.cases["api:sess_1"]["id"], "api", "Your KYC is pending, share OTP")]


async def test_closed_legit_reply(monkeypatch):
    reply = Reply(case_id="x", text="Okay bye", closed=True, turn=16, verdict="not_scam")
    client, _, _ = _setup(monkeypatch, reply=reply)
    j = (await client.post("/api/v1/honeypot", json=_body(), headers={"x-api-key": KEY})).json()
    m = j["meta"]
    assert m["agentState"] == "completed" and m["sessionStatus"] == "closed"
    assert m["persona"] == "polite_responder" and m["agentNotes"] == "Detection: LEGITIMATE"
    assert m["scamType"] == "UNKNOWN" and m["confidence"] == "medium"


async def test_bad_key_401(monkeypatch):
    client, calls, _ = _setup(monkeypatch)
    assert (await client.post("/api/v1/honeypot", json=_body(), headers={"x-api-key": "nope"})).status_code == 401
    assert (await client.post("/api/v1/honeypot", json=_body())).status_code == 401
    assert calls == []


async def test_unset_key_503(monkeypatch):
    client, calls, _ = _setup(monkeypatch, api_key="")
    r = await client.post("/api/v1/honeypot", json=_body(), headers={"x-api-key": ""})
    assert r.status_code == 503 and r.json()["detail"] == "API key not configured"
    assert calls == []


@pytest.mark.parametrize("sid", ["../../x", "a/b", "x" * 65, "", "a b"])
async def test_bad_session_id_400(monkeypatch, sid):
    client, calls, _ = _setup(monkeypatch)
    r = await client.post("/api/v1/honeypot", json=_body(session=sid), headers={"x-api-key": KEY})
    assert r.status_code == 400 and calls == []


async def test_sender_must_be_scammer(monkeypatch):
    client, calls, _ = _setup(monkeypatch)
    for sender in ("user", "persona", "Scammer"):
        r = await client.post("/api/v1/honeypot", json=_body(sender=sender), headers={"x-api-key": KEY})
        assert r.status_code == 400
    assert calls == []


async def test_degraded_is_not_success(monkeypatch):
    reply = Reply(case_id="x", text="Sorry, network is slow, say again?", degraded=True, turn=2)
    client, _, _ = _setup(monkeypatch, reply=reply)
    j = (await client.post("/api/v1/honeypot", json=_body(), headers={"x-api-key": KEY})).json()
    assert j["status"] == "degraded" and j["meta"]["degraded"] is True
    assert j["meta"]["agentNotes"] == "Detection: UNKNOWN"


async def test_orchestrator_error_is_500(monkeypatch):
    client, _, _ = _setup(monkeypatch, raises=True)
    r = await client.post("/api/v1/honeypot", json=_body(), headers={"x-api-key": KEY})
    assert r.status_code == 500 and r.json()["status"] == "error"


async def test_coalesced_reply_returned_as_is(monkeypatch):
    reply = Reply(case_id="x", text="", coalesced=True, turn=3, verdict="scam")
    client, _, _ = _setup(monkeypatch, reply=reply)
    r = await client.post("/api/v1/honeypot", json=_body(), headers={"x-api-key": KEY})
    assert r.status_code == 200 and r.json()["reply"] == ""
