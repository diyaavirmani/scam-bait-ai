"""Extraction: whitespace token split, linear checks per token, validators. Track A, commit 10.

Scammer text only, one message at a time (X-03): no joining across messages, no "at" -> "@" rewriting.
Every pattern is anchored to one token or is a simple linear scan (X-01): no nested quantifiers."""
from __future__ import annotations

import re
from typing import Iterable

from app.models import MAX_TEXT_CHARS, IntelCandidate

_STRIP = "()[]{}<>\"'`,;:!?*|“”‘’"
_TLDS = frozenset({
    "com", "in", "net", "org", "co", "io", "app", "xyz", "info", "biz", "online", "site", "top", "club", "live",
    "shop", "store", "link", "me", "ly", "gl", "cc", "tk", "ml", "ga", "cf", "gq", "pw", "ru", "cn", "us", "uk",
    "example", "tech", "website", "click", "page", "cloud", "pro", "vip", "win", "bid", "loan", "work", "money",
})
_SCHEME_RE = re.compile(r"^https?://[^\s/]+", re.IGNORECASE)
_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62})(?:\.[a-z0-9-]{1,63}){1,6}$", re.IGNORECASE)
_UPI_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}@[a-z]{2,32}$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){1,4}$", re.IGNORECASE)
_APK_FILE_RE = re.compile(r"^[\w.-]{1,120}\.apk$", re.IGNORECASE)
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
# Indian mobile: optional +91 / 91 / 0, 10 digits starting 6-9, optional single space or dash after 5 digits.
_PHONE_RE = re.compile(r"(?<![\d+])(?:\+91[\s-]?|91[\s-]?|0)?([6-9]\d{4})[\s-]?(\d{5})(?!\d)")
_DIGIT_RUN_RE = re.compile(r"(?<!\d)\d{9,18}(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_ACCOUNT_WORD_RE = re.compile(r"\b(?:account|acct|a/c|ac|khata|acc)\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(
    r"(?:(?:rs\.?|inr|₹)\s?(\d{1,3}(?:,\d{2,3})+|\d{1,9})(?:\.\d{1,2})?)"
    r"|(?:(\d{1,3}(?:,\d{2,3})+|\d{1,9})\s?(?:rupees|rupaye|rs\b|inr\b))",
    re.IGNORECASE,
)
_CRYPTO_RE = re.compile(r"^(?:0x[a-fA-F0-9]{40}|(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,59}|T[1-9A-HJ-NP-Za-km-z]{33})$")
_NAME_CUE_RE = re.compile(
    r"\b(?:I am|I'm|my name is|this is|name is|name|naam|admin is|manager is|officer is)\s*:?\s+"
    r"([A-Z][a-z][A-Za-z]{0,20}(?: [A-Z][a-z][A-Za-z]{0,20}){0,2})")
_NAME_STOP = frozenset({"Sir", "Madam", "Mam", "Ji", "Bhai", "Calling", "From", "The", "Your", "Here", "Not", "Very"})
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,59}$")
_REF_RE = re.compile(r"^[A-Za-z0-9-]{3,20}$")
_EMP_RE = re.compile(r"^[A-Za-z0-9/-]{2,30}$")


def _clean_token(tok: str) -> str:
    tok = tok.strip(_STRIP)
    # Trailing sentence punctuation (one or more dots) is not part of a link.
    return tok.rstrip(".").strip(_STRIP)


def _is_url(tok: str) -> bool:
    if _SCHEME_RE.match(tok):
        return True
    if "@" in tok:
        return False
    host = tok.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not _HOST_RE.match(host):
        return False
    tld = host.rsplit(".", 1)[-1].lower()
    return tld in _TLDS and not host.replace(".", "").isdigit()


def _is_apk_url(tok: str) -> bool:
    path = tok.split("?", 1)[0].split("#", 1)[0]
    return path.lower().endswith(".apk")


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def normalise_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    return None


