"""Play a realistic FAKE event stream (the docs/DEMO_SCRIPT.md chat plus one call) into a Store and Bus,
so the dashboard pages can be checked without Telegram, Twilio or model keys.

All values are fake on purpose (.example domains, the +91 90000 test number, a made-up account and IFSC).
The pages themselves never contain sample data; they only render what this script puts in the store/bus.

Usage:
  .venv/bin/python scripts/fake_events.py                 # serve on 127.0.0.1:8011 and play the stream
  .venv/bin/python scripts/fake_events.py --port 8022 --delay 0.5
  .venv/bin/python scripts/fake_events.py --no-serve --db out/fake.db   # only fill a DB and exit

The dev server prints a one-off dashboard password (or uses DASHBOARD_PASSWORD if set). Track C.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.events import Bus  # noqa: E402
from app.models import Event  # noqa: E402
from app.runtime import Runtime, set_runtime  # noqa: E402
from app.store import Store  # noqa: E402

CHAT = [
    ("Your OTP for HDFC Bank login is 482913. Do not share it with anyone.", "Okay, thank you.", False, []),
    ("Hi, kal meeting 4 baje hai na?", "Haan, 4 baje theek hai.", False, []),
    ("Hello sir, I am Rahul Mehta from Mumbai, SEBI registered advisor. Your referral code is GOLD77.",
     "Namaste beta, I am Meena. SEBI advisor? What is this about?", True,
     [("name", "Rahul Mehta", "persona"), ("reference_code", "GOLD77", "regex")]),
    ("We run a VIP stock trading group, members are earning 30% weekly returns.",
     "30 percent every week? My son says that is not possible. How does it work?", True, []),
    ("Aapko bas ek app install karna hai, very safe.", "Kaunsa app beta? Mujhe phone chalana zyada nahi aata.", True, []),
    ("Download link: https://stockpro-demo.example/StockPro.apk",
     "The link is not opening, it says file. What is the app name?", True,
     [("url", "https://stockpro-demo.example/StockPro.apk", "regex"), ("apk", "StockPro.apk", "regex")]),
    ("Minimum investment only 10,000 rupees, first profit in 2 days guaranteed.",
     "10,000 is a lot for me. Is there a receipt?", True, [("amount", "10000", "regex")]),
    ("Pay to UPI fakeinvest.demo@okaxis and send screenshot.",
     "Which UPI app should I use? Can you spell the ID again?", True, [("upi", "fakeinvest.demo@okaxis", "regex")]),
    ("If UPI not working, call me on +91 90000 00001.", "Okay, I will note your number.", True,
     [("phone", "+919000000001", "regex")]),
    ("Or do bank transfer: account 000123456789, IFSC ABCD0001234, name StockPro Ventures.",
     "Bank is far for me. Which branch is this?", True,
     [("bank_account", "000123456789", "regex"), ("ifsc", "ABCD0001234", "regex"),
      ("organisation", "StockPro Ventures", "persona")]),
]
SUMMARY = ("Investment and trading scam: a caller posing as SEBI advisor Rahul Mehta pushes a VIP stock group "
           "promising 30 percent weekly returns, an APK download, and payment by UPI or bank transfer.")
CALL = [
    ("caller", "Hello madam, I am calling from the cyber police, your Aadhaar is linked to a money laundering case."),
    ("persona", "Oh no, police? What happened, beta? I did nothing wrong."),
    ("caller", "To clear your name, pay the fine to UPI fakeinvest.demo@okaxis."),
    ("persona", "Fine? How much fine? Let me get my glasses."),
    ("caller", "My officer number is +91 90000 00001."),
]


async def _metric(bus, case_id, channel, step, model, lo, hi, provider="cerebras"):
    ms = random.randint(lo, hi)
    completion = random.randint(40, 220)
    await bus.emit(Event(case_id=case_id, channel=channel, type="metrics.speed", data={
        "step": step, "provider": provider, "model": model, "ms": ms, "queued_ms": random.choice([0, 0, 0, 120, 900]),
        "retries": 0, "tokens_per_s": round(completion / max(ms, 1) * 1000 * 6, 1), "prompt_tokens": random.randint(600, 3200),
        "completion_tokens": completion, "cached_tokens": random.choice([0, 512, 1024, 2048])}))


async def play_chat(store, bus, delay: float, channel: str = "telegram") -> str:
    case = await store.new_case(channel, f"{'tg' if channel == 'telegram' else 'api'}:fake{secrets.token_hex(3)}")
    cid = case["id"]
    for turn, (text, reply, scam, intel) in enumerate(CHAT, start=1):
        mid = await store.add_message(cid, "scammer", text)
        await bus.emit(Event(case_id=cid, channel=channel, type="message.received",
                             data={"role": "scammer", "text": text, "message_id": mid, "turn": turn}))
        await asyncio.sleep(delay / 3)
        await bus.emit(Event(case_id=cid, channel=channel, type="ratelimit.status",
                             data={"model": "qwen-3.8-27b", "rpm_used": min(5, turn % 6), "rpm_limit": 5, "waiting": 1 if turn % 6 == 5 else 0}))
        if turn <= 4:
            pc = round(random.uniform(0.86, 0.97), 2) if scam else round(random.uniform(0.02, 0.12), 2)
            pd = round(random.uniform(0.8, 0.95), 2) if scam else round(random.uniform(0.03, 0.2), 2)
            verdict = "scam" if scam else "not_scam"
            base = {"scam_type": "investment" if scam else "none", "risk": "high" if scam else "none", "recheck": False}
            await _metric(bus, cid, channel, "flag", "qwen-3.8-27b", 180, 420)
            await bus.emit(Event(case_id=cid, channel=channel, type="scam.detected", data={
                **base, "stage": "fast", "p_cerebras": pc, "p_decisions": None, "verdict": verdict,
                "decisions_available": True, "decided_by": "cerebras"}))
            await asyncio.sleep(delay / 3)
            await _metric(bus, cid, channel, "decisions", "gpt-6-luna", 700, 1600, provider="openai")
            await bus.emit(Event(case_id=cid, channel=channel, type="scam.detected", data={
                **base, "stage": "final", "p_cerebras": pc, "p_decisions": pd, "verdict": verdict,
                "decisions_available": turn != 4, "decided_by": "decisions" if turn != 4 else "cerebras"}))
            await store.update_case(cid, verdict=verdict, scam_type=base["scam_type"],
                                    status="engaged" if scam else "watching")
        if turn == 7:
            await bus.emit(Event(case_id=cid, channel=channel, type="task.retrying", data={
                "step": "persona", "model": "gpt-oss-120b", "retry_in_ms": 3000, "reason": "429 per-minute"}))
        await _metric(bus, cid, channel, "persona", "gpt-oss-120b", 350, 900)
        rid = await store.add_message(cid, "persona", reply)
        await bus.emit(Event(case_id=cid, channel=channel, type="persona.reply", data={
            "text": reply, "message_id": rid, "turn": turn, "mode": "engage" if scam else "watch",
            "degraded": False, "language": "hi-Latn" if "beta" in reply or "Haan" in reply else "en"}))
        for kind, value, source in intel:
            if await store.add_intel(cid, kind, value, mid):
                await bus.emit(Event(case_id=cid, channel=channel, type="intel.extracted",
                                     data={"kind": kind, "value": value, "message_id": mid, "source": source}))
        if scam and turn >= 3:
            summ = SUMMARY if turn >= 8 else SUMMARY.split(",")[0] + "."
            await store.update_case(cid, summary=summ)
            await bus.emit(Event(case_id=cid, channel=channel, type="case.summary",
                                 data={"summary": summ, "status": "engaged", "final": False, "report": None}))
        await asyncio.sleep(delay)
    report = {"title": "Investment scam case report", "scam_type": "investment", "risk": "high",
              "findings": ["Claims SEBI registration", "Promises guaranteed weekly returns", "Pushes an APK outside the Play Store"],
              "advice": "File the evidence pack on cybercrime.gov.in or call 1930."}
    await store.update_case(cid, status="closed", summary=SUMMARY)
    await bus.emit(Event(case_id=cid, channel=channel, type="case.summary",
                         data={"summary": SUMMARY, "status": "closed", "final": True, "report": report}))
    return cid


async def play_call(store, bus, delay: float) -> str:
    sid = "CA" + secrets.token_hex(16)
    case = await store.new_case("call", f"call:{sid}")
    cid = case["id"]
    for status in ("ringing", "in-progress", "stream-started"):
        await bus.emit(Event(case_id=cid, channel="call", type="call.status",
                             data={"call_sid": sid, "status": status, "from_masked": "+91 90000 XXXXX", "detail": ""}))
        await asyncio.sleep(delay / 2)
    t = 0
    for i, (speaker, text) in enumerate(CALL):
        words = text.split(" ")
        for k in range(0, len(words), 3):
            await bus.emit(Event(case_id=cid, channel="call", type="transcript.partial",
                                 data={"call_sid": sid, "speaker": speaker, "delta": " ".join(words[k:k + 3]) + " "}))
            await asyncio.sleep(delay / 6)
        dur = 400 * len(words)
        await bus.emit(Event(case_id=cid, channel="call", type="transcript.final",
                             data={"call_sid": sid, "speaker": speaker, "text": text, "start_ms": t, "end_ms": t + dur}))
        await store.add_message(cid, "scammer" if speaker == "caller" else "persona", text)
        t += dur + 300
        if i == 2:
            await _metric(bus, cid, "call", "call_batch", "qwen-3.8-27b", 250, 600)
            await bus.emit(Event(case_id=cid, channel="call", type="scam.detected", data={
                "stage": "final", "p_cerebras": 0.95, "p_decisions": 0.91, "verdict": "scam", "scam_type": "digital_arrest",
                "risk": "critical", "decisions_available": True, "decided_by": "decisions", "recheck": False}))
            await store.update_case(cid, verdict="scam", scam_type="digital_arrest", status="engaged")
            if await store.add_intel(cid, "upi", "fakeinvest.demo@okaxis", None):
                await bus.emit(Event(case_id=cid, channel="call", type="intel.extracted",
                                     data={"kind": "upi", "value": "fakeinvest.demo@okaxis", "message_id": None, "source": "call_batch"}))
        if i == 4 and await store.add_intel(cid, "phone", "+919000000001", None):
            await bus.emit(Event(case_id=cid, channel="call", type="intel.extracted",
                                 data={"kind": "phone", "value": "+919000000001", "message_id": None, "source": "call_batch"}))
    await bus.emit(Event(case_id=cid, channel="call", type="call.status",
                         data={"call_sid": sid, "status": "completed", "from_masked": "+91 90000 XXXXX", "detail": "caller hung up"}))
    summ = ("Digital arrest scam: caller posing as cyber police claims an Aadhaar money laundering case and demands a "
            "fine by UPI, giving an officer phone number.")
    await store.update_case(cid, status="closed", summary=summ)
    await bus.emit(Event(case_id=cid, channel="call", type="case.summary",
                         data={"summary": summ, "status": "closed", "final": True, "report": None}))
    return cid


async def play_all(store, bus, delay: float) -> list[str]:
    return [await play_chat(store, bus, delay), await play_call(store, bus, delay)]


def build_app(store, password: str):
    from fastapi import FastAPI
    from fastapi.responses import RedirectResponse

    import app.events as events
    import app.web as web

    settings = Settings(dashboard_password=password, public_base_url="")
    bus = Bus(store)
    set_runtime(Runtime(settings=settings, store=store, bus=bus))
    fast = FastAPI(title="SCAM-BAIT fake dashboard")
    fast.state.settings = settings
    fast.include_router(events.router)
    fast.include_router(web.router)

    @fast.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/chats")
    return fast, bus


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="out/fake_events.db")
    ap.add_argument("--port", type=int, default=8011)
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between chat turns")
    ap.add_argument("--start-after", type=float, default=5.0, help="seconds before the stream starts")
    ap.add_argument("--no-serve", action="store_true")
    args = ap.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(args.db + suffix):
            os.remove(args.db + suffix)

    if args.no_serve:
        async def fill():
            store = Store(args.db)
            await store.init()
            bus = Bus(store)
            print("cases:", await play_all(store, bus, 0.0))
            await store.close()
        asyncio.run(fill())
        return

    import uvicorn

    password = os.getenv("DASHBOARD_PASSWORD") or secrets.token_urlsafe(9)
    store = Store(args.db)

    async def serve():
        await store.init()
        fast, bus = build_app(store, password)

        async def player():
            await asyncio.sleep(args.start_after)
            print("cases:", await play_all(store, bus, args.delay), flush=True)
        task = asyncio.create_task(player())
        config = uvicorn.Config(fast, host="127.0.0.1", port=args.port, log_level="warning")
        try:
            await uvicorn.Server(config).serve()
        finally:
            task.cancel()
            await store.close()

    if not os.getenv("DASHBOARD_PASSWORD"):
        print(f"one-off dev dashboard password: {password}")
    print(f"open http://127.0.0.1:{args.port}/chats (the stream starts in {args.start_after:.0f} s)", flush=True)
    asyncio.run(serve())


if __name__ == "__main__":
    main()
