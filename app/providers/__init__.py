"""Model providers. Track A, commit 4."""
PRIORITY_PERSONA = 0  # served first
PRIORITY_LIVE = 1  # detection flag, call batches
PRIORITY_BACKGROUND = 2  # reports, re-checks, evals


class ProviderError(Exception):
    """kind: rate_limit_quota (hourly/daily bucket: stop), outage (5xx/timeout after retries), bad_output, unavailable."""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
