"""Shared typed models. This file is the contract between tracks (see docs/CONTRACTS.md)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_TEXT_CHARS = 4000  # inbound text is truncated to this before any regex or model call


def utc_now() -> str:
    """UTC ISO timestamp, the only timestamp format used in the app."""
    return datetime.now(timezone.utc).isoformat()


# ---------- Kept API contract: POST /api/v1/honeypot (old app/models.py) ----------
class Message(BaseModel):
    sender: str
    text: str = Field(..., max_length=10000)
    timestamp: Union[str, int]


class Metadata(BaseModel):
    channel: Optional[str] = "unknown"
    language: Optional[str] = "en"
    locale: Optional[str] = "IN"


class HoneypotRequest(BaseModel):
    sessionId: str
    message: Message
    conversationHistory: list[Message] = []  # accepted for compatibility, ignored: the server owns history
    metadata: Optional[Metadata] = None


class ResponseMeta(BaseModel):
    agentState: Literal["engaging", "completed"]
    sessionStatus: Literal["active", "closed"]
    persona: str
    turn: int
    confidence: Optional[str] = None
    scamType: Optional[str] = "UNKNOWN"
    agentNotes: str
    degraded: bool = False  # new, additive: true when the reply is a fallback after an internal error


class JudgeResponse(BaseModel):
    status: str = "success"  # "degraded" when meta.degraded is true
    reply: str
    meta: ResponseMeta


# ---------- Internal contract ----------
Channel = Literal["telegram", "api", "call"]
Role = Literal["scammer", "persona"]
CaseStatus = Literal["watching", "engaged", "closed"]
VerdictLabel = Literal["scam", "not_scam", "unknown"]
EventType = Literal[
    "message.received", "persona.reply", "scam.detected", "intel.extracted", "case.summary",
    "transcript.partial", "transcript.final", "call.status", "metrics.speed",
    "ratelimit.status", "task.retrying",
]
IntelKind = Literal[
    "phone", "upi", "bank_account", "ifsc", "card", "url", "apk", "email", "crypto_wallet",
    "social_handle", "name", "employee_id", "organisation", "amount", "reference_code",
]


class Event(BaseModel):
    id: Optional[int] = None  # set by the store (SQLite autoincrement), used as the SSE id
    ts: str = Field(default_factory=utc_now)
    case_id: Optional[str] = None
    channel: Channel
    type: EventType
    data: dict[str, Any] = {}


class Verdict(BaseModel):
    """One detector's opinion. p_scam is in [0, 1]; None when the detector did not answer."""
    source: Literal["regex", "cerebras", "decisions", "ensemble"]
    available: bool = True
    is_scam: Optional[bool] = None
    p_scam: Optional[float] = None
    scam_type: str = "unknown"
    risk: str = "unknown"  # none | low | high | critical | unknown
    error: Optional[str] = None
    ms: Optional[int] = None


class FinalVerdict(BaseModel):
    verdict: VerdictLabel
    stage: Literal["fast", "final"]
    p_cerebras: Optional[float] = None
    p_decisions: Optional[float] = None
    scam_type: str = "unknown"
    risk: str = "unknown"
    decisions_available: bool = True
    decided_by: str = "none"  # cerebras | decisions | regex | none


class IntelCandidate(BaseModel):
    kind: IntelKind
    value: str  # normalised value (validators run before anything is stored)
    source: Literal["regex", "persona", "call_batch"] = "regex"


class PersonaTurn(BaseModel):
    reply: str
    intel: list[IntelCandidate] = []
    summary: str = ""
    still_scam: bool = True
    confidence: float = 0.5


class Reply(BaseModel):
    """What a channel sends back. Empty text with coalesced=True means another call answers this burst."""
    case_id: str
    text: str
    degraded: bool = False
    closed: bool = False
    coalesced: bool = False
    turn: int = 0
    verdict: VerdictLabel = "unknown"
    scam_type: str = "unknown"


class CallMetrics(BaseModel):
    step: str  # flag | persona | call_batch | report | decisions | moderation
    provider: Literal["cerebras", "openai"]
    model: str
    ms: int
    queued_ms: int = 0
    retries: int = 0
    tokens_per_s: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
