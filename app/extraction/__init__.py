"""Extraction: whitespace token split, linear regex per token, validators. Track A, commit 10."""
from __future__ import annotations

from app.models import IntelCandidate


def extract(text: str) -> list[IntelCandidate]:
    """Scammer text only, one message at a time, capped length, no cross-message joining."""
    raise NotImplementedError


def validate(candidates: list[IntelCandidate]) -> list[IntelCandidate]:
    """Python validators (UPI handle, IFSC, phone vs account, Luhn, URL/APK). Drops invalid, dedupes."""
    raise NotImplementedError
