"""Milestone 08: E2 bands, errors never not_scam, on_fast fires before Decisions finishes, recheck."""
import asyncio
import time

import pytest

from app.detection import decisions as dec
from app.detection import ensemble
from app.models import Verdict

CFG = {"rule": "E2", "lo": 0.2, "hi": 0.8, "decisions_threshold": 0.5}


def cer(p, scam_type="investment_trading", risk="high"):
    return Verdict(source="cerebras", is_scam=p >= 0.5, p_scam=p, scam_type=scam_type, risk=risk)


def deci(p, scam_type="upi_collect", risk="critical"):
    return Verdict(source="decisions", is_scam=p >= 0.5, p_scam=p, scam_type=scam_type, risk=risk)


DOWN_C = Verdict(source="cerebras", available=False, error="outage")
DOWN_D = Verdict(source="decisions", available=False, error="unavailable")


@pytest.fixture(autouse=True)
def reset():
    dec._reset_status()
    yield
    dec._reset_status()


def test_config_file_loads():
    cfg = ensemble.load_config()
    assert cfg["rule"] == "E2" and cfg["lo"] == 0.2 and cfg["hi"] == 0.8 and cfg["decisions_threshold"] == 0.5
    assert ensemble.load_config() is cfg  # cached


def test_cerebras_confident_low_and_high():
    lowv = ensemble.combine(cer(0.1, "not_a_scam", "none"), deci(0.9), 0.0, CFG)
    assert lowv.verdict == "not_scam" and lowv.decided_by == "cerebras" and lowv.p_decisions == 0.9
    highv = ensemble.combine(cer(0.95), deci(0.1, "not_a_scam", "none"), 0.0, CFG)
    assert highv.verdict == "scam" and highv.decided_by == "cerebras" and highv.scam_type == "investment_trading"
    assert highv.stage == "final" and highv.p_cerebras == 0.95


def test_band_goes_to_decisions():
    v = ensemble.combine(cer(0.5, "other"), deci(0.7), 0.0, CFG)
    assert v.verdict == "scam" and v.decided_by == "decisions" and v.scam_type == "upi_collect"
    assert v.risk == "critical"
    v = ensemble.combine(cer(0.6), deci(0.3, "not_a_scam", "low"), 0.0, CFG)
    assert v.verdict == "not_scam" and v.decided_by == "decisions" and v.scam_type == "not_a_scam"


def test_band_without_decisions_falls_back_to_cerebras_band():
    v = ensemble.combine(cer(0.6), DOWN_D, 0.0, CFG)
    assert v.verdict == "scam" and v.decided_by == "cerebras_band" and v.decisions_available is False
    v = ensemble.combine(cer(0.3, "not_a_scam"), DOWN_D, 0.0, CFG)
    assert v.verdict == "not_scam" and v.decided_by == "cerebras_band"


def test_cerebras_down_decisions_decides():
    v = ensemble.combine(DOWN_C, deci(0.8), 0.0, CFG)
    assert v.verdict == "scam" and v.decided_by == "decisions" and v.p_cerebras is None


def test_both_down_is_unknown_never_not_scam():
    for regex in (0.0, 0.9):
        v = ensemble.combine(DOWN_C, DOWN_D, regex, CFG)
        assert v.verdict == "unknown" and v.decided_by == "none" and v.scam_type == "unknown"
    v = ensemble.combine(None, None, 0.0, CFG)
    assert v.verdict == "unknown"


def test_fast_stage_regex_only_when_cerebras_down():
    v = ensemble.combine(DOWN_C, None, 0.7, CFG, stage="fast")
    assert v.verdict == "scam" and v.decided_by == "regex" and v.stage == "fast"
    v = ensemble.combine(DOWN_C, None, 0.1, CFG, stage="fast")
    assert v.verdict == "unknown"  # low regex never says safe


async def test_on_fast_fires_before_decisions(monkeypatch):
    log = []

    async def fake_flag(window, case_id):
        await asyncio.sleep(0.01)
        log.append("cerebras")
        return cer(0.9)

    async def fake_dec(window, case_id):
        await asyncio.sleep(0.2)
        log.append("decisions")
        return deci(0.95)

    async def on_fast(v):
        log.append(("fast", v.stage, v.verdict, v.decided_by))

    monkeypatch.setattr(ensemble, "cerebras_flag", fake_flag)
    monkeypatch.setattr(ensemble, "decisions_verdict", fake_dec)
    t0 = time.perf_counter()
    final = await ensemble.detect_opening([{"role": "scammer", "text": "30% weekly returns"}], "c_1", on_fast=on_fast)
    elapsed = time.perf_counter() - t0
    assert log == ["cerebras", ("fast", "fast", "scam", "cerebras"), "decisions"]
    assert final.stage == "final" and final.verdict == "scam" and final.p_decisions == 0.95
    assert elapsed < 0.35  # parallel, not the sum of a sequence plus extra waits


async def test_detect_opening_both_down_unknown(monkeypatch):
    async def down_flag(w, c):
        return DOWN_C

    async def down_dec(w, c):
        return DOWN_D

    seen = []

    async def on_fast(v):
        seen.append(v)

    monkeypatch.setattr(ensemble, "cerebras_flag", down_flag)
    monkeypatch.setattr(ensemble, "decisions_verdict", down_dec)
    final = await ensemble.detect_opening([{"role": "scammer", "text": "hello"}], "c_1", on_fast=on_fast)
    assert final.verdict == "unknown" and seen[0].verdict == "unknown"


async def test_on_fast_error_does_not_break_detection(monkeypatch):
    async def flag(w, c):
        return cer(0.1, "not_a_scam", "none")

    async def d(w, c):
        return deci(0.1, "not_a_scam", "none")

    async def bad(v):
        raise RuntimeError("x")

    monkeypatch.setattr(ensemble, "cerebras_flag", flag)
    monkeypatch.setattr(ensemble, "decisions_verdict", d)
    final = await ensemble.detect_opening([{"role": "scammer", "text": "Hi, kal meeting 4 baje hai na?"}], "c_1",
                                          on_fast=bad)
    assert final.verdict == "not_scam"


async def test_recheck_uses_decisions_only(monkeypatch):
    async def d(w, c):
        return deci(0.2, "not_a_scam", "low")

    monkeypatch.setattr(ensemble, "decisions_verdict", d)
    v = await ensemble.recheck([{"role": "scammer", "text": "ok"}], "c_1")
    assert v.verdict == "not_scam" and v.decided_by == "decisions" and v.p_cerebras is None and v.stage == "final"

    async def down(w, c):
        return DOWN_D

    monkeypatch.setattr(ensemble, "decisions_verdict", down)
    v = await ensemble.recheck([{"role": "scammer", "text": "ok"}], "c_1")
    assert v.verdict == "unknown"
