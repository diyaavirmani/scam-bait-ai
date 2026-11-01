"""Language detection by Unicode script (L-01): curly quotes and emoji never change the result."""
from __future__ import annotations

import re

HINGLISH_MARKERS = frozenset({
    "aapko", "aap", "bas", "karna", "karo", "hai", "hain", "kal", "baje", "nahi", "kya", "bhai", "ji",
    "jaldi", "paise", "bhejo", "mera", "mujhe", "abhi", "haan", "na", "ek", "toh", "kar",
    "nahin", "kaise", "kyun", "kyon", "hoga", "karein", "kijiye", "batao", "bataiye", "accha", "achha",
    "theek", "thik", "aapka", "apna", "tum", "tumhara", "yeh", "woh", "chalo", "beta", "paisa",
})
_WORD_RE = re.compile(r"[a-z]+")


def _is_devanagari(ch: str) -> bool:
    return "ऀ" <= ch <= "ॿ"


def detect_language(text: str) -> str:
    """'hi' if Devanagari (U+0900-U+097F) letters are at least 30% of letters, 'hinglish' when Roman Hindi
    markers appear, else 'en'."""
    if not text:
        return "en"
    deva = 0
    letters = 0
    for ch in text:
        if _is_devanagari(ch):
            deva += 1
            letters += 1
        elif ch.isalpha():
            letters += 1
    if letters and deva / letters >= 0.30:
        return "hi"
    words = _WORD_RE.findall(text.lower())
    if any(w in HINGLISH_MARKERS for w in words):
        return "hinglish"
    return "en"
