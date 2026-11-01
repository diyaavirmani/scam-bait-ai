"""Logging to stdout only, with redaction of identifiers (LOG-01). No per-session log files (P-01, P-02)."""
from __future__ import annotations

import logging
import re
import sys

_PATTERNS = [
    (re.compile(r"\b[\w.+-]{1,64}@[\w.-]{2,64}\b"), "<id@redacted>"),  # emails and UPI IDs
    (re.compile(r"(?<!\d)(\+?\d[\d -]{5,}\d)(?!\d)"), lambda m: "<digits:" + m.group(1)[-2:] + ">"),
    (re.compile(r"(?i)\b(bearer|api[_-]?key|token|secret)\b\s*[:=]?\s*\S+"), r"\1 <redacted>"),
]


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = None
        except Exception:
            pass
        return True


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
