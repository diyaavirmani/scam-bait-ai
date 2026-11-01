"""Step 1 key smoke tests with real APIs. Prints statuses, timings and field names only, never secrets.

  .venv/bin/python -B scripts/smoke_providers.py
"""
import asyncio
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import openai  # noqa: E402
import websockets  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.providers import build_clients  # noqa: E402
from app.voice import live_protocol as lp  # noqa: E402

S = get_settings()
RESULTS: dict = {}
TINY_SCHEMA = {"type": "object", "additionalProperties": False,
               "properties": {"ok": {"type": "boolean"}, "word": {"type": "string"}}, "required": ["ok", "word"]}


SECRETS = [v for v in (S.openai_api_key, S.cerebras_api_key, S.twilio_auth_token, S.telegram_bot_token,
                        S.telegram_webhook_secret, S.api_key, S.dashboard_password) if v]


def scrub(text: str) -> str:
    for v in SECRETS:
        text = text.replace(v, "<redacted>")
    return text


def show(name, data):
    line = scrub(json.dumps(data, default=str))
    RESULTS[name] = json.loads(line)
    print(f"{name}: {line}", flush=True)


async def cerebras():
    client = openai.AsyncOpenAI(base_url=S.cerebras_base_url, api_key=S.cerebras_api_key, max_retries=0, timeout=30)
    t0 = time.perf_counter()
    try:
        raw = await client.models.with_raw_response.list()
        ids = sorted(m.id for m in raw.parse().data)
        show("cerebras.models", {"http": raw.http_response.status_code, "ms": int((time.perf_counter() - t0) * 1000),
                                 "ids": ids, "persona_model_served": S.persona_model in ids,
                                 "flag_model_served": S.flag_model in ids})
    except Exception as e:
        show("cerebras.models", {"error": type(e).__name__, "status": getattr(e, "status_code", None)})
    for model, effort in ((S.flag_model, "none"), (S.persona_model, "low")):
        t0 = time.perf_counter()
        try:
            raw = await client.chat.completions.with_raw_response.create(
                model=model, messages=[{"role": "user", "content": 'Reply with ok=true and word="ready".'}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "tiny", "strict": True, "schema": TINY_SCHEMA}},
                max_completion_tokens=300, reasoning_effort=effort)
            ms = int((time.perf_counter() - t0) * 1000)
            resp = raw.parse()
            extra = resp.model_extra or {}
            ti = extra.get("time_info") or {}
            ct = resp.usage.completion_tokens if resp.usage else None
            tps = round(ct / ti["completion_time"], 1) if ct and ti.get("completion_time") else None
            rl = {k: v for k, v in raw.http_response.headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
            show(f"cerebras.{model}", {"http": raw.http_response.status_code, "ms": ms,
                                       "json_valid": json.loads(resp.choices[0].message.content).get("ok") is True,
                                       "completion_tokens": ct, "time_info": ti, "tokens_per_s": tps,
                                       "ratelimit_headers": rl})
        except Exception as e:
            show(f"cerebras.{model}", {"error": type(e).__name__, "status": getattr(e, "status_code", None),
                                       "message": str(e)[:200]})
    await client.close()


async def moderation():
    _, oai = build_clients(S)
    t0 = time.perf_counter()
    try:
        out = await oai.moderate("Pay the fine now or the police will arrest you today.")
        show("openai.moderation", {"ok": True, "ms": int((time.perf_counter() - t0) * 1000),
                                   "flagged": out.get("flagged"), "fields": sorted(out)})
    except Exception as e:
        show("openai.moderation", {"error": type(e).__name__, "message": str(e)[:200]})
    await oai.client.close()
    await oai.http.aclose()


async def gpt_live():
    seen, t0 = [], time.perf_counter()
    try:
        async with websockets.connect(lp.LIVE_URL, additional_headers=lp.headers(S.openai_api_key),
                                      open_timeout=15, max_size=None) as ws:
            await ws.send(json.dumps(lp.session_start(S.live_model, lp.PERSONA_INSTRUCTIONS)))
            started_ms = None
            deadline = time.monotonic() + 20
            greeted = False
            while time.monotonic() < deadline:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                etype = msg.get("type", "?")
                if etype not in seen:
                    seen.append(etype)
                if etype == lp.ERROR:
                    show("gpt_live.error_event", {"error": msg.get("error", msg)})
                if etype == lp.SESSION_STARTED and not greeted:
                    started_ms = int((time.perf_counter() - t0) * 1000)
                    await ws.send(json.dumps(lp.instructions_append(lp.GREETING_INSTRUCTION)))
                    await ws.send(json.dumps(lp.commentary_append(lp.GREETING_COMMENTARY)))
                    greeted = True
                if lp.OUTPUT_AUDIO_DELTA in seen and lp.OUTPUT_TRANSCRIPT_DELTA in seen:
                    break
            await ws.send(json.dumps(lp.session_close()))
            try:
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=end - time.monotonic()))
                    if msg.get("type") not in seen:
                        seen.append(msg.get("type"))
                    if msg.get("type") == lp.SESSION_CLOSED:
                        break
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                pass
        expected = [lp.SESSION_STARTED, lp.OUTPUT_AUDIO_DELTA, lp.OUTPUT_TRANSCRIPT_DELTA, lp.SESSION_CLOSED]
        show("gpt_live", {"access": lp.SESSION_STARTED in seen, "session_started_ms": started_ms, "events_seen": seen,
                          "expected_present": {e: e in seen for e in expected},
                          "input_transcript_delta": "not checked (needs caller speech)"})
    except websockets.InvalidStatus as e:
        show("gpt_live", {"access": False, "http": e.response.status_code})
    except Exception as e:
        show("gpt_live", {"access": False, "error": type(e).__name__, "message": str(e)[:200]})


