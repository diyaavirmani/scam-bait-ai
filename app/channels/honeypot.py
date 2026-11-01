"""POST /api/v1/honeypot: the kept contract of the old app (HoneypotRequest -> JudgeResponse). Track B, commit 12.

- x-api-key is compared in constant time with API_KEY. An unset API_KEY gives 503, never open access (A-05).
- sessionId must match SESSION_ID_RE (400 otherwise); it is only used as a lookup key, never in a path (P-01).
- message.sender must be exactly "scammer" (server-assigned roles, PI-02). conversationHistory is accepted
  for compatibility and ignored: the server owns the history.
- Errors are not hidden: a fallback reply has meta.degraded=true and status "degraded", and an exception
  in the orchestrator gives HTTP 500 with a JSON error (A-04).
- Coalesced replies: a Telegram burst can be answered by one reply, but an API client cannot wait for it,
  so a coalesced reply (empty text) is returned as is. API clients send one message at a time and wait
  for the answer, so in practice this does not happen.
"""
from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

import app.orchestrator as orchestrator
from app.models import SESSION_ID_RE, HoneypotRequest, JudgeResponse, Reply, ResponseMeta
from app.runtime import get_runtime

log = logging.getLogger("scambait.api")
router = APIRouter()

NOTES = {"scam": "Detection: SCAM", "not_scam": "Detection: LEGITIMATE", "unknown": "Detection: UNKNOWN"}
CONFIDENCE = {"scam": "high", "not_scam": "medium", "unknown": "low"}  # only reported once the case is closed


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="x-api-key")) -> None:
    try:
        expected = get_runtime().settings.api_key
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Service starting")
    if not expected:
        raise HTTPException(status_code=503, detail="API key not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid API key")


def build_response(reply: Reply) -> JudgeResponse:
    closed = reply.closed
    scam_type = (reply.scam_type or "unknown").strip()
    return JudgeResponse(
        status="degraded" if reply.degraded else "success",
        reply=reply.text,
        meta=ResponseMeta(
            agentState="completed" if closed else "engaging",
            sessionStatus="closed" if closed else "active",
            persona="confused_customer" if reply.verdict == "scam" else "polite_responder",
            turn=reply.turn,
            confidence=CONFIDENCE.get(reply.verdict, "low") if closed else None,
            scamType=scam_type.upper() if scam_type and scam_type.lower() != "unknown" else "UNKNOWN",
            agentNotes=NOTES.get(reply.verdict, "Detection: UNKNOWN"),
            degraded=reply.degraded,
        ),
    )


@router.post("/api/v1/honeypot", response_model=JudgeResponse, dependencies=[Depends(require_api_key)])
async def honeypot(body: HoneypotRequest):
    if not SESSION_ID_RE.match(body.sessionId):
        raise HTTPException(status_code=400, detail="Invalid sessionId (allowed: A-Z a-z 0-9 _ -, 1 to 64 chars)")
    if body.message.sender != "scammer":
        raise HTTPException(status_code=400, detail="message.sender must be 'scammer'")
    try:
        store = get_runtime().store
        case = await store.get_or_create_case("api", f"api:{body.sessionId}")
        reply = await orchestrator.handle_message(case["id"], "api", body.message.text)
    except Exception:
        log.exception("honeypot turn failed")
        return JSONResponse({"status": "error", "error": "internal error"}, status_code=500)
    if reply.degraded:
        log.error("honeypot reply degraded for case %s", reply.case_id)
    return build_response(reply)
