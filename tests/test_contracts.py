"""Contract modules import and expose the agreed names."""
import importlib

import pytest

from app.models import SESSION_ID_RE, Event, HoneypotRequest, JudgeResponse


@pytest.mark.parametrize("mod", [
    "app.store", "app.events", "app.providers", "app.providers.limiter", "app.providers.cerebras",
    "app.providers.openai_client", "app.detection.prefilter", "app.detection.flag", "app.detection.decisions",
    "app.detection.ensemble", "app.persona.persona", "app.persona.memory", "app.persona.guard",
    "app.persona.language", "app.extraction", "app.orchestrator", "app.report", "app.runtime",
])
def test_module_imports(mod):
    importlib.import_module(mod)


def test_session_id_rule():
    assert SESSION_ID_RE.match("telegram_123-abc")
    for bad in ["../x", "a/b", "x" * 65, "", "a b"]:
        assert not SESSION_ID_RE.match(bad)


def test_event_defaults_utc():
    e = Event(channel="api", type="message.received")
    assert e.ts.endswith("+00:00")


def test_honeypot_contract_shape():
    req = HoneypotRequest(sessionId="s1", message={"sender": "scammer", "text": "hi", "timestamp": 1})
    assert req.conversationHistory == []
    resp = JudgeResponse(reply="ok", meta={"agentState": "engaging", "sessionStatus": "active",
                                          "persona": "confused_customer", "turn": 1, "agentNotes": "x"})
    assert resp.status == "success" and resp.meta.degraded is False
