"""Per-model async RPM limiter with priority (persona first). Track A, commit 4."""


class RateLimiter:
    def __init__(self, model: str, rpm: int) -> None:
        self.model, self.rpm = model, rpm

    async def acquire(self, priority: int) -> int:
        """Wait for a slot; returns queued milliseconds."""
        raise NotImplementedError

    def status(self) -> dict:
        """{model, rpm_used, rpm_limit, waiting} for ratelimit.status events."""
        raise NotImplementedError
