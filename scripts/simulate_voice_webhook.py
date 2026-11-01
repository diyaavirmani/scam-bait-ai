"""Smoke test for POST /voice/incoming: sign a fake Twilio form and POST it (old tests/simulate_voice_webhook.py, fixed).

The server checks the signature against PUBLIC_BASE_URL + /voice/incoming, so the request is signed for that
URL (--public-base-url, default env PUBLIC_BASE_URL) while it is sent to --url (default the local server).
Only local targets are allowed unless --allow-remote is given. The auth token is never printed.

Usage:
  TWILIO_AUTH_TOKEN=test-token PUBLIC_BASE_URL=https://example.ngrok.app \
    .venv/bin/python scripts/simulate_voice_webhook.py [--url http://127.0.0.1:8000/voice/incoming]
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlsplit

from twilio.request_validator import RequestValidator

DEFAULT_URL = "http://127.0.0.1:8000/voice/incoming"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def build_request(signed_url: str, auth_token: str, call_sid: str = "CA_SIMULATED_0001",
                  from_number: str = "+919000000001", to_number: str = "+15550000000") -> tuple[dict, dict]:
    """Return (form params, headers) for a Twilio-style signed webhook POST."""
    params = {"CallSid": call_sid, "From": from_number, "To": to_number, "CallStatus": "ringing",
              "Direction": "inbound"}
    signature = RequestValidator(auth_token).compute_signature(signed_url, params)
    return params, {"X-Twilio-Signature": signature}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=DEFAULT_URL, help="where to send the POST")
    ap.add_argument("--public-base-url", default=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
                    help="base URL the server validates against (default env PUBLIC_BASE_URL)")
    ap.add_argument("--auth-token-env", default="TWILIO_AUTH_TOKEN", help="env var holding the auth token")
    ap.add_argument("--call-sid", default="CA_SIMULATED_0001")
    ap.add_argument("--from-number", default="+919000000001")
    ap.add_argument("--allow-remote", action="store_true", help="allow a non-local --url")
    args = ap.parse_args(argv)

    if urlsplit(args.url).hostname not in LOCAL_HOSTS and not args.allow_remote:
        print(f"refusing non-local target {args.url}; pass --allow-remote if you really mean it", file=sys.stderr)
        return 2
    token = os.getenv(args.auth_token_env, "")
    if not token:
        print(f"{args.auth_token_env} is not set", file=sys.stderr)
        return 2
    signed_url = (args.public_base_url + "/voice/incoming") if args.public_base_url else args.url
    params, headers = build_request(signed_url, token, args.call_sid, args.from_number)

    import httpx
    resp = httpx.post(args.url, data=params, headers=headers, timeout=10)
    print(f"HTTP {resp.status_code}")
    print(resp.text)
    ok = resp.status_code == 200 and "<Response>" in resp.text and "<Connect>" in resp.text
    print("OK: TwiML with <Connect><Stream>" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
