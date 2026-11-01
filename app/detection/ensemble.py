from __future__ import annotations

from typing import Optional

from app.models import FinalVerdict, Verdict


def load_config(path: str = "config/ensemble.json") -> dict:
    raise NotImplementedError


def combine(cerebras: Verdict, decisions: Optional[Verdict], regex_score: float, cfg: dict) -> FinalVerdict:
    """E2: Cerebras decides when p <= lo or p >= hi; Decisions decides the band; errors -> unknown, never not_scam."""
    raise NotImplementedError
