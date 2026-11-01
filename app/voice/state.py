"""In-memory call state for the voice track: one-time stream tokens, per-call entries, the end-once guard.

One uvicorn worker (docs/CONTRACTS.md), so module-level dicts are the whole truth for live calls.
"""
from __future__ import annotations

import logging
import re
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from app import orchestrator
from app.models import Event

log = logging.getLogger("scambait.voice")

TOKEN_TTL_SECONDS = 120  # Twilio opens the stream a second or two after the webhook answers
TERMINAL_CALL_STATUSES = frozenset({"completed", "failed", "busy", "no-answer", "canceled"})


@dataclass
class CallEntry:
    call_sid: str
    case_id: str
    from_masked: str
    bridge_active: bool = False
    ended: bool = False


_calls: dict[str, CallEntry] = {}
_tokens: dict[str, tuple[str, float]] = {}  # token -> (call_sid, expires_at monotonic)


def reset() -> None:
    """Tests only."""
    _calls.clear()
    _tokens.clear()


def mask_number(raw: Optional[str]) -> str:
    """Keep only the last 4 digits of a phone number. Full numbers are never logged or emitted."""
    digits = re.sub(r"\D", "", raw or "")
    return "***" + digits[-4:] if len(digits) >= 4 else "***"


def register_call(call_sid: str, case_id: str, from_masked: str) -> CallEntry:
    entry = _calls.get(call_sid)
    if entry is None or entry.case_id != case_id:
        entry = CallEntry(call_sid=call_sid, case_id=case_id, from_masked=from_masked)
        _calls[call_sid] = entry
    return entry


def get_call(call_sid: str) -> Optional[CallEntry]:
    return _calls.get(call_sid)


def issue_token(call_sid: str, ttl: float = TOKEN_TTL_SECONDS) -> str:
    now = time.monotonic()
    for tok, (_, exp) in list(_tokens.items()):
        if exp < now:
            _tokens.pop(tok, None)
    token = secrets.token_urlsafe(24)
    _tokens[token] = (call_sid, now + ttl)
    return token


def consume_token(token: Optional[str], call_sid: Optional[str]) -> bool:
    """True once for a live token bound to this call_sid. Any presented token is burnt, match or not."""
    if not token or not call_sid:
        return False
    item = _tokens.pop(token, None)
    if item is None:
        return False
    bound_sid, expires_at = item
    return secrets.compare_digest(bound_sid, call_sid) and time.monotonic() <= expires_at


async def emit(event_type: str, case_id: Optional[str], data: dict) -> None:
    """Emit through the bus (app.events.emit). Never raises into the call path."""
    try:
        from app.events import emit as bus_emit
        await bus_emit(Event(case_id=case_id, channel="call", type=event_type, data=data))
    except Exception:
        log.exception("emit failed for type=%s", event_type)


async def emit_status(call_sid: str, status: str, detail: Optional[str] = None,
                      case_id: Optional[str] = None, from_masked: Optional[str] = None) -> None:
    entry = _calls.get(call_sid)
    if entry is not None:
        case_id = case_id or entry.case_id
        from_masked = from_masked or entry.from_masked
    await emit("call.status", case_id, {
        "call_sid": call_sid, "status": status, "from_masked": from_masked or "***", "detail": detail})


async def finish_call(call_sid: str) -> bool:
    """Run orchestrator.end_call once per call, then emit call.status ended. Safe to call from the stream
    stop, the socket close and the status callbacks: only the first caller does the work (V-08)."""
    entry = _calls.get(call_sid)
    if entry is None or entry.ended:
        return False
    entry.ended = True  # set before any await so concurrent callers return at once
    try:
        await orchestrator.end_call(entry.case_id)
    except Exception as exc:
        log.exception("end_call failed for call %s", call_sid)
        await emit_status(call_sid, "error", detail=f"end_call failed: {type(exc).__name__}")
    await emit_status(call_sid, "ended")
    return True
