from __future__ import annotations

from typing import Awaitable, Callable, Optional

from app.models import FinalVerdict, Verdict


def load_config(path: str = "config/ensemble.json") -> dict:
    raise NotImplementedError


def combine(cerebras: Verdict, decisions: Optional[Verdict], regex_score: float, cfg: dict) -> FinalVerdict:
    """E2: Cerebras decides when p <= lo or p >= hi; Decisions decides the band; errors -> unknown, never not_scam."""
    raise NotImplementedError


async def detect_opening(window: list[dict], case_id: str,
                         on_fast: Optional[Callable[[FinalVerdict], Awaitable[None]]] = None) -> FinalVerdict:
    """Prefilter, then asyncio.gather(cerebras_flag, decisions_verdict). Calls on_fast(stage="fast") as soon as the
    Cerebras flag returns so the persona can start; returns the stage="final" E2 verdict."""
    raise NotImplementedError


async def recheck(window: list[dict], case_id: str) -> FinalVerdict:
    """Background Decisions re-check after confirmation (every 3 scammer messages, or when still_scam is false)."""
    raise NotImplementedError
