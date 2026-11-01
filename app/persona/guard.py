"""Persona reply guard: style, AI-admission and prompt-leak block, in-character PII fumbling (H-01)."""
from __future__ import annotations

import re

MAX_REPLY_CHARS = 350

DEFLECTION = "Bot? Beta, I am just slow with this phone. What were you saying?"
EMPTY_FALLBACK = "Sorry, I did not understand. Can you say that again slowly?"

EM_DASH = chr(0x2014)
# Emoji and pictographs (same ranges as tests/test_style.py plus common extras), built from code points so the
# source holds no literal symbols.
_EMOJI_RANGES = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0xFE0F, 0xFE0F), (0x200D, 0x200D), (0x2B00, 0x2BFF),
                 (0x2300, 0x23FF)]
_EMOJI_RE = re.compile(
    "[" + "".join(chr(a) + "-" + chr(b) for a, b in _EMOJI_RANGES) + "]"
)

_LEAK_RE = re.compile(
    r"\b(?:i\s*(?:am|'m|’m)\s+(?:an?\s+)?(?:ai|a\.i\.|bot|chat\s*bot|robot|language\s+model|assistant|"
    r"virtual\s+assistant|computer\s+program|program)\b"
    r"|as\s+an?\s+(?:ai|language\s+model|assistant)\b"
    r"|language\s+model|large\s+language|\bllm\b|system\s+prompt|my\s+(?:instructions|prompt|programming)"
    r"|honey\s*pot|cerebras|openai|open\s+ai|chatgpt|\bgpt\b|gpt-|gpt\s*oss|qwen|anthropic|claude"
    r"|artificial\s+intelligence|scam\s*bait|i\s+was\s+(?:instructed|programmed|told\s+to\s+pretend))",
    re.IGNORECASE,
)

_URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|net|org|co|io|app|xyz|info|example)\b(?:/\S*)?",
                     re.IGNORECASE)
_EMAIL_OR_UPI_RE = re.compile(r"\b[\w.\-]+@[\w.\-]+\b")
_DIGITS_RE = re.compile(r"\d(?:[\s\-]?\d){5,}")

_FUMBLE_NUMBER = "nine eight... wait, my glasses"
_FUMBLE_ID = "that thing with the at sign... I cannot read it, the letters are too small"
_FUMBLE_LINK = "that link thing... my grandson handles those"


def _strip_style(text: str) -> str:
    text = text.replace(" " + EM_DASH + " ", ", ").replace(EM_DASH, ", ")
    text = _EMOJI_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def reply_guard(text: str) -> tuple[str, list[str]]:
    """Strip em dashes and emojis, block AI admission and prompt leaks, replace realistic PII with fumbling.
    Returns (safe_text, flags)."""
    flags: list[str] = []
    text = (text or "").strip()
    if EM_DASH in text:
        flags.append("em_dash")
    if _EMOJI_RE.search(text):
        flags.append("emoji")
    text = _strip_style(text)
    if _LEAK_RE.search(text):
        flags.append("leak")
        return DEFLECTION, flags
    new = _URL_RE.sub(_FUMBLE_LINK, text)
    new = _EMAIL_OR_UPI_RE.sub(_FUMBLE_ID, new)
    new = _DIGITS_RE.sub(_FUMBLE_NUMBER, new)
    if new != text:
        flags.append("pii")
        text = new
    # Remove bracket placeholders the model might still produce (H-01).
    if re.search(r"\[[^\]]{0,40}\]", text):
        flags.append("placeholder")
        text = re.sub(r"\s*\[[^\]]{0,40}\]", "", text).strip()
    if len(text) > MAX_REPLY_CHARS:
        flags.append("truncated")
        cut = text[:MAX_REPLY_CHARS]
        end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        text = cut[: end + 1] if end > 80 else cut.rsplit(" ", 1)[0] + "..."
    if not text:
        flags.append("empty")
        text = EMPTY_FALLBACK
    return text, flags
