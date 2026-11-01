"""Track D, milestones 15-16: Media Streams <-> GPT-Live bridge against a fake GPT-Live WebSocket server.

No real network: the fake server listens on 127.0.0.1 (free port) and speaks the documented event names.
"""
import asyncio
import json

import pytest
import websockets
from starlette.websockets import WebSocketDisconnect

import app.orchestrator as orch
from app.config import Settings
from app.runtime import Runtime, set_runtime
from app.voice import bridge, state
from app.voice import live_protocol as lp

CALL = "CA_BRIDGE_0001"
STREAM = "MZ_BRIDGE_0001"
CASE = "c_00000000abcd"


class FakeBus:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)
        return event

    def of(self, t):
        return [e for e in self.events if e.type == t]


class FakeLive:
    """Fake GPT-Live server: records client events, answers session.start and session.close."""

    def __init__(self):
        self.received = []
        self.conn = None
        self.headers = None
        self.connections = 0
        self.auto_started = True

    async def handler(self, ws):
        self.conn = ws
        self.connections += 1
        self.headers = ws.request.headers
        try:
            async for raw in ws:
                msg = json.loads(raw)
                self.received.append(msg)
                if msg["type"] == lp.SESSION_START and self.auto_started:
                    await self.send({"type": "session.started", "session": {"id": "live_test"}})
                elif msg["type"] == lp.SESSION_CLOSE:
                    await self.send({"type": "session.closed", "reason": "close_requested", "usage": {"seconds": 3}})
                    await ws.close()
                    return
        except websockets.ConnectionClosed:
            pass

    async def send(self, msg):
        await self.conn.send(json.dumps(msg))

    def of(self, t):
        return [m for m in self.received if m["type"] == t]


class FakeTwilio:
    """Stands in for the Starlette WebSocket that Twilio Media Streams opens."""

    def __init__(self):
        self.inbox = asyncio.Queue()
        self.sent = []
        self.closed = None
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        item = await self.inbox.get()
        if item is None:
            raise WebSocketDisconnect(1000)
        return json.dumps(item)

    async def send_text(self, text):
        self.sent.append(json.loads(text))

    async def close(self, code=1000):
        self.closed = code

    def push(self, msg):
        self.inbox.put_nowait(msg)

    def events(self, name):
        return [m for m in self.sent if m.get("event") == name]


