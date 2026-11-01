"""Per-model async RPM limiter with priority (persona first). Track A, commit 4.

Sliding 60 s window. Waiters are served lowest priority number first, then in arrival order.
It does not read rate-limit headers; a 429 that still happens is retried by the caller on the same model.
"""
from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from collections import deque

WINDOW_S = 60.0


class RateLimiter:
    def __init__(self, model: str, rpm: int, window_s: float = WINDOW_S) -> None:
        self.model, self.rpm = model, max(1, int(rpm))
        self.window_s = window_s
        self._sent: deque[float] = deque()  # monotonic timestamps of granted slots
        self._heap: list[tuple[int, int, asyncio.Future]] = []
        self._seq = itertools.count()
        self._wake: asyncio.TimerHandle | None = None

    def _prune(self, now: float) -> None:
        while self._sent and now - self._sent[0] >= self.window_s:
            self._sent.popleft()

    def _dispatch(self) -> None:
        """Grant free slots to the best waiters; schedule a wake-up when the window frees the next slot."""
        self._wake = None
        now = time.monotonic()
        self._prune(now)
        while self._heap and len(self._sent) < self.rpm:
            _, _, fut = heapq.heappop(self._heap)
            if fut.done():  # cancelled waiter
                continue
            self._sent.append(now)
            fut.set_result(None)
        if self._heap and self._sent:
            delay = max(0.0, self.window_s - (now - self._sent[0])) + 0.001
            self._wake = asyncio.get_running_loop().call_later(delay, self._dispatch)

    async def acquire(self, priority: int) -> int:
        """Wait for a slot; returns queued milliseconds."""
        t0 = time.monotonic()
        self._prune(t0)
        if not self._heap and len(self._sent) < self.rpm:
            self._sent.append(t0)
            return 0
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        heapq.heappush(self._heap, (priority, next(self._seq), fut))
        if self._wake is None:
            self._dispatch()
        try:
            await fut
        except asyncio.CancelledError:
            if not fut.done():
                fut.cancel()
            raise
        return int((time.monotonic() - t0) * 1000)

    def status(self) -> dict:
        """{model, rpm_used, rpm_limit, waiting} for ratelimit.status events."""
        self._prune(time.monotonic())
        waiting = sum(1 for _, _, f in self._heap if not f.done())
        return {"model": self.model, "rpm_used": len(self._sent), "rpm_limit": self.rpm, "waiting": waiting}
