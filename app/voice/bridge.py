"""WS /voice/stream: Twilio Media Streams <-> GPT-Live bridge. One CallBridge per call.

Everything runs on the server's event loop with async I/O only (no threads, no blocking SDK iterators:
V-01, V-06). Audio passes through untouched (Twilio mu-law 8 kHz == GPT-Live audio/pcmu 8000).
Protocol constants and their doc sources live in app/voice/live_protocol.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import websockets
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app import orchestrator
from app.runtime import get_runtime
from app.voice import live_protocol as lp
from app.voice import state

log = logging.getLogger("scambait.voice")

router = APIRouter()
ACTIVE: dict[str, "CallBridge"] = {}  # call_sid -> live bridge (debugging and tests)

UTTERANCE_PAUSE_S = 0.5  # close an utterance after this long without a new transcript delta (old endpointing: 500 ms)
START_WAIT_S = 15.0  # how long to wait for Twilio's "start" after the socket opens
CLOSE_WAIT_S = 2.0  # how long to wait for session.closed after session.close
SIDE_TASK_WAIT_S = 5.0  # how long cleanup waits for in-flight orchestrator calls before end_call
POLICY_VIOLATION = 1008


@dataclass
class _Utterance:
    parts: list[str] = field(default_factory=list)
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


class CallBridge:
    def __init__(self, twilio_ws: Any, stream_sid: str, call_sid: str, case_id: str,
                 settings: Any, pause_s: Optional[float] = None) -> None:
        self.twilio = twilio_ws
        self.stream_sid = stream_sid
        self.call_sid = call_sid
        self.case_id = case_id
        self.settings = settings
        self.pause_s = UTTERANCE_PAUSE_S if pause_s is None else pause_s
        self.live: Any = None
        self.session_id: Optional[str] = None
        self.close_reason: Optional[str] = None
        self.pending_marks: set[str] = set()
        self.marks_sent = 0
        self.clears_sent = 0
        self._evt = 0
        self.live_started = asyncio.Event()
        self.live_closed = asyncio.Event()
        self._utt: dict[str, _Utterance] = {"caller": _Utterance(), "persona": _Utterance()}
        self._timers: dict[str, asyncio.Task] = {}
        self._side: set[asyncio.Task] = set()
        self._twilio_lock = asyncio.Lock()
        self._live_lock = asyncio.Lock()
        self._stopping = False
        self._closing = False
        self._cleaned = False
        self._orch_error_reported = False

    # ---------- sending ----------
    def _event_id(self, prefix: str) -> str:
        self._evt += 1
        return f"{prefix}_{self._evt}"

    async def _send_live(self, msg: dict) -> None:
        if self.live is None:
            return
        async with self._live_lock:
            await self.live.send(json.dumps(msg))

    async def _send_twilio(self, msg: dict) -> None:
        async with self._twilio_lock:
            await self.twilio.send_text(json.dumps(msg))

    async def _status(self, status: str, detail: Optional[str] = None) -> None:
        await state.emit_status(self.call_sid, status, detail=detail, case_id=self.case_id)

    async def _error(self, detail: str) -> None:
        log.warning("call %s error: %s", self.call_sid, detail)
        await self._status("error", detail)

    # ---------- main ----------
    async def run(self) -> None:
        entry = state.get_call(self.call_sid)
        if entry is not None:
            entry.bridge_active = True
        ACTIVE[self.call_sid] = self
        tw: Optional[asyncio.Task] = None
        lv: Optional[asyncio.Task] = None
        try:
            await self._status("connecting")
            if not self.settings.openai_api_key:
                await self._error("OPENAI_API_KEY is not set")
                return
            try:
                self.live = await websockets.connect(
                    lp.LIVE_URL, additional_headers=lp.headers(self.settings.openai_api_key),
                    user_agent_header=lp.USER_AGENT, open_timeout=10)
            except Exception as exc:
                await self._error(f"GPT-Live connect failed: {type(exc).__name__}")
                return
            await self._send_live(lp.session_start(self.settings.live_model, lp.PERSONA_INSTRUCTIONS))
            tw = asyncio.create_task(self._twilio_loop())
            lv = asyncio.create_task(self._live_loop())
            done, _ = await asyncio.wait({tw, lv}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if not task.cancelled() and task.exception() is not None:
                    exc = task.exception()
                    await self._error(f"bridge failed: {type(exc).__name__}")
            if lv in done and not self._stopping:
                await self._error(f"GPT-Live session ended ({self.close_reason or 'connection closed'})")
        except Exception as exc:  # never end a call silently
            log.exception("bridge crashed for call %s", self.call_sid)
            await self._error(f"bridge failed: {type(exc).__name__}")
        finally:
            await self.cleanup(tw, lv)

    async def cleanup(self, tw: Optional[asyncio.Task] = None, lv: Optional[asyncio.Task] = None) -> None:
        """Idempotent: runs once even if stop, socket close and the status callback all fire (V-08)."""
        if self._cleaned:
            return
        self._cleaned = True
        self._closing = True
        if tw is not None and not tw.done():
            tw.cancel()
        # Close any open utterance so the orchestrator sees the last words before end_call.
        for speaker in ("caller", "persona"):
            timer = self._timers.pop(speaker, None)
            if timer is not None:
                timer.cancel()
            await self._close_utterance(speaker)
        if self.live is not None:
            if not self.live_closed.is_set():
                try:
                    await self._send_live(lp.session_close())
                    await asyncio.wait_for(self.live_closed.wait(), CLOSE_WAIT_S)  # docs: wait for session.closed
                except Exception:
                    pass
            if lv is not None and not lv.done():
                lv.cancel()
            try:
                await self.live.close()
            except Exception:
                pass
        if self._side:
            await asyncio.wait(set(self._side), timeout=SIDE_TASK_WAIT_S)
        try:
            await self.twilio.close()
        except Exception:
            pass
        await state.finish_call(self.call_sid)
        entry = state.get_call(self.call_sid)
        if entry is not None:
            entry.bridge_active = False
        ACTIVE.pop(self.call_sid, None)
        log.info("call %s cleaned up (marks sent %d, clears %d)", self.call_sid, self.marks_sent, self.clears_sent)

    # ---------- Twilio -> GPT-Live ----------
    async def _twilio_loop(self) -> None:
        while True:
            try:
                raw = await self.twilio.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                return
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            event = msg.get("event")
            if event == "media":
                # Docs: no audio before session.started. Twilio streams continuously, so dropping is fine.
                if self.live_started.is_set() and not self._closing:
                    payload = (msg.get("media") or {}).get("payload")
                    if payload:
                        await self._send_live(lp.input_audio_append(payload))
            elif event == "mark":
                self.pending_marks.discard(((msg.get("mark") or {}).get("name")) or "")
            elif event == "stop":
                self._stopping = True
                return

    # ---------- GPT-Live -> Twilio ----------
    async def _live_loop(self) -> None:
        try:
            async for raw in self.live:
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == lp.SESSION_STARTED:
                    await self._on_started(ev)
                elif kind == lp.OUTPUT_AUDIO_DELTA:
                    await self._on_audio(ev.get("delta"))
                elif kind == lp.INPUT_TRANSCRIPT_DELTA:
                    await self._on_transcript("caller", ev)
                elif kind == lp.OUTPUT_TRANSCRIPT_DELTA:
                    await self._on_transcript("persona", ev)
                elif kind in lp.SPEECH_STARTED_EVENTS:
                    await self._barge_in()
                elif kind == lp.SESSION_CLOSED:
                    self.close_reason = ev.get("reason")
                    return
                elif kind == lp.ERROR:
                    err = ev.get("error") or {}
                    await self._error(f"GPT-Live error: {err.get('code') or err.get('type') or 'unknown'}")
        except websockets.ConnectionClosed:
            return
        finally:
            self.live_closed.set()

    async def _on_started(self, ev: dict) -> None:
        self.session_id = (ev.get("session") or {}).get("id")
        self.live_started.set()
        await self._status("live", detail=f"gpt-live session {self.session_id}" if self.session_id else None)
        # Greeting, as in Twilio's GPT-Live tutorial: a verbatim first line, then commentary to speak now.
        await self._send_live(lp.instructions_append(lp.GREETING_INSTRUCTION, self._event_id("greeting")))
        await self._send_live(lp.commentary_append(lp.GREETING_COMMENTARY, self._event_id("greeting")))

    async def _on_audio(self, payload: Optional[str]) -> None:
        if not payload or self._closing:
            return
        self.marks_sent += 1
        name = f"m{self.marks_sent}"
        await self._send_twilio(lp.twilio_media(self.stream_sid, payload))
        await self._send_twilio(lp.twilio_mark(self.stream_sid, name))
        self.pending_marks.add(name)

    async def _barge_in(self) -> None:
        """The caller talks over audio Twilio has not played yet: drop Twilio's buffer once."""
        if not self.pending_marks:
            return
        self.pending_marks.clear()
        self.clears_sent += 1
        await self._send_twilio(lp.twilio_clear(self.stream_sid))

    # ---------- transcripts and the utterance grouper ----------
    async def _on_transcript(self, speaker: str, ev: dict) -> None:
        delta = ev.get("delta") or ""
        if not delta:
            return
        await state.emit("transcript.partial", self.case_id,
                         {"call_sid": self.call_sid, "speaker": speaker, "delta": delta})
        if speaker == "caller" and delta.strip():
            await self._barge_in()
        utt = self._utt[speaker]
        if not utt.parts:
            utt.start_ms = ev.get("start_ms")
        utt.parts.append(delta)
        if ev.get("end_ms") is not None:
            utt.end_ms = ev.get("end_ms")
        old = self._timers.pop(speaker, None)
        if old is not None:
            old.cancel()
        if not self._closing:
            self._timers[speaker] = self._spawn(self._utterance_timer(speaker))

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._side.add(task)
        task.add_done_callback(self._side.discard)
        return task

    async def _utterance_timer(self, speaker: str) -> None:
        try:
            await asyncio.sleep(self.pause_s)
        except asyncio.CancelledError:
            return
        if self._timers.get(speaker) is asyncio.current_task():
            del self._timers[speaker]  # from here on a new delta starts a new timer instead of cancelling us
        await self._close_utterance(speaker)

    async def _close_utterance(self, speaker: str) -> None:
        utt = self._utt[speaker]
        text = "".join(utt.parts).strip()
        self._utt[speaker] = _Utterance()
        if not text:
            return
        await state.emit("transcript.final", self.case_id, {
            "call_sid": self.call_sid, "speaker": speaker, "text": text,
            "start_ms": utt.start_ms, "end_ms": utt.end_ms})
        try:
            nudge = await orchestrator.handle_call_transcript(self.case_id, speaker, text, True)
        except Exception as exc:
            log.warning("handle_call_transcript failed for call %s: %s", self.call_sid, type(exc).__name__)
            if not self._orch_error_reported:
                self._orch_error_reported = True
                await self._status("error", f"orchestrator failed: {type(exc).__name__}")
            return
        if nudge and isinstance(nudge, str) and not self._closing:
            try:
                await self._send_live(lp.instructions_append(nudge, self._event_id("nudge")))
            except Exception:
                log.warning("could not send nudge for call %s", self.call_sid)


