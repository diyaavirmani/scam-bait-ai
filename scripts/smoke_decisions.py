"""One real Decisions call (commit 7 smoke test). Saves a redacted response to tests/fixtures/decisions_sample.json.

Run only with the user's keys in .env: .venv/bin/python scripts/smoke_decisions.py
Prints the HTTP outcome and the field names, never the key.
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.providers import ProviderError, build_clients  # noqa: E402

QUESTIONS_SRC = pathlib.Path("testset/providers/decisions_provider.py")
MESSAGE = "We run a VIP stock trading group, members are earning 30% weekly returns."  # DEMO_SCRIPT message 2


def _redact(obj):
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in ("id", "request_id", "user", "organization", "project") else _redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


async def main() -> int:
    ns: dict = {}
    exec(compile(QUESTIONS_SRC.read_text(), str(QUESTIONS_SRC), "exec"), ns)
    _, openai_client = build_clients(get_settings())
    try:
        out = await openai_client.decisions(input=MESSAGE, questions=ns["QUESTIONS"], cache_key="sb-detect-v1")
    except ProviderError as exc:
        print(f"Decisions call failed: {exc.kind}: {str(exc)[:200]}")
        return 1
    path = pathlib.Path("tests/fixtures/decisions_sample.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"_note": "real response, redacted, 1 Nov 2026", "input": MESSAGE,
                                "response": _redact(out)}, indent=2, ensure_ascii=False))
    print("Decisions call ok; top-level fields:", sorted(out.keys()))
    print("saved", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
