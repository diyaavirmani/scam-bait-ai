"""Track C, commit 17: event bus and SSE stream."""
import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.events import Bus, router as events_router
from app.events.sse import event_stream, format_event
from app.models import Event
from app.runtime import Runtime, set_runtime
from app.store import Store


@pytest.fixture
async def rt(tmp_path):
    store = Store(str(tmp_path / "c.db"))
    await store.init()
    runtime = Runtime(settings=Settings(public_base_url=""), store=store, bus=Bus(store))
    set_runtime(runtime)
    yield runtime
    await store.close()


class _Req:
    async def is_disconnected(self):
        return False


def _ev(t="message.received", **data):
    return Event(case_id="c_000000000001", channel="api", type=t, data=data)


async def test_emit_stores_and_sets_id(rt):
    ev = await rt.bus.emit(_ev(text="hello", turn=1))
    assert isinstance(ev.id, int)
    stored = await rt.store.events_after(0, 10)
    assert [e.id for e in stored] == [ev.id] and stored[0].data["text"] == "hello"


async def test_unstored_types_not_persisted(rt):
    q = rt.bus.subscribe()
    a = await rt.bus.emit(_ev("transcript.partial", call_sid="CA1", speaker="caller", delta="hel"))
    b = await rt.bus.emit(_ev("ratelimit.status", model="m", rpm_used=1, rpm_limit=5, waiting=0))
    assert a.id is None and b.id is None
    assert await rt.store.events_after(0, 10) == []
    assert q.qsize() == 2  # still fanned out live
    assert format_event(a).startswith("event: transcript.partial\n")


async def test_slow_subscriber_dropped_without_blocking(rt):
    bus = Bus(rt.store, queue_size=2)
    slow = bus.subscribe()
    t0 = time.perf_counter()
    for i in range(5):
        await bus.emit(_ev(text=str(i)))
    assert time.perf_counter() - t0 < 2.0
    assert slow.dropped is True and bus.subscriber_count == 0
    fast = bus.subscribe()
    await bus.emit(_ev(text="after"))
    assert fast.qsize() == 1


async def test_emit_never_raises_when_store_fails():
    class Broken:
        async def add_event(self, event):
            raise RuntimeError("db down")
    bus = Bus(Broken())
    q = bus.subscribe()
    ev = await bus.emit(_ev(text="x"))
    assert ev.id is None and q.qsize() == 1


async def test_sse_replay_after_last_id_then_live(rt):
    ids = [(await rt.bus.emit(_ev(text=f"m{i}", turn=i))).id for i in range(4)]
    gen = event_stream(_Req(), rt.bus, rt.store, last_id=ids[1], keepalive_s=0.05)
    assert (await gen.__anext__()).startswith("retry:")
    first = await gen.__anext__()
    second = await gen.__anext__()
    assert first.startswith(f"id: {ids[2]}\nevent: message.received\ndata: ")
    assert second.startswith(f"id: {ids[3]}\n")
    live = await rt.bus.emit(_ev(text="live"))
    nxt = await gen.__anext__()
    while nxt.startswith(":"):
        nxt = await gen.__anext__()
    assert nxt.startswith(f"id: {live.id}\n") and '"live"' in nxt
    assert (await gen.__anext__()) == ": keepalive\n\n"
    await gen.aclose()
    assert rt.bus.subscriber_count == 0


async def test_sse_without_last_id_is_live_only(rt):
    await rt.bus.emit(_ev(text="old"))
    gen = event_stream(_Req(), rt.bus, rt.store, last_id=None, keepalive_s=0.05)
    await gen.__anext__()  # retry
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0)
    await rt.bus.emit(_ev("transcript.partial", call_sid="CA1", speaker="caller", delta="hi"))
    msg = await task
    assert msg.startswith("event: transcript.partial\n") and "old" not in msg
    await gen.aclose()


async def test_sse_dropped_subscriber_stream_closes(rt):
    bus = Bus(rt.store, queue_size=1)
    gen = event_stream(_Req(), bus, rt.store, last_id=None, keepalive_s=0.05)
    await gen.__anext__()
    for i in range(3):
        await bus.emit(_ev(text=str(i)))
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


def test_sse_route_is_open(rt):
    route = next(r for r in events_router.routes if getattr(r, "path", "") == "/api/v1/events/stream")
    assert route.dependant.dependencies == []  # no login or header needed
