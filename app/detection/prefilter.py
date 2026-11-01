"""Stage 1 regex prefilter. Track A, commit 5.

Linear time on capped text (R-01, R-02): one tokenising pass (\\w+), set membership for single words, padded
substring checks for short phrases, and one bounded UPI pattern. No .* chains, no nested quantifiers.
Whole-word matching only, so 'otp' never matches inside 'footpath' and 'band' never inside 'husband' (D-03).
It is a feature score, never a verdict: nothing here marks a message trusted (D-01).
"""
from __future__ import annotations

import re

from app.models import MAX_TEXT_CHARS

_WORD_RE = re.compile(r"\w+")
_UPI_RE = re.compile(r"\b[a-z0-9._-]{2,64}@[a-z]{2,32}\b(?!\.)")  # bounded; '@gmail.com' and 'me@5pm' do not match

# feature -> (weight, single words, phrases). Phrases are matched as whole words in the space-joined token string.
FEATURES: dict[str, tuple[float, frozenset[str], tuple[str, ...]]] = {
    "payment_ask": (0.2, frozenset({"pay", "paying", "payment", "transfer", "deposit", "remit", "fee", "fees",
                                    "charges", "fine", "penalty", "refundable", "processing"}),
                    ("send money", "send screenshot", "send the amount", "bank transfer", "paise bhejo",
                     "paisa bhejo", "payment karo")),
    "credential_ask": (0.3, frozenset(), ("share otp", "send otp", "tell otp", "give otp", "otp batao", "otp bhejo",
                                          "share the otp", "send the otp", "tell me the otp", "share your otp",
                                          "enter otp", "upi pin", "share pin", "your pin", "your password",
                                          "cvv", "card number", "net banking password", "login details",
                                          "trading login")),
    "otp_mention": (0.05, frozenset({"otp", "pin", "password", "cvv", "mpin", "passcode"}), ()),
    "kyc": (0.2, frozenset({"kyc", "rekyc"}), ("update your pan", "pan card update", "aadhaar update")),
    "urgency": (0.15, frozenset({"urgent", "urgently", "immediately", "hurry", "asap", "quickly", "expire",
                                 "expires", "expired", "expiring"}),
                ("last chance", "act now", "right now", "only today", "today only", "slots left", "within 24 hours",
                 "within 2 hours", "limited slots", "limited seats", "before it is too late")),
    "threat": (0.3, frozenset({"arrest", "arrested", "warrant", "jail", "laundering", "seized", "suspended",
                               "blocked", "frozen", "freeze", "illegal", "fir", "prosecution", "summons"}),
               ("legal action", "case registered", "digital arrest", "account will be blocked", "narcotics found",
                "money laundering")),
    "guaranteed_returns": (0.25, frozenset({"guaranteed", "guarantee", "assured", "profit", "profits", "returns",
                                            "earning", "earnings", "doubled", "multibagger"}),
                           ("double your money", "risk free", "fixed return", "daily income", "weekly returns")),
    "investment_pitch": (0.1, frozenset({"stock", "stocks", "trading", "crypto", "bitcoin", "usdt", "forex", "ipo",
                                          "invest", "investment", "investing", "portfolio"}),
                         ("trading group", "vip group", "stock tips")),
    "install_ask": (0.15, frozenset(), ("install", "download", "install karna", "download karo", "app install")),
    "remote_access": (0.35, frozenset({"anydesk", "teamviewer", "quicksupport", "rustdesk", "airdroid", "alpemix",
                                       "screenshare"}),
                      ("screen share", "screen sharing", "remote access")),
    "impersonation": (0.15, frozenset({"sebi", "rbi", "cbi", "police", "trai", "npci", "uidai", "customs",
                                       "cybercrime", "hdfc", "sbi", "icici", "kotak", "pnb", "fedex", "dhl",
                                       "interpol", "narcotics"}),
                      ("cyber cell", "cyber police", "income tax", "enforcement directorate", "crime branch",
                       "customer care", "registered advisor", "bank manager", "bank officer")),
    "hinglish_urgency": (0.15, frozenset({"jaldi", "turant", "fauran", "warna", "jald"}),
                         ("abhi karo", "abhi bhejo", "aaj hi", "nahi toh", "nahi to", "time nahi")),
    "lottery_prize": (0.2, frozenset({"lottery", "jackpot", "winner", "won", "prize", "cashback", "reward"}),
                      ("you have won", "claim your")),
    "job_task": (0.15, frozenset(), ("part time job", "work from home", "like videos", "simple tasks",
                                     "earn daily", "task based")),
}


def prefilter(text: str) -> dict:
    """Word-boundary, linear-time rules on capped text. Returns {score: float, hits: [str]}. Never whitelists by text."""
    low = (text or "")[:MAX_TEXT_CHARS].lower()
    tokens = _WORD_RE.findall(low)
    words = set(tokens)
    joined = " " + " ".join(tokens) + " "
    hits: list[str] = []
    score = 0.0
    for name, (weight, singles, phrases) in FEATURES.items():
        if (singles and not words.isdisjoint(singles)) or any(f" {p} " in joined for p in phrases):
            hits.append(name)
            score += weight
    if "credential_ask" in hits and "otp_mention" in hits:  # do not double count the OTP word
        hits.remove("otp_mention")
        score -= FEATURES["otp_mention"][0]
    if "://" in low or "www." in low:
        hits.append("link")
        score += 0.1
    if ".apk" in low or "apk" in words:
        hits.append("apk")
        score += 0.25
    if "upi" in words or _UPI_RE.search(low):
        hits.append("upi")
        score += 0.2
    return {"score": round(min(1.0, max(0.0, score)), 3), "hits": hits}
