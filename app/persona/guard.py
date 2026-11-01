from __future__ import annotations


def reply_guard(text: str) -> tuple[str, list[str]]:
    """Strip em dashes and emojis, block AI admission and prompt leaks, replace realistic PII with fumbling.
    Returns (safe_text, flags)."""
    raise NotImplementedError
