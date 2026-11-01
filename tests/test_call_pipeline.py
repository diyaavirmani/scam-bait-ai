"""Call path end to end on the real orchestrator: caller utterances -> per-utterance Decisions -> qwen batches
-> validated intel and verdict -> end_call (idempotent) -> background case report. Models are faked."""
import asyncio

from test_a2_fakes import FakeCerebras, FakeOpenAI, make_store

from app import orchestrator
from app.config import Settings
from app.events import Bus
from app.runtime import Runtime, set_runtime

REPORT = {"summary": "Fake cyber police caller demanded a fine to a UPI ID.", "scam_type": "digital_arrest",
          "modus_operandi": "Aadhaar money laundering threat", "key_points": ["fine via UPI"],
          "suspect_identifiers": [{"kind": "upi", "value": "fakeinvest.demo@okaxis"}], "risk": "high",
          "recommended_action": "Report on 1930 / NCRP"}
LINES = [
    "Hello madam, I am calling from the cyber police, your Aadhaar is linked to a money laundering case.",
    "To clear your name, pay the fine to UPI fakeinvest.demo@okaxis.",
    "My officer number is +91 90000 00001.",
]


class CountingOpenAI(FakeOpenAI):
    def __init__(self):
        super().__init__()
        self.decisions_calls = 0

    async def decisions(self, input, questions, cache_key=None):
        self.decisions_calls += 1
        return {}


async def test_call_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = await make_store(tmp_path)
    try:
        await _run_call(store)
    finally:
        await store.close()  # aiosqlite's worker thread would otherwise keep the test process alive


async def _run_call(store):
    def handler(step, kw):
        if step == "call_batch":
            assert kw["model"] == "qwen-3.8-27b" and kw["reasoning_effort"] == "none"
            return {"is_scam": True, "p_scam": 0.93, "scam_type": "digital_arrest",
                    "intel": [{"kind": "upi", "value": "fakeinvest.demo@okaxis"}],
                    "summary": "Caller posing as cyber police demands a fine to a UPI ID."}
        if step == "report":
            return dict(REPORT)
        raise AssertionError(f"unexpected step {step}")

    cerebras, openai_client = FakeCerebras(handler), CountingOpenAI()
    set_runtime(Runtime(settings=Settings(call_batch_seconds=0), store=store, bus=Bus(store),
                        cerebras=cerebras, openai=openai_client))
    orchestrator.reset_state()
    case = await store.get_or_create_case("call", "call:CA1")
    await orchestrator.handle_call_transcript(case["id"], "persona", "Hello? Who is this?", True)
    for line in LINES:
        await orchestrator.handle_call_transcript(case["id"], "caller", line, True)
    await orchestrator.end_call(case["id"])
    await orchestrator.end_call(case["id"])  # idempotent: Twilio stop, socket close and status callback can all fire
    for _ in range(100):
        if [e for e in await store.list_evidence(case["id"]) if e["kind"] == "report"]:
            break
        await asyncio.sleep(0.05)

    roles = [m["role"] for m in await store.list_messages(case["id"])]
    assert roles.count("scammer") == 3 and roles.count("persona") == 1
    intel = {(i["kind"], i["value"]) for i in await store.list_intel(case["id"])}
    assert ("upi", "fakeinvest.demo@okaxis") in intel and ("phone", "+919000000001") in intel
    assert not any(k == "bank_account" for k, _ in intel)  # the phone is never also a bank account
    final = await store.get_case(case["id"])
    assert final["status"] == "closed" and final["verdict"] == "scam"
    assert openai_client.decisions_calls == 3  # one Decisions check per caller utterance
    steps = [c["step"] for c in cerebras.calls]
    assert "call_batch" in steps and steps.count("report") == 1
    reports = [e for e in await store.list_evidence(case["id"]) if e["kind"] == "report"]
    assert len(reports) == 1
    events = await store.events_for_case(case["id"])
    assert any(e.type == "scam.detected" and e.channel == "call" for e in events)
    assert any(e.type == "case.summary" and e.data.get("report") for e in events)
