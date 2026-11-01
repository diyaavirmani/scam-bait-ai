"""Event bus: persist to the events table first, then fan out to SSE subscribers. Track C, commit 17.

- emit(event) stores the event with store.add_event (which gives it its id), except the high-volume
  types in UNSTORED (transcript.partial, ratelimit.status), whose id stays None.
- Then it puts the event on every subscriber queue without waiting. A subscriber whose queue is full
  is dropped (queue.dropped = True); its SSE stream closes and the browser reconnects with
  Last-Event-ID, which replays the gap from SQLite.
- emit never blocks on a slow subscriber and never raises to the caller.
"""
from __future__ import annotations

import asyncio
import logging

from app.models import Event

log = logging.getLogger("scambait.events")

UNSTORED = frozenset({"transcript.partial", "ratelimit.status"})
QUEUE_SIZE = 1000


class Bus:
    def __init__(self, store, queue_size: int = QUEUE_SIZE) -> None:
        self.store = store
        self.queue_size = queue_size
        self._subs: set[asyncio.Queue] = set()

    async def emit(self, event: Event) -> Event:
        if event.type not in UNSTORED and self.store is not None:
            try:
                event.id = await self.store.add_event(event)
            except Exception:  # the pipeline must keep going even if the DB write fails
                log.exception("event store failed for type=%s", event.type)
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                self._subs.discard(q)
                q.dropped = True  # type: ignore[attr-defined]
                log.warning("dropped a slow SSE subscriber; it will reconnect and replay")
            except Exception:
                log.exception("fan-out failed")
        return event

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        q.dropped = False  # type: ignore[attr-defined]
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


async def emit(event: Event) -> Event:
    """Module-level helper used by every track: emit(Event(...))."""
    from app.runtime import get_runtime
    return await get_runtime().bus.emit(event)


from app.events.sse import router  # noqa: E402  (exposed for app/main.py)

__all__ = ["Bus", "emit", "router", "UNSTORED"]