async def twilio():
    auth = (S.twilio_account_sid, S.twilio_auth_token)
    base = f"https://api.twilio.com/2010-04-01/Accounts/{S.twilio_account_sid}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(base + ".json", auth=auth)
        acct = r.json() if r.status_code == 200 else {}
        r2 = await c.get(base + "/IncomingPhoneNumbers.json", params={"PhoneNumber": S.twilio_phone_number}, auth=auth)
        nums = r2.json().get("incoming_phone_numbers", []) if r2.status_code == 200 else []
        voice = {}
        if nums:
            n = nums[0]
            voice = {"voice_url_set": bool(n.get("voice_url")), "voice_method": n.get("voice_method"),
                     "status_callback_set": bool(n.get("status_callback")),
                     "capabilities": n.get("capabilities")}
        show("twilio", {"account_http": r.status_code, "account_status": acct.get("status"),
                        "account_type": acct.get("type"), "numbers_http": r2.status_code,
                        "number_belongs_to_account": len(nums) == 1, "number_config": voice})


async def telegram():
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"https://api.telegram.org/bot{S.telegram_bot_token}/getMe")
        body = r.json()
        res = body.get("result", {})
        w = await c.get(f"https://api.telegram.org/bot{S.telegram_bot_token}/getWebhookInfo")
        wi = w.json().get("result", {})
        show("telegram", {"http": r.status_code, "ok": body.get("ok"), "is_bot": res.get("is_bot"),
                          "username": res.get("username"), "webhook_url_set": bool(wi.get("url")),
                          "pending_update_count": wi.get("pending_update_count")})


async def main():
    for step in (cerebras, moderation, gpt_live, twilio, telegram):
        try:
            await step()
        except Exception as e:
            show(step.__name__, {"error": type(e).__name__, "message": str(e)[:200]})
    out = pathlib.Path("out/eval")
    out.mkdir(parents=True, exist_ok=True)
    (out / "smoke_providers.json").write_text(json.dumps(RESULTS, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
