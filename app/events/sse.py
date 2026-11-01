"""GET /api/v1/events/stream: Server-Sent Events with Last-Event-ID replay. Track C, commit 17.

On connect the stream subscribes to the bus first, then replays stored events after the
Last-Event-ID header (or ?last_id=) from SQLite, then sends live events, skipping any live event
already replayed. Without either, it sends live events only. Each message is
`id: <id>\\nevent: <type>\\ndata: <json>\\n\\n` (no id line for unstored events). A `: keepalive`
comment goes out every 15 s. Login cookie required.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.models import Event

router = APIRouter()

KEEPALIVE_S = 15.0
REPLAY_BATCH = 500


def format_event(ev: Event) -> str:
    data = json.dumps(ev.model_dump(), ensure_ascii=False, separators=(",", ":"))
    head = f"id: {ev.id}\n" if ev.id is not None else ""
    return f"{head}event: {ev.type}\ndata: {data}\n\n"


def _parse_last_id(header: Optional[str], param: Optional[str]) -> Optional[int]:
    for raw in (header, param):
        if raw is not None and raw.strip().isdigit():
            return int(raw.strip())
    return None


async def event_stream(request: Request, bus, store, last_id: Optional[int], keepalive_s: float = KEEPALIVE_S):
    q = bus.subscribe()
    try:
        yield "retry: 2000\n\n"
        cursor = last_id
        if last_id is not None:
            while True:
                batch = await store.events_after(cursor, REPLAY_BATCH)
                for ev in batch:
                    yield format_event(ev)
                    if ev.id is not None:
                        cursor = ev.id
                if len(batch) < REPLAY_BATCH:
                    break
        while True:
            if getattr(q, "dropped", False):
                return  # too slow: close so the browser reconnects with Last-Event-ID
            try:
                ev = await asyncio.wait_for(q.get(), timeout=keepalive_s)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    return
                yield ": keepalive\n\n"
                continue
            if getattr(q, "dropped", False):
                return
            if ev.id is not None and cursor is not None and ev.id <= cursor:
                continue  # already sent during replay
            yield format_event(ev)
            if ev.id is not None:
                cursor = ev.id
    finally:
        bus.unsubscribe(q)


@router.get("/api/v1/events/stream")
async def stream(request: Request, last_id: Optional[str] = None):
    from app.runtime import get_runtime
    rt = get_runtime()
    start = _parse_last_id(request.headers.get("last-event-id"), last_id)
    return StreamingResponse(
        event_stream(request, rt.bus, rt.store, start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
