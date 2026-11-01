"""Milestone 07: Decisions parser on the docs-derived fixture, unavailable latch, errors never give not-scam."""
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.detection import decisions as dec
from app.providers import ProviderError
from app.runtime import Runtime, set_runtime

FIXTURE = Path(__file__).parent / "fixtures" / "decisions_docs_example.json"


class FakeOpenAI:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def decisions(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def reset():
    dec._reset_status()
    yield
    dec._reset_status()


def install(fake):
    set_runtime(Runtime(settings=Settings(), store=None, bus=None, openai=fake))


def test_parse_docs_example():
    data = json.loads(FIXTURE.read_text())
    assert data["_note"].startswith("docs-derived example")
    out = dec.parse_decisions(data)
    assert out["p_scam"] == 0.92 and out["scam_type"] == "investment_trading" and out["risk"] == "high"
    assert out["tactics"]["promises_assured_returns"] == 0.95
    assert "credential_request" not in out["tactics"]  # refusal skipped


def test_parse_tolerant_variants():
    out = dec.parse_decisions({"answers": [
        {"type": "choice", "name": "scam_type", "probabilities": [{"value": "upi_collect", "probability": 0.7},
                                                                  {"value": "other", "probability": 0.3}]},
        {"type": "score", "name": "risk", "score": 2.8},
        {"type": "predicate", "name": "is_scam", "probability": "0.4"},
    ]})
    assert out["scam_type"] == "upi_collect" and out["risk"] == "critical" and out["p_scam"] == 0.4
    assert dec.parse_decisions({})["p_scam"] is None


async def test_verdict_from_fixture_and_request():
    fake = FakeOpenAI(json.loads(FIXTURE.read_text()))
    install(fake)
    v = await dec.decisions_verdict([{"role": "scammer", "text": "30% weekly returns"}], "c_1")
    assert v.source == "decisions" and v.available and v.is_scam and v.p_scam == 0.92
    assert v.scam_type == "investment_trading" and v.risk == "high"
    kw = fake.calls[0]
    assert kw["questions"] is dec.QUESTIONS and kw["cache_key"] == dec.CACHE_KEY
    assert "DATA" in kw["input"] and "30% weekly returns" in kw["input"]
    names = {q["name"] for q in dec.QUESTIONS}
    assert {"is_scam", "scam_type", "risk", "credential_request"} <= names
    assert "not_a_scam" in [c["value"] for c in dec.QUESTIONS[1]["choices"]]


async def test_unavailable_latches_and_skips_calls():
    fake = FakeOpenAI(error=ProviderError("unavailable", "decisions: HTTP 403"))
    install(fake)
    v1 = await dec.decisions_verdict([{"role": "scammer", "text": "x"}], "c_1")
    v2 = await dec.decisions_verdict([{"role": "scammer", "text": "x"}], "c_1")
    assert not v1.available and not v2.available and v2.error == "unavailable"
    assert len(fake.calls) == 1
    st = dec.decisions_status()
    assert st["available"] is False and "403" in st["reason"]


async def test_outage_does_not_latch():
    fake = FakeOpenAI(error=ProviderError("outage", "decisions: HTTP 500"))
    install(fake)
    v = await dec.decisions_verdict([{"role": "scammer", "text": "x"}], "c_1")
    assert not v.available and v.error == "outage" and v.is_scam is None
    assert dec.decisions_status()["available"] is True


async def test_missing_is_scam_is_unavailable():
    install(FakeOpenAI({"answers": [{"type": "refusal", "name": "is_scam"}]}))
    v = await dec.decisions_verdict([{"role": "scammer", "text": "x"}], "c_1")
    assert v.available is False and v.error == "bad_output"
