"""Milestone 10: extraction per message (DEMO_SCRIPT), validators, timing guards (X-01..X-04)."""
from __future__ import annotations

import random
import string
import time

import pytest

from app.extraction import extract, validate
from app.models import IntelCandidate


def kv(text):
    return [(c.kind, c.value) for c in extract(text)]


def test_demo_message_4_url_and_apk():
    assert kv("Download link: https://stockpro-demo.example/StockPro.apk") == [
        ("url", "https://stockpro-demo.example/StockPro.apk"), ("apk", "https://stockpro-demo.example/StockPro.apk")]


def test_demo_message_6_upi():
    assert kv("Pay to UPI fakeinvest.demo@okaxis and send screenshot.") == [("upi", "fakeinvest.demo@okaxis")]


def test_demo_message_7_phone_once_not_bank_account():
    assert kv("If UPI not working, call me on +91 90000 00001.") == [("phone", "+919000000001")]


@pytest.mark.parametrize("raw", ["9000000001", "+919000000001", "919000000001", "09000000001", "+91-90000-00001",
                                 "90000-00001"])
def test_phone_formats_never_bank_account(raw):
    assert kv(f"call {raw} now") == [("phone", "+919000000001")]


def test_demo_message_8_no_bogus_upi():
    assert kv("Call me at 5pm if any doubt.") == []
    assert kv("me@5pm") == []


def test_demo_message_9_account_ifsc_name():
    out = kv("Or do bank transfer: account 000123456789, IFSC ABCD0001234, name StockPro Ventures.")
    assert ("bank_account", "000123456789") in out and ("ifsc", "ABCD0001234") in out
    assert ("name", "StockPro Ventures") in out
    assert not any(k == "phone" for k, _ in out)


def test_demo_message_12_second_url():
    assert kv("Join here also: https://vip-trading-demo.example/join") == [
        ("url", "https://vip-trading-demo.example/join")]


def test_demo_other_messages():
    assert ("name", "Rahul Mehta") in kv(
        "Hello sir, I am Rahul Mehta from Mumbai, SEBI registered advisor. Your referral code is GOLD77.")
    assert ("name", "Priya") in kv("Our group admin is Priya, she will add you on WhatsApp.")
    assert kv("Minimum investment only 10,000 rupees, first profit in 2 days guaranteed.") == [("amount", "INR 10000")]
    assert kv("Your OTP for HDFC Bank login is 482913. Do not share it with anyone.") == []
    assert kv("Hi, kal meeting 4 baje hai na?") == []


def test_bare_domain_and_apk_file_and_email_and_card():
    assert kv("Update KYC at sbi-kyc-update.in today.") == [("url", "sbi-kyc-update.in")]
    assert kv("Install KYC_update.apk") == [("apk", "KYC_update.apk")]
    assert kv("mail a.b@gmail.com") == [("email", "a.b@gmail.com")]
    assert kv("card 4111 1111 1111 1111") == [("card", "4111111111111111")]
    assert kv("card 4111 1111 1111 1112") == []


def test_validate_normalises_dedupes_and_drops_phone_as_account():
    out = validate([
        IntelCandidate(kind="phone", value="+91 90000 00001", source="persona"),
        IntelCandidate(kind="bank_account", value="9000000001", source="persona"),
        IntelCandidate(kind="upi", value="FakeInvest.Demo@OKAXIS", source="persona"),
        IntelCandidate(kind="upi", value="fakeinvest.demo@okaxis", source="persona"),
        IntelCandidate(kind="upi", value="me@5pm", source="persona"),
        IntelCandidate(kind="ifsc", value="abcd0001234", source="persona"),
        IntelCandidate(kind="name", value="Rahul  Mehta", source="persona"),
        IntelCandidate(kind="name", value="x", source="persona"),
        IntelCandidate(kind="reference_code", value="gold77", source="persona"),
        IntelCandidate(kind="reference_code", value="no spaces allowed", source="persona"),
        IntelCandidate(kind="organisation", value="SEBI", source="persona"),
        IntelCandidate(kind="url", value="not a url", source="persona"),
        IntelCandidate(kind="amount", value="Rs. 10,000", source="persona"),
    ])
    assert [(c.kind, c.value) for c in out] == [
        ("phone", "+919000000001"), ("upi", "fakeinvest.demo@okaxis"), ("ifsc", "ABCD0001234"),
        ("name", "Rahul Mehta"), ("reference_code", "GOLD77"), ("organisation", "SEBI"), ("amount", "INR 10000")]
    assert all(c.source == "persona" for c in out)


def test_no_joining_across_messages():
    assert kv("my number is 90000") == [] and kv("00001 ok") == []


def _timed(text):
    t = time.perf_counter()
    extract(text)
    return time.perf_counter() - t


def test_timing_random_paste():
    rnd = random.Random(7)
    paste = "".join(rnd.choice(string.ascii_letters + string.digits + string.punctuation + "  ") for _ in range(2000))
    assert _timed(paste) < 0.05


@pytest.mark.parametrize("text", ["http://" * 10000, "http:// " * 10000, "a@" * 20000, "1" * 20000,
                                  "https://x." * 5000 + "apk", ("1 " * 20000)])
def test_timing_adversarial(text):
    assert _timed(text) < 0.05
