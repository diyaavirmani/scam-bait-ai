"""One check per docs/AUDIT.md issue that can be tested in code. Test names carry the issue ID."""
import pathlib
import re
import time

from app.detection.ensemble import combine, load_config
from app.detection.prefilter import prefilter
from app.extraction import extract, validate
from app.models import Verdict, utc_now
from app.persona.guard import reply_guard
from app.persona.language import detect_language

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP_SRC = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "app").rglob("*.py"))


def _ms(fn, *args):
    t0 = time.perf_counter()
    fn(*args)
    return (time.perf_counter() - t0) * 1000


def test_M01_no_dead_models_and_pinned_defaults():
    assert "zai-glm" not in APP_SRC and "llama-3.1" not in APP_SRC
    env = (ROOT / ".env.example").read_text()
    assert "PERSONA_MODEL=gpt-oss-120b" in env and "FLAG_MODEL=qwen-3.8-27b" in env


def test_PROV01_only_allowed_providers():
    reqs = (ROOT / "requirements.txt").read_text().lower()
    for banned in ("groq", "deepgram", "elevenlabs", "langchain", "langgraph", "scikit-learn", "psycopg2"):
        assert banned not in reqs and f"import {banned}" not in APP_SRC.lower()


def test_D01_no_text_whitelist():
    for text in ["Dear customer, your HDFC Bank account will be suspended today. Share the OTP.",
                 "Your Amazon delivery is on hold. Pay Rs 49 customs fee.",
                 "Traffic violation challan pending. Pay now."]:
        assert set(prefilter(text)) == {"score", "hits"}  # nothing can mark a message trusted
    assert "isTrusted" not in APP_SRC and "LEGIT_SENDERS" not in APP_SRC  # the old trusted-session mechanism is gone


def test_D02_errors_never_become_safe():
    down = Verdict(source="cerebras", available=False, error="outage")
    dec_down = Verdict(source="decisions", available=False, error="unavailable")
    assert combine(down, dec_down, 0.0, load_config()).verdict == "unknown"


def test_D03_substrings_do_not_trigger():
    for text in ["Hi sir, how is your husband doing?", "I was walking on the footpath near the bank."]:
        assert prefilter(text)["score"] < 0.3


def test_X01_R01_R02_no_catastrophic_backtracking():
    cases = ["http://" + "a" * 160, "you are now " * 240, "txn of " * 1400, "http://" * 1400]
    for text in cases:
        assert _ms(prefilter, text) < 50 and _ms(extract, text) < 50


def test_X03_extraction_false_positives():
    assert not [c for c in extract("Call me at 5pm if any doubt.") if c.kind == "upi"]
    got = validate(extract("If UPI not working, call me on +91 90000 00001."))
    assert [(c.kind, c.value) for c in got] == [("phone", "+919000000001")]


def test_X04_bare_phishing_domain():
    assert any(c.kind == "url" for c in extract("Visit sbi-kyc-update.in to verify"))


def test_P01_P02_no_log_files_and_session_id_rule():
    assert "FileHandler" not in APP_SRC
    from app.models import SESSION_ID_RE
    assert not SESSION_ID_RE.match("/../../escaped") and not SESSION_ID_RE.match("a/b")


def test_A05_constant_time_key_checks():
    assert APP_SRC.count("hmac.compare_digest") >= 2  # API key (when set) and the Telegram webhook secret


def test_C01_single_worker():
    assert "--workers 1" in (ROOT / "scripts/run.sh").read_text()


def test_L01_curly_quotes_and_emoji_stay_english():
    assert detect_language("I\u2019m fine \u2705 thank you") == "en"
    assert detect_language("Aapko bas ek app install karna hai, very safe.") == "hinglish"


def test_H01_no_bracket_placeholders():
    text, _ = reply_guard("Okay, my account is 123456789012 and email meena@example.com")
    assert "[" not in text and "123456789012" not in text and "@" not in text


def test_TS01_utc_timestamps():
    assert utc_now().endswith("+00:00")


def test_DEP01_pinned_requirements():
    lines = [ln for ln in (ROOT / "requirements.txt").read_text().splitlines() if ln and not ln.startswith("#")]
    assert lines and all(re.match(r"^[A-Za-z0-9_.\-\[\]]+==[\w.]+$", ln) for ln in lines)