def extract(text: str) -> list[IntelCandidate]:
    """Scammer text only, one message at a time, capped length, no cross-message joining."""
    text = (text or "")[:MAX_TEXT_CHARS]
    out: list[IntelCandidate] = []

    def add(kind: str, value: str) -> None:
        out.append(IntelCandidate(kind=kind, value=value, source="regex"))

    # 1. Token pass: URLs, APKs, UPI, email, IFSC, crypto wallets.
    for raw in text.split():
        tok = _clean_token(raw)
        if len(tok) < 3 or len(tok) > 500:
            continue
        if "@" in tok:
            if _EMAIL_RE.match(tok) and "." in tok.split("@", 1)[1]:
                add("email", tok)
            elif _UPI_RE.match(tok):
                add("upi", tok)
            elif tok.startswith("@") and re.match(r"^@[A-Za-z0-9_.]{3,32}$", tok):
                add("social_handle", tok)
            continue
        if _is_url(tok):
            add("url", tok)
            if _is_apk_url(tok):
                add("apk", tok)
            continue
        if _APK_FILE_RE.match(tok):
            add("apk", tok)
            continue
        up = tok.upper()
        if len(up) == 11 and _IFSC_RE.match(up) and tok == up:
            add("ifsc", up)
            continue
        if len(tok) >= 26 and _CRYPTO_RE.match(tok):
            add("crypto_wallet", tok)

    # 2. Phones (linear, within this message only).
    phone_digits: set[str] = set()
    spans: list[tuple[int, int]] = []
    for m in _PHONE_RE.finditer(text):
        p = normalise_phone(m.group(0))
        if p:
            add("phone", p)
            phone_digits.add(p[3:])
            spans.append(m.span())

    def in_phone(a: int, b: int) -> bool:
        return any(a < pe and b > ps for ps, pe in spans)

    # 3. Cards (13-19 digits with Luhn), then bank accounts (9-18 digit run that is not a phone).
    card_spans: list[tuple[int, int]] = []
    for m in _CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits) and not in_phone(*m.span()) and (
                " " in m.group(0) or "-" in m.group(0) or re.search(r"\bcard\b", text, re.IGNORECASE)):
            add("card", digits)
            card_spans.append(m.span())
    for m in _DIGIT_RUN_RE.finditer(text):
        run = m.group(0)
        if in_phone(*m.span()) or any(m.start() < ce and m.end() > cs for cs, ce in card_spans):
            continue
        if normalise_phone(run) or run[-10:] in phone_digits and len(run) <= 12:
            continue
        window = text[max(0, m.start() - 40):m.start()]
        if _ACCOUNT_WORD_RE.search(window) or len(run) >= 11:
            add("bank_account", run)

    # 4. Names the scammer states ("I am Rahul Mehta", "name StockPro Ventures", "admin is Priya").
    for m in _NAME_CUE_RE.finditer(text):
        add("name", m.group(1))

    # 5. Amounts.
    for m in _AMOUNT_RE.finditer(text):
        num = (m.group(1) or m.group(2) or "").replace(",", "")
        if num.isdigit() and int(num) > 0:
            add("amount", f"INR {int(num)}")

    return validate(out)


# ---------- validators ----------
def _norm(c: IntelCandidate) -> str | None:
    v = (c.value or "").strip()
    k = c.kind
    if not v or len(v) > 500:
        return None
    if k == "phone":
        return normalise_phone(v)
    if k == "upi":
        v = v.strip(_STRIP).rstrip(".")
        return v.lower() if _UPI_RE.match(v) else None
    if k == "email":
        v = v.strip(_STRIP).rstrip(".")
        return v.lower() if _EMAIL_RE.match(v) and "." in v.split("@", 1)[1] else None
    if k == "bank_account":
        d = re.sub(r"[\s-]", "", v)
        return d if d.isdigit() and 9 <= len(d) <= 18 else None
    if k == "ifsc":
        v = v.upper().replace(" ", "")
        return v if _IFSC_RE.match(v) else None
    if k == "card":
        d = re.sub(r"[\s-]", "", v)
        return d if d.isdigit() and 13 <= len(d) <= 19 and _luhn(d) else None
    if k == "url":
        v = _clean_token(v)
        return v if " " not in v and _is_url(v) else None
    if k == "apk":
        v = _clean_token(v)
        if " " in v:
            return None
        return v if (_is_url(v) and _is_apk_url(v)) or _APK_FILE_RE.match(v) else None
    if k == "crypto_wallet":
        return v if _CRYPTO_RE.match(v) else None
    if k == "social_handle":
        return v if re.match(r"^@?[A-Za-z0-9_.]{3,40}$", v) else None
    if k == "name":
        v = " ".join(w for w in v.split() if w not in _NAME_STOP) if c.source == "regex" else " ".join(v.split())
        return v if _NAME_RE.match(v) and sum(ch.isalpha() for ch in v) >= 2 else None
    if k == "reference_code":
        return v.upper() if _REF_RE.match(v) else None
    if k == "employee_id":
        return v.upper() if _EMP_RE.match(v) else None
    if k == "organisation":
        v = " ".join(v.split())
        return v if 2 <= len(v) <= 80 and any(ch.isalpha() for ch in v) else None
    if k == "amount":
        v = " ".join(v.split())
        if v.startswith("INR ") and v[4:].isdigit():
            return v
        m = re.search(r"\d[\d,]{0,20}", v)
        digits = m.group(0).replace(",", "") if m else ""
        return f"INR {int(digits)}" if digits.isdigit() and 0 < int(digits) < 10**12 else None
    return None


def validate(candidates: Iterable[IntelCandidate]) -> list[IntelCandidate]:
    """Python validators (UPI handle, IFSC, phone vs account, Luhn, URL/APK). Drops invalid, dedupes by
    (kind, normalised value), drops a bank account equal to a phone's digits. Order is first seen."""
    seen: set[tuple[str, str]] = set()
    kept: list[IntelCandidate] = []
    for c in candidates:
        try:
            v = _norm(c)
        except Exception:
            v = None
        if not v or (c.kind, v) in seen:
            continue
        seen.add((c.kind, v))
        kept.append(IntelCandidate(kind=c.kind, value=v, source=c.source))
    phone_digits = {c.value[3:] for c in kept if c.kind == "phone"}
    return [c for c in kept if not (c.kind == "bank_account" and (
        c.value in phone_digits or c.value[-10:] in phone_digits and len(c.value) <= 12 or normalise_phone(c.value)))]
