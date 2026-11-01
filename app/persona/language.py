from __future__ import annotations


def detect_language(text: str) -> str:
    """'hi' if Devanagari (U+0900-U+097F) letters dominate, 'hinglish' for Roman Hindi, else 'en'."""
    raise NotImplementedError
