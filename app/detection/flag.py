from __future__ import annotations

from app.models import Verdict


async def cerebras_flag(window: list[dict], case_id: str) -> Verdict:
    """qwen-3.8-27b strict JSON {is_scam, p_scam, scam_type, risk}, reasoning_effort none. Errors -> available=False."""
    raise NotImplementedError
