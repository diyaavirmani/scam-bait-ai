"""Orchestrator: persist first, detect, persona, extract, summarise, emit. Track A, commit 11."""
from __future__ import annotations

from app.models import Channel, Reply


async def handle_message(case_id: str, channel: Channel, text: str) -> Reply:
    raise NotImplementedError


async def handle_call_transcript(case_id: str, role: str, text: str, final: bool) -> None:
    raise NotImplementedError
