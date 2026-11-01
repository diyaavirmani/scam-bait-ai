from __future__ import annotations


def prefilter(text: str) -> dict:
    """Word-boundary, linear-time rules on capped text. Returns {score: float, hits: [str]}. Never whitelists by text."""
    raise NotImplementedError
