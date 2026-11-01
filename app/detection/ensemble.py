"""E2 ensemble: Cerebras decides when confident, Decisions decides the band. Track A, commit 8.

Errors never produce not_scam (D-02): with no detector answer the verdict is "unknown" and the persona stays engaged.
The regex prefilter only matters on the fast stage when Cerebras is down, and it can only say scam, never safe.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app.detection.decisions import decisions_status, decisions_verdict
from app.detection.flag import cerebras_flag
from app.detection.prefilter import prefilter
from app.models import FinalVerdict, Verdict

log = logging.getLogger(__name__)

DEFAULTS = {"rule": "E2", "lo": 0.2, "hi": 0.8, "decisions_threshold": 0.5}
REGEX_FAST_SCAM = 0.6  # fast stage only, Cerebras down: regex score at or above this says scam
REPO_ROOT = Path(__file__).resolve().parents[2]
_cfg_cache: dict[str, dict] = {}


def load_config(path: str = "config/ensemble.json") -> dict:
    if path in _cfg_cache:
        return _cfg_cache[path]
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = REPO_ROOT / path
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(p.read_text()))
    except (OSError, ValueError) as e:
        log.warning("ensemble config %s not read (%s); using defaults", path, type(e).__name__)
    _cfg_cache[path] = cfg
    return cfg


def _ok(v: Optional[Verdict]) -> bool:
    return v is not None and v.available and v.p_scam is not None


def _known(x: Optional[str]) -> bool:
    return bool(x) and x not in ("unknown", "not_a_scam", "other")  # "other" only when nothing more specific


def combine(cerebras: Optional[Verdict], decisions: Optional[Verdict], regex_score: float, cfg: dict,
            *, stage: str = "final") -> FinalVerdict:
    """E2: Cerebras decides when p <= lo or p >= hi; Decisions decides the band; errors -> unknown, never not_scam."""
    lo, hi = float(cfg.get("lo", DEFAULTS["lo"])), float(cfg.get("hi", DEFAULTS["hi"]))
    dt = float(cfg.get("decisions_threshold", DEFAULTS["decisions_threshold"]))
    c_ok, d_ok = _ok(cerebras), _ok(decisions)
    p_c = cerebras.p_scam if c_ok else None
    p_d = decisions.p_scam if d_ok else None

    if c_ok and p_c <= lo:
        verdict, by = "not_scam", "cerebras"
    elif c_ok and p_c >= hi:
        verdict, by = "scam", "cerebras"
    elif c_ok and d_ok:
        verdict, by = ("scam" if p_d >= dt else "not_scam"), "decisions"
    elif c_ok:
        verdict, by = ("scam" if p_c >= 0.5 else "not_scam"), "cerebras_band"
    elif d_ok:
        verdict, by = ("scam" if p_d >= dt else "not_scam"), "decisions"
    elif stage == "fast" and regex_score >= REGEX_FAST_SCAM:
        verdict, by = "scam", "regex"
    else:
        verdict, by = "unknown", "none"

    if verdict == "scam":
        if c_ok and _known(cerebras.scam_type):
            scam_type = cerebras.scam_type
        elif d_ok and _known(decisions.scam_type):
            scam_type = decisions.scam_type
        else:
            scam_type = "other"
    elif verdict == "not_scam":
        scam_type = "not_a_scam"
    else:
        scam_type = "unknown"

    first, second = (decisions, cerebras) if by == "decisions" else (cerebras, decisions)
    risk = "unknown"
    for v in (first, second):
        if _ok(v) and v.risk and v.risk != "unknown":
            risk = v.risk
            break

    dec_available = decisions.available if decisions is not None else bool(decisions_status()["available"])
    return FinalVerdict(verdict=verdict, stage=stage, p_cerebras=p_c, p_decisions=p_d, scam_type=scam_type,
                        risk=risk, decisions_available=dec_available, decided_by=by)


def _latest_scammer_text(window: list[dict]) -> str:
    for turn in reversed(window or []):
        if turn.get("role", "scammer") == "scammer":
            return str(turn.get("text", ""))
    return ""


async def detect_opening(window: list[dict], case_id: str,
                         on_fast: Optional[Callable[[FinalVerdict], Awaitable[None]]] = None) -> FinalVerdict:
    """Prefilter, then cerebras_flag and decisions_verdict in parallel. Calls on_fast(stage="fast") as soon as the
    Cerebras flag returns so the persona can start; returns the stage="final" E2 verdict."""
    cfg = load_config()
    regex_score = prefilter(_latest_scammer_text(window))["score"]
    t_c = asyncio.create_task(cerebras_flag(window, case_id))
    t_d = asyncio.create_task(decisions_verdict(window, case_id))
    try:
        cer = await t_c
        if on_fast is not None:
            fast = combine(cer, None, regex_score, cfg, stage="fast")
            try:
                await on_fast(fast)
            except Exception:
                log.exception("on_fast callback failed")
        dec = await t_d
    finally:
        for t in (t_c, t_d):
            if not t.done():
                t.cancel()
    return combine(cer, dec, regex_score, cfg, stage="final")


async def recheck(window: list[dict], case_id: str) -> FinalVerdict:
    """Background Decisions re-check after confirmation (every 3 scammer messages, or when still_scam is false)."""
    dec = await decisions_verdict(window, case_id)
    return combine(None, dec, 0.0, load_config(), stage="final")
