import logging

from app.logs import RedactingFilter, redact


def test_redacts_identifiers_and_secrets():
    out = redact("pay fakeinvest.demo@okaxis or call +91 90000 00001, acct 000123456789, Bearer abc.def")
    assert "okaxis" not in out and "90000" not in out and "000123456789" not in out and "abc.def" not in out
    assert "<digits:01>" in out and "<digits:89>" in out


def test_filter_applies_to_records():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "upi %s", ("a.b@ybl",), None)
    RedactingFilter().filter(rec)
    assert rec.getMessage() == "upi <id@redacted>"