async def _wait_for_start(ws: Any) -> Optional[dict]:
    """Read Twilio messages until "start" (after "connected"). None on stop, disconnect, bad JSON or timeout."""
    async def _read() -> Optional[dict]:
        while True:
            msg = json.loads(await ws.receive_text())
            event = msg.get("event")
            if event == "start":
                return msg.get("start") or {}
            if event == "stop":
                return None
    try:
        return await asyncio.wait_for(_read(), START_WAIT_S)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, RuntimeError):
        return None


async def handle_stream(ws: Any) -> Optional[CallBridge]:
    await ws.accept()
    start = await _wait_for_start(ws)
    if start is None:
        await _close_quietly(ws, POLICY_VIOLATION)
        return None
    stream_sid = start.get("streamSid") or ""
    call_sid = start.get("callSid") or ""
    token = (start.get("customParameters") or {}).get("token")
    entry = state.get_call(call_sid)
    if not stream_sid or entry is None or not state.consume_token(token, call_sid):
        log.warning("stream rejected: bad or reused token for call %s", call_sid or "?")
        await _close_quietly(ws, POLICY_VIOLATION)
        return None
    bridge = CallBridge(ws, stream_sid, call_sid, entry.case_id, get_runtime().settings)
    await bridge.run()
    return bridge


async def _close_quietly(ws: Any, code: int) -> None:
    try:
        await ws.close(code=code)
    except Exception:
        pass


@router.websocket("/voice/stream")
async def voice_stream(websocket: WebSocket) -> None:
    await handle_stream(websocket)
