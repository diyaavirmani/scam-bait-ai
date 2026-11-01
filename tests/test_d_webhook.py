"""Track D, milestone 14: signed Twilio webhooks, TwiML, one-time stream tokens, status callbacks."""
import importlib.util
import pathlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

import app.orchestrator as orch
from app.config import Settings
from app.runtime import Runtime, set_runtime
from app.voice import router as voice_router, state

AUTH = "test-auth-token"
BASE = "https://scambait-test.example"


class FakeStore:
    def __init__(self):
        self.cases = {}

    async def get_or_create_case(self, channel, external_id):
        if external_id not in self.cases:
            self.cases[external_id] = {"id": f"c_{len(self.cases) + 1:012x}", "channel": channel,
                                       "external_id": external_id, "status": "watching"}
        return self.cases[external_id]


class FakeBus:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)
        return event

    def of(self, t):
        return [e for e in self.events if e.type == t]


def _runtime(token=AUTH, base=BASE):
    rt = Runtime(settings=Settings(twilio_auth_token=token, public_base_url=base, openai_api_key="test-key"),
                 store=FakeStore(), bus=FakeBus())
    set_runtime(rt)
    return rt


@pytest.fixture
def rt():
    state.reset()
    return _runtime()


@pytest.fixture
def ended(monkeypatch):
    calls = []

    async def fake_end_call(case_id):
        calls.append(case_id)
    monkeypatch.setattr(orch, "end_call", fake_end_call)
    return calls


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(voice_router)
    return TestClient(app)


def _post(client, path, params, url=None, token=AUTH, sig=None):
    signed = url or BASE + path
    sig = sig if sig is not None else RequestValidator(token).compute_signature(signed, params)
    return client.post(path, data=params, headers={"X-Twilio-Signature": sig})


FORM = {"CallSid": "CA_TEST_0001", "From": "+919000001234", "To": "+15550000000", "CallStatus": "ringing"}


def test_get_incoming_is_readiness_text(rt, client):
    r = client.get("/voice/incoming")
    assert r.status_code == 200 and "ready" in r.text.lower()


def test_valid_signature_returns_stream_twiml(rt, client):
    r = _post(client, "/voice/incoming", FORM)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    body = r.text
    assert '<Stream url="wss://scambait-test.example/voice/stream"' in body
    assert 'statusCallback="https://scambait-test.example/voice/stream-status"' in body
    token = re.search(r'<Parameter name="token" value="([^"]+)"/>', body).group(1)
    case_id = re.search(r'<Parameter name="case_id" value="([^"]+)"/>', body).group(1)
    assert len(token) >= 24 and case_id.startswith("c_")
    assert rt.store.cases["call:CA_TEST_0001"]["id"] == case_id
    ev = rt.bus.of("call.status")
    assert len(ev) == 1 and ev[0].channel == "call" and ev[0].case_id == case_id
    assert ev[0].data["status"] == "ringing" and ev[0].data["call_sid"] == "CA_TEST_0001"
    assert ev[0].data["from_masked"] == "***1234" and "9000001234" not in str(ev[0].data)


def test_host_header_is_never_used(rt, client):
    r = client.post("/voice/incoming", data=FORM, headers={
        "Host": "evil.example", "X-Twilio-Signature": RequestValidator(AUTH).compute_signature(
            BASE + "/voice/incoming", FORM)})
    assert r.status_code == 200 and "evil.example" not in r.text


def test_invalid_signature_403(rt, client):
    assert _post(client, "/voice/incoming", FORM, sig="bm90LWEtc2lnbmF0dXJl").status_code == 403
    assert _post(client, "/voice/incoming", FORM, token="wrong-token").status_code == 403
    assert _post(client, "/voice/incoming", FORM, url="https://other.example/voice/incoming").status_code == 403
    assert client.post("/voice/incoming", data=FORM).status_code == 403  # no header at all
    assert rt.bus.events == []


@pytest.mark.parametrize("token,base", [("", BASE), (AUTH, "")])
def test_unset_token_or_public_url_403(client, token, base):
    state.reset()
    _runtime(token=token, base=base)
    assert _post(client, "/voice/incoming", FORM).status_code == 403


def test_token_single_use_and_bound_to_call_sid(rt):
    t1 = state.issue_token("CA_A")
    assert state.consume_token(t1, "CA_B") is False  # wrong call: rejected and burnt
    assert state.consume_token(t1, "CA_A") is False
    t2 = state.issue_token("CA_A")
    assert state.consume_token(t2, "CA_A") is True
    assert state.consume_token(t2, "CA_A") is False  # single use
    t3 = state.issue_token("CA_A", ttl=-1)
    assert state.consume_token(t3, "CA_A") is False  # expired
    assert state.consume_token(None, "CA_A") is False


def test_status_completed_ends_call_once(rt, client, ended):
    _post(client, "/voice/incoming", FORM)
    case_id = rt.store.cases["call:CA_TEST_0001"]["id"]
    done = dict(FORM, CallStatus="completed")
    assert _post(client, "/voice/status", done).status_code == 204
    assert _post(client, "/voice/status", done).status_code == 204
    assert ended == [case_id]
    statuses = [e.data["status"] for e in rt.bus.of("call.status")]
    assert statuses == ["ringing", "completed", "ended", "completed"]


def test_status_does_not_end_while_bridge_active(rt, client, ended):
    _post(client, "/voice/incoming", FORM)
    state.get_call("CA_TEST_0001").bridge_active = True
    assert _post(client, "/voice/status", dict(FORM, CallStatus="completed")).status_code == 204
    assert ended == []


def test_stream_status_signed_and_emitted(rt, client, ended):
    _post(client, "/voice/incoming", FORM)
    form = {"CallSid": "CA_TEST_0001", "StreamSid": "MZ_TEST", "StreamEvent": "stream-started"}
    assert _post(client, "/voice/stream-status", form).status_code == 204
    assert _post(client, "/voice/stream-status", form, sig="AAAA").status_code == 403
    assert rt.bus.of("call.status")[-1].data["status"] == "stream-started"
    err = dict(form, StreamEvent="stream-error", StreamError="boom")
    assert _post(client, "/voice/stream-status", err).status_code == 204
    st = [e.data for e in rt.bus.of("call.status")]
    assert {"status": "error", "detail": "boom"}.items() <= st[-2].items() and st[-1]["status"] == "ended"
    assert len(ended) == 1


def test_simulate_script_signature_is_accepted(rt, client):
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "simulate_voice_webhook.py"
    spec = importlib.util.spec_from_file_location("simulate_voice_webhook", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    params, headers = mod.build_request(BASE + "/voice/incoming", AUTH)
    r = client.post("/voice/incoming", data=params, headers=headers)
    assert r.status_code == 200 and "<Connect>" in r.text
    assert mod.main(["--url", "https://example.com/voice/incoming"]) == 2  # refuses external targets
