"""Voice track (Track D): Twilio webhooks and the Media Streams to GPT-Live bridge.

Routes (full paths, include with app.include_router(app.voice.router)):
- GET  /voice/incoming       plain readiness text
- POST /voice/incoming       signed Twilio Voice webhook, answers <Connect><Stream> TwiML
- POST /voice/status         signed call status callback (set on the number in the Twilio console)
- POST /voice/stream-status  signed <Stream statusCallback>
- WS   /voice/stream         Media Streams bridge (app/voice/bridge.py)
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit
from xml.sax.saxutils import quoteattr

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from twilio.request_validator import RequestValidator

from app.runtime import get_runtime
from app.voice import state
from app.voice.bridge import router as _bridge_router

log = logging.getLogger("scambait.voice")

router = APIRouter()
router.include_router(_bridge_router)

READY_TEXT = "SCAM-BAIT voice webhook ready. Configure Twilio to POST to this URL."


async def _validated_form(request: Request, path: str) -> dict[str, str]:
    """403 unless X-Twilio-Signature matches PUBLIC_BASE_URL + path (never the Host header, V-09)."""
    settings = get_runtime().settings
    if not settings.twilio_auth_token or not settings.public_base_url:
        log.warning("voice webhook rejected: TWILIO_AUTH_TOKEN or PUBLIC_BASE_URL is not set")
        raise HTTPException(status_code=403, detail="forbidden")
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    url = settings.public_base_url + path
    if request.url.query:
        url += "?" + request.url.query
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature or not RequestValidator(settings.twilio_auth_token).validate(url, params, signature):
        log.warning("voice webhook rejected: bad X-Twilio-Signature on %s", path)
        raise HTTPException(status_code=403, detail="forbidden")
    return params


def stream_twiml(public_base_url: str, token: str, case_id: str) -> str:
    parts = urlsplit(public_base_url)
    ws_url = f"wss://{parts.netloc}{parts.path.rstrip('/')}/voice/stream"
    status_cb = f"{public_base_url}/voice/stream-status"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect>"
        f'<Stream url={quoteattr(ws_url)} statusCallback={quoteattr(status_cb)} statusCallbackMethod="POST">'
        f'<Parameter name="token" value={quoteattr(token)}/>'
        f'<Parameter name="case_id" value={quoteattr(case_id)}/>'
        "</Stream></Connect></Response>"
    )


@router.get("/voice/incoming")
async def voice_ready() -> PlainTextResponse:
    return PlainTextResponse(READY_TEXT)


@router.post("/voice/incoming")
async def voice_incoming(request: Request) -> Response:
    form = await _validated_form(request, "/voice/incoming")
    call_sid = form.get("CallSid", "").strip()
    if not call_sid:
        raise HTTPException(status_code=400, detail="CallSid missing")
    from_masked = state.mask_number(form.get("From"))
    rt = get_runtime()
    case = await rt.store.get_or_create_case("call", f"call:{call_sid}")
    state.register_call(call_sid, case["id"], from_masked)
    token = state.issue_token(call_sid)
    log.info("incoming call %s from %s -> case %s", call_sid, from_masked, case["id"])
    await state.emit_status(call_sid, "ringing")
    return Response(content=stream_twiml(rt.settings.public_base_url, token, case["id"]),
                     media_type="application/xml")


async def _status_callback(request: Request, path: str) -> Response:
    form = await _validated_form(request, path)
    call_sid = form.get("CallSid", "").strip()
    if not call_sid:
        return Response(status_code=204)
    entry = state.get_call(call_sid)
    if path == "/voice/stream-status":
        event = form.get("StreamEvent", "stream-unknown")
        status = "error" if event == "stream-error" else event
        await state.emit_status(call_sid, status, detail=form.get("StreamError") or None)
        terminal = event in ("stream-stopped", "stream-error")
    else:
        status = form.get("CallStatus", "unknown")
        await state.emit_status(call_sid, status,
                                from_masked=None if entry else state.mask_number(form.get("From")))
        terminal = status in state.TERMINAL_CALL_STATUSES
    # A live bridge ends the call itself (after flushing its last utterances); this only covers a missed stop.
    if terminal and entry is not None and not entry.bridge_active:
        await state.finish_call(call_sid)
    return Response(status_code=204)


@router.post("/voice/status")
async def voice_status(request: Request) -> Response:
    return await _status_callback(request, "/voice/status")


@router.post("/voice/stream-status")
async def voice_stream_status(request: Request) -> Response:
    return await _status_callback(request, "/voice/stream-status")


__all__ = ["router", "stream_twiml"]
