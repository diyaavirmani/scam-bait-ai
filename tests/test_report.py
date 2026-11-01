import hashlib
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.models import CallMetrics
from app.providers import ProviderError
from app.report import write_case_report
from app.runtime import Runtime, set_runtime
from app.store import Store

REPORT = {"summary": "Investment scam: fake SEBI advisor asked for UPI payment.", "scam_type": "investment_trading",
          "modus_operandi": "VIP group, guaranteed returns", "key_points": ["asked for 10,000"],
          "suspect_identifiers": [{"kind": "upi", "value": "fakeinvest.demo@okaxis"}], "risk": "high",
          "recommended_action": "Report on 1930 / NCRP"}


class Bus:
    def __init__(self):
        self.events = []

    async def emit(self, e):
        self.events.append(e)
        return e


class Cerebras:
    def __init__(self, exc=None):
        self.exc, self.calls = exc, []

    async def chat_json(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return dict(REPORT), CallMetrics(step="report", provider="cerebras", model=kw["model"], ms=5)


class OpenAI:
    def __init__(self):
        self.calls = 0

    async def responses_json(self, **kw):
        self.calls += 1
        return dict(REPORT)


@pytest.fixture
async def rt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = Store(str(tmp_path / "r.db"))
    await store.init()
    case = await store.new_case("telegram", "tg:9")
    m = await store.add_message(case["id"], "scammer", "Pay to UPI fakeinvest.demo@okaxis")
    await store.add_intel(case["id"], "upi", "fakeinvest.demo@okaxis", m)
    runtime = Runtime(settings=Settings(), store=store, bus=Bus(), cerebras=Cerebras(), openai=OpenAI())
    set_runtime(runtime)
    yield runtime, case
    await store.close()


async def test_report_written_hashed_and_announced(rt):
    runtime, case = rt
    report = await write_case_report(case["id"])
    call = runtime.cerebras.calls[0]
    assert call["model"] == runtime.settings.persona_model and call["priority"] == 2  # background, pinned model
    path = Path("out/reports") / case["id"] / "report.json"
    ev = (await runtime.store.list_evidence(case["id"]))[0]
    assert ev["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (await runtime.store.get_case(case["id"]))["summary"] == REPORT["summary"]
    last = runtime.bus.events[-1]
    assert last.type == "case.summary" and last.data["final"] and last.data["report"]["generated_by"] == "cerebras"
    assert json.loads(path.read_text())["risk"] == "high" and report["summary"]


async def test_outage_uses_responses_fallback(rt):
    runtime, case = rt
    runtime.cerebras = Cerebras(ProviderError("outage", "503"))
    report = await write_case_report(case["id"])
    assert runtime.openai.calls == 1 and report["generated_by"] == "openai_responses_fallback"


async def test_rate_limit_never_falls_back(rt):
    runtime, case = rt
    runtime.cerebras = Cerebras(ProviderError("rate_limit_quota", "tokens per day"))
    assert await write_case_report(case["id"]) == {}
    assert runtime.openai.calls == 0
    assert runtime.bus.events[-1].data["report_error"] == "rate_limit_quota"
