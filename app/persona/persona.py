from __future__ import annotations

from app.models import PersonaTurn


async def persona_turn(case_id: str, history: list[dict], key_facts: list[str], language: str,
                       mode: str, missing_intel: list[str]) -> PersonaTurn:
    """mode: neutral | bait | wrap_up. history: [{role, text}] in order, full chat."""
    raise NotImplementedError
