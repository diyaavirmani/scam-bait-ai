"""Deterministic offline mock for dry-running the promptfoo wiring with NO API keys.
It is NOT a model: verdicts come from a crude keyword score and latency is simulated from a fixed
distribution, so the numbers it produces only prove the pipeline (parsing, asserts, metrics) works.
config.style: "decisions" (nested answers with probability) or "json" (Cerebras-style flat JSON).
config.latency_ms: [median, p95] used to simulate per-call latency (sleep)."""
import hashlib, json, math, random, re, time

CUES = r"(kyc|block|suspend|disconnect|redeem|lottery|kbc|won|prize|customer care|call now|press [19]|click|apk|part[\s-]?time|daily salary|telegram|whatsapp|update your pan|expire|parcel|drugs|arrest|cbi|investor)"
CALM = r"(thank you for contacting|हम से संपर्क|beware|alert|fraud|scam|fake|received|got this|is this genuine)"

def call_api(prompt, options, context):
    cfg = (options or {}).get("config", {}) or {}
    msg = context.get("vars", {}).get("message", prompt)
    lo = msg.lower()
    z = 1.2 * len(re.findall(CUES, lo)) - 1.5 * len(re.findall(CALM, lo)) - 0.8
    p = 1 / (1 + math.exp(-z))
    seed = int(hashlib.sha1((cfg.get("style", "") + msg).encode()).hexdigest()[:8], 16)
    med, p95 = cfg.get("latency_ms", [300, 700])
    lat = med * math.exp(random.Random(seed).gauss(0, 1) * math.log(p95 / med) / 1.645)
    time.sleep(lat / 1000)
    if cfg.get("style") == "decisions":
        out = {"mock": True, "answers": {"is_scam": {"value": p >= 0.5, "probability": round(p, 3)},
                                         "risk": {"level": "High" if p > 0.7 else "Low"}}}
    else:
        out = {"mock": True, "is_scam": p >= 0.5, "p_scam": round(p, 3), "scam_type": "other" if p >= 0.5 else "not_a_scam", "risk": "high" if p > 0.7 else "low"}
    return {"output": json.dumps(out), "metadata": {"latency_ms": round(lat, 1)}}
