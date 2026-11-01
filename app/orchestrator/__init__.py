"""Orchestrator: persist first, detect, persona, extract, summarise, emit. Track A, commit 11."""
from __future__ import annotations

from typing import Optional

from app.models import Channel, Reply


async def handle_message(case_id: str, channel: Channel, text: str) -> Reply:
    raise NotImplementedError


async def handle_call_transcript(case_id: str, role: str, text: str, final: bool) -> Optional[str]:
    """role: caller | persona. Returns a nudge for GPT-Live (session.instructions.append) or None."""
    raise NotImplementedError


async def end_call(case_id: str) -> None:
    """Final batch, close the case, schedule the report. Idempotent."""
    raise NotImplementedError
