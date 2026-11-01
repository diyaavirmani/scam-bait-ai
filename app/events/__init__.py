"""Event bus: persist to the events table first, then fan out to SSE subscribers. Track C, commit 17."""
from __future__ import annotations

import asyncio

from app.models import Event


class Bus:
    def __init__(self, store) -> None:
        self.store = store

    async def emit(self, event: Event) -> Event: raise NotImplementedError
    def subscribe(self) -> asyncio.Queue: raise NotImplementedError
    def unsubscribe(self, q: asyncio.Queue) -> None: raise NotImplementedError


async def emit(event: Event) -> Event:
    """Module-level helper used by every track: emit(Event(...))."""
    from app.runtime import get_runtime
    return await get_runtime().bus.emit(event)
