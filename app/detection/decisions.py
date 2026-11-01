from __future__ import annotations

from app.models import Verdict


async def decisions_verdict(window: list[dict], case_id: str) -> Verdict:
    """Decisions gpt-6-luna. On 403/unavailable: Verdict(available=False), logged once, dashboard shows it."""
    raise NotImplementedError