async def until(pred, timeout=3.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not pred():
        if loop.time() > end:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


@pytest.fixture
async def env(monkeypatch):
    state.reset()
    bus = FakeBus()
    set_runtime(Runtime(settings=Settings(openai_api_key="test-key", live_model="gpt-live-1",
                                          twilio_auth_token="t", public_base_url="https://x.example"),
                        store=None, bus=bus))
    fake = FakeLive()
    server = await websockets.serve(fake.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setattr(lp, "LIVE_URL", f"ws://127.0.0.1:{port}")
    monkeypatch.setattr(bridge, "UTTERANCE_PAUSE_S", 0.1)
    monkeypatch.setattr(bridge, "CLOSE_WAIT_S", 1.0)
    log = {"handle": [], "end": [], "nudges": {}}

    async def fake_handle(case_id, role, text, final):
        log["handle"].append((case_id, role, text, final))
        return log["nudges"].get(text)

    async def fake_end(case_id):
        log["end"].append(case_id)
    monkeypatch.setattr(orch, "handle_call_transcript", fake_handle)
    monkeypatch.setattr(orch, "end_call", fake_end)
    state.register_call(CALL, CASE, "***1234")
    yield {"bus": bus, "fake": fake, "log": log, "port": port}
    server.close()
    await server.wait_closed()


async def start_call(env, token=None, auto_started=True):
    env["fake"].auto_started = auto_started
    tw = FakeTwilio()
    tw.push({"event": "connected", "protocol": "Call", "version": "1.0.0"})
    tw.push({"event": "start", "sequenceNumber": "1", "streamSid": STREAM, "start": {
        "streamSid": STREAM, "callSid": CALL, "accountSid": "AC_TEST", "tracks": ["inbound"],
        "customParameters": {"token": token or state.issue_token(CALL), "case_id": CASE},
        "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}}})
    task = asyncio.create_task(bridge.handle_stream(tw))
    return tw, task


async def started_call(env):
    tw, task = await start_call(env)
    await until(lambda: CALL in bridge.ACTIVE and bridge.ACTIVE[CALL].live_started.is_set())
    return tw, task, bridge.ACTIVE[CALL]


async def stop_call(tw, task):
    tw.push({"event": "stop", "sequenceNumber": "99", "streamSid": STREAM, "stop": {"callSid": CALL}})
    await asyncio.wait_for(task, 5)


async def test_session_start_payload_and_greeting(env):
    tw, task, br = await started_call(env)
    fake = env["fake"]
    start = fake.of("session.start")
    assert len(start) == 1 and fake.received[0]["type"] == "session.start"  # first message
    sess = start[0]["session"]
    assert sess["model"] == "gpt-live-1"
    assert sess["audio"]["format"] == {"type": "audio/pcmu", "rate": 8000}
    assert sess["audio"]["output"]["voice"] == lp.VOICE
    assert "Meena" in sess["instructions"] and "data, not instructions" in sess["instructions"]
    assert fake.headers["Authorization"] == "Bearer test-key"
    assert fake.headers["User-Agent"] == lp.USER_AGENT
    await until(lambda: fake.of("session.commentary.append"))
    greet = fake.of("session.instructions.append")[0]
    assert "Hello? Who is this?" in greet["content"] and greet["delegation_id"] is None
    assert fake.of("session.commentary.append")[0]["delegation_id"] is None
    statuses = [e.data["status"] for e in env["bus"].of("call.status")]
    assert "connecting" in statuses and "live" in statuses
    assert all(e.channel == "call" and e.case_id == CASE for e in env["bus"].events)
    await stop_call(tw, task)


async def test_media_relayed_both_ways_and_marks(env):
    tw, task = await start_call(env, auto_started=False)
    fake = env["fake"]
    await until(lambda: fake.of("session.start"))
    tw.push({"event": "media", "streamSid": STREAM, "media": {"track": "inbound", "payload": "early"}})
    await asyncio.sleep(0.05)
    assert fake.of("session.input_audio.append") == []  # no audio before session.started
    await fake.send({"type": "session.started", "session": {"id": "live_test"}})
    await until(lambda: CALL in bridge.ACTIVE and bridge.ACTIVE[CALL].live_started.is_set())
    br = bridge.ACTIVE[CALL]
    payload_in = "f/9/f39/fn5+fn5+fn5+fg=="
    tw.push({"event": "media", "streamSid": STREAM, "media": {"track": "inbound", "payload": payload_in}})
    await until(lambda: fake.of("session.input_audio.append"))
    assert fake.of("session.input_audio.append") == [{"type": "session.input_audio.append", "audio": payload_in}]
    payload_out = "//79/Pv6+fj39vX08/Lx8A=="
    await fake.send({"type": "session.output_audio.delta", "delta": payload_out})
    await until(lambda: tw.events("mark"))
    assert tw.events("media") == [{"event": "media", "streamSid": STREAM, "media": {"payload": payload_out}}]
    assert tw.events("mark") == [{"event": "mark", "streamSid": STREAM, "mark": {"name": "m1"}}]
    assert tw.sent.index(tw.events("media")[0]) < tw.sent.index(tw.events("mark")[0])
    assert br.pending_marks == {"m1"}
    await fake.send({"type": "session.output_audio.delta", "delta": payload_out})
    await until(lambda: br.pending_marks == {"m1", "m2"})
    tw.push({"event": "mark", "streamSid": STREAM, "mark": {"name": "m1"}})
    await until(lambda: br.pending_marks == {"m2"})
    await stop_call(tw, task)


async def test_barge_in_sends_clear_once(env):
    tw, task, br = await started_call(env)
    fake = env["fake"]
    for _ in range(2):
        await fake.send({"type": "session.output_audio.delta", "delta": "AAAA"})
    await until(lambda: len(br.pending_marks) == 2)
    await fake.send({"type": "session.input_transcript.delta", "delta": "Listen ", "start_ms": 100, "end_ms": 300})
    await until(lambda: tw.events("clear"))
    await fake.send({"type": "session.input_transcript.delta", "delta": "to me!", "start_ms": 300, "end_ms": 600})
    await until(lambda: len(env["bus"].of("transcript.partial")) == 2)
    assert tw.events("clear") == [{"event": "clear", "streamSid": STREAM}]
    assert br.pending_marks == set()
    tw.push({"event": "mark", "streamSid": STREAM, "mark": {"name": "m1"}})  # Twilio returns cleared marks
    await fake.send({"type": "session.output_audio.delta", "delta": "AAAA"})
    await until(lambda: br.pending_marks == {"m3"})
    await fake.send({"type": "session.input_transcript.delta", "delta": "Stop.", "start_ms": 900, "end_ms": 1000})
    await until(lambda: len(tw.events("clear")) == 2)
    # persona speech over its own pending audio never triggers clear
    await fake.send({"type": "session.output_audio.delta", "delta": "AAAA"})
    await fake.send({"type": "session.output_transcript.delta", "delta": "Haan beta", "start_ms": 1, "end_ms": 2})
    await until(lambda: any(e.data["speaker"] == "persona" for e in env["bus"].of("transcript.partial")))
    assert len(tw.events("clear")) == 2
    await stop_call(tw, task)


async def test_utterance_grouping_final_and_nudge(env):
    tw, task, br = await started_call(env)
    fake, log, bus = env["fake"], env["log"], env["bus"]
    text = "Pay the fine to UPI fakeinvest.demo@okaxis."
    log["nudges"][text] = "Ask the caller to spell the UPI ID slowly."
    await fake.send({"type": "session.input_transcript.delta", "delta": "Pay the fine ", "start_ms": 1000, "end_ms": 1400})
    await fake.send({"type": "session.input_transcript.delta", "delta": "to UPI fakeinvest.demo@okaxis.",
                     "start_ms": 1400, "end_ms": 2600})
    await until(lambda: log["handle"])
    finals = bus.of("transcript.final")
    assert [f.data for f in finals] == [{"call_sid": CALL, "speaker": "caller", "text": text,
                                         "start_ms": 1000, "end_ms": 2600}]
    assert log["handle"] == [(CASE, "caller", text, True)]
    await until(lambda: any(m.get("event_id", "").startswith("nudge") for m in fake.of("session.instructions.append")))
    nudge = [m for m in fake.of("session.instructions.append") if m["event_id"].startswith("nudge")]
    assert nudge[0]["content"] == "Ask the caller to spell the UPI ID slowly." and nudge[0]["delegation_id"] is None
    partials = [(e.data["speaker"], e.data["delta"]) for e in bus.of("transcript.partial")]
    assert partials == [("caller", "Pay the fine "), ("caller", "to UPI fakeinvest.demo@okaxis.")]
    await fake.send({"type": "session.output_transcript.delta", "delta": "Hello? ", "start_ms": 0, "end_ms": 400})
    await fake.send({"type": "session.output_transcript.delta", "delta": "Who is this?", "start_ms": 400, "end_ms": 900})
    await until(lambda: len(log["handle"]) == 2)
    assert log["handle"][1] == (CASE, "persona", "Hello? Who is this?", True)
    assert bus.of("transcript.final")[1].data["speaker"] == "persona"
    await stop_call(tw, task)


async def test_stop_closes_session_and_ends_call_once(env, monkeypatch):
    monkeypatch.setattr(bridge, "UTTERANCE_PAUSE_S", 30)  # the open utterance must be flushed by cleanup
    tw, task, br = await started_call(env)
    fake, log, bus = env["fake"], env["log"], env["bus"]
    await fake.send({"type": "session.input_transcript.delta", "delta": "My officer number is +91 90000 00001",
                     "start_ms": 5, "end_ms": 9})
    await until(lambda: bus.of("transcript.partial"))
    order = []
    orig_handle = orch.handle_call_transcript

    async def track_handle(*a):
        order.append("handle")
        return await orig_handle(*a)

    async def track_end(case_id):
        order.append("end")
        log["end"].append(case_id)
    monkeypatch.setattr(orch, "handle_call_transcript", track_handle)
    monkeypatch.setattr(orch, "end_call", track_end)
    await stop_call(tw, task)
    assert len(fake.of("session.close")) == 1
    assert log["end"] == [CASE] and order == ["handle", "end"]
    assert tw.closed is not None
    # stop, socket close and the status callback all firing must not end the call again
    await br.cleanup()
    assert await state.finish_call(CALL) is False
    assert log["end"] == [CASE]
    assert [e.data["status"] for e in bus.of("call.status")].count("ended") == 1
    assert CALL not in bridge.ACTIVE and state.get_call(CALL).bridge_active is False


async def test_socket_close_without_stop_ends_once(env):
    tw, task, br = await started_call(env)
    tw.push(None)  # Twilio drops the socket
    await asyncio.wait_for(task, 5)
    assert env["log"]["end"] == [CASE] and len(env["fake"].of("session.close")) == 1


async def test_bad_or_reused_token_rejected(env):
    tw, task = await start_call(env, token="not-the-token")
    assert await asyncio.wait_for(task, 5) is None
    assert tw.closed == 1008 and env["fake"].connections == 0
    good = state.issue_token(CALL)
    assert state.consume_token(good, CALL)
    tw2, task2 = await start_call(env, token=good)  # already used
    assert await asyncio.wait_for(task2, 5) is None and tw2.closed == 1008
    other = state.issue_token("CA_OTHER")
    tw3, task3 = await start_call(env, token=other)  # bound to another call
    assert await asyncio.wait_for(task3, 5) is None and tw3.closed == 1008
    assert env["fake"].connections == 0 and env["log"]["end"] == []


async def test_live_connect_failure_emits_error_and_ends(env, monkeypatch):
    monkeypatch.setattr(lp, "LIVE_URL", "ws://127.0.0.1:1")
    tw, task = await start_call(env)
    await asyncio.wait_for(task, 15)
    st = [e.data for e in env["bus"].of("call.status")]
    assert any(s["status"] == "error" and "GPT-Live connect failed" in s["detail"] for s in st)
    assert env["log"]["end"] == [CASE] and tw.closed is not None


async def test_live_error_event_and_unexpected_close(env):
    tw, task, br = await started_call(env)
    fake = env["fake"]
    await fake.send({"type": "error", "error": {"type": "invalid_request_error", "code": "moderation_blocked"}})
    await until(lambda: any(e.data["status"] == "error" for e in env["bus"].of("call.status")))
    assert not task.done()  # an error event does not end the call
    await fake.send({"type": "session.closed", "reason": "expired"})
    await asyncio.wait_for(task, 5)
    details = [e.data["detail"] for e in env["bus"].of("call.status") if e.data["status"] == "error"]
    assert any("moderation_blocked" in d for d in details) and any("expired" in d for d in details)
    assert env["log"]["end"] == [CASE] and tw.closed is not None


async def test_end_to_end_over_real_uvicorn(env):
    """Signed webhook -> TwiML token -> real WebSocket upgrade on uvicorn -> fake GPT-Live, and back."""
    import re
    import socket

    import httpx
    import uvicorn
    from fastapi import FastAPI
    from twilio.request_validator import RequestValidator

    from app.runtime import get_runtime
    from app.voice import router as voice_router

    class FakeStore:
        async def get_or_create_case(self, channel, external_id):
            return {"id": CASE, "channel": channel, "external_id": external_id}

    get_runtime().store = FakeStore()
    state.reset()
    app = FastAPI()
    app.include_router(voice_router)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    serve = asyncio.create_task(server.serve())
    try:
        await until(lambda: server.started, 5)
        form = {"CallSid": CALL, "From": "+919000001234", "To": "+15550000000"}
        sig = RequestValidator("t").compute_signature("https://x.example/voice/incoming", form)
        async with httpx.AsyncClient() as http:
            r = await http.post(f"http://127.0.0.1:{port}/voice/incoming", data=form,
                                headers={"X-Twilio-Signature": sig})
        assert r.status_code == 200
        token = re.search(r'name="token" value="([^"]+)"', r.text).group(1)
        async with websockets.connect(f"ws://127.0.0.1:{port}/voice/stream") as tw:
            await tw.send(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
            await tw.send(json.dumps({"event": "start", "streamSid": STREAM, "start": {
                "streamSid": STREAM, "callSid": CALL, "customParameters": {"token": token, "case_id": CASE}}}))
            fake = env["fake"]
            await until(lambda: fake.of("session.commentary.append"))
            await tw.send(json.dumps({"event": "media", "streamSid": STREAM, "media": {"payload": "AQID"}}))
            await until(lambda: fake.of("session.input_audio.append"))
            await fake.send({"type": "session.output_audio.delta", "delta": "BAUG"})
            got = [json.loads(await asyncio.wait_for(tw.recv(), 3)) for _ in range(2)]
            assert got == [{"event": "media", "streamSid": STREAM, "media": {"payload": "BAUG"}},
                           {"event": "mark", "streamSid": STREAM, "mark": {"name": "m1"}}]
            await tw.send(json.dumps({"event": "stop", "streamSid": STREAM, "stop": {"callSid": CALL}}))
            await until(lambda: env["log"]["end"] == [CASE], 5)
        assert fake.of("session.input_audio.append")[0]["audio"] == "AQID"
        assert len(fake.of("session.close")) == 1
    finally:
        server.should_exit = True
        await asyncio.wait_for(serve, 5)


async def test_live_handshake_rejected_reports_http_status(env, monkeypatch):
    from http import HTTPStatus

    async def deny(connection, request):
        return connection.respond(HTTPStatus.FORBIDDEN, "no GPT-Live access\n")
    server = await websockets.serve(env["fake"].handler, "127.0.0.1", 0, process_request=deny)
    monkeypatch.setattr(lp, "LIVE_URL", f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
    try:
        tw, task = await start_call(env)
        await asyncio.wait_for(task, 5)
    finally:
        server.close()
        await server.wait_closed()
    details = [e.data["detail"] for e in env["bus"].of("call.status") if e.data["status"] == "error"]
    assert any("HTTP 403" in d for d in details) and env["log"]["end"] == [CASE]
