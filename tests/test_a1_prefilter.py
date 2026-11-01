"""Milestone 05: prefilter is word-boundary, linear time, and never a whitelist."""
import time

import pytest

from app.detection.prefilter import prefilter

LOW = ["Hi sir, how is your husband doing?", "I was walking on the footpath near the bank.",
       "Hi, kal meeting 4 baje hai na?"]
DEMO = {
    2: "We run a VIP stock trading group, members are earning 30% weekly returns.",
    4: "Download link: https://stockpro-demo.example/StockPro.apk",
    6: "Pay to UPI fakeinvest.demo@okaxis and send screenshot.",
}


@pytest.mark.parametrize("text", LOW)
def test_ordinary_chat_scores_low(text):
    out = prefilter(text)
    assert out["score"] < 0.1, out


def test_no_substring_matches():
    assert "otp_mention" not in prefilter("footpath")["hits"]
    assert prefilter("my husband and his band")["score"] == 0.0
    assert "upi" not in prefilter("cupid")["hits"]


@pytest.mark.parametrize("n", sorted(DEMO))
def test_demo_scam_messages_score_higher(n):
    low_max = max(prefilter(t)["score"] for t in LOW)
    out = prefilter(DEMO[n])
    assert out["score"] >= 0.3 and out["score"] > low_max, out


def test_features():
    assert "apk" in prefilter(DEMO[4])["hits"] and "link" in prefilter(DEMO[4])["hits"]
    assert "upi" in prefilter(DEMO[6])["hits"]
    assert "remote_access" in prefilter("Please install AnyDesk so I can help")["hits"]
    assert "threat" in prefilter("A warrant is issued, you will be arrested today")["hits"]
    assert "impersonation" in prefilter("This is SEBI registered advisor")["hits"]
    assert "hinglish_urgency" in prefilter("jaldi karo warna account band")["hits"]
    assert "credential_ask" in prefilter("please share otp now")["hits"]


def test_no_bogus_upi_or_email_as_upi():
    assert "upi" not in prefilter("Call me at 5pm if any doubt. me@5pm")["hits"]
    assert "upi" not in prefilter("mail me at someone@gmail.com")["hits"]


def test_never_whitelists():
    out = prefilter("Amazon delivery: your order id 123 credited. Pay fee via UPI fakeinvest.demo@okaxis")
    assert out["score"] > 0.3
    assert set(out) == {"score", "hits"}  # no trusted flag of any kind


@pytest.mark.parametrize("text", [
    "you are now " * 240,  # 2,880 chars (AUDIT R-02)
    ("txn of " * 1430)[:10000],  # 10k chars (AUDIT R-01)
    "http://" + "a" * 160,
    "a@" * 5000,
    "x" * 10000,
])
def test_pathological_inputs_fast(text):
    t0 = time.perf_counter()
    prefilter(text)
    assert (time.perf_counter() - t0) * 1000 < 50
