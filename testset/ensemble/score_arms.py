"""Score every row of the frozen detection splits with each detector arm and save per-row scores.

Arms (all on the SAME rows, same prompt, same split):
  regex      - old repo keyword list (providers/regex_only.py, keyless; needs SCAMBAIT_REPO pointing at the old repo)
  cerebras   - Cerebras CEREBRAS_DETECT_MODEL (default gpt-oss-120b; or qwen-3.8-27b with
               CEREBRAS_REASONING_EFFORT=none), strict JSON verdict (CEREBRAS_API_KEY).
               Paced to --cerebras-rpm (default 5 = Free Trial); 429s retry on the same model.
  decisions  - OpenAI Decisions API gpt-6-luna, typed probabilities (OPENAI_API_KEY)

Output: one JSONL per split, one line per row:
  {"id", "split", "gold", "scam_type", "lookalike", "language",
   "p_regex", "p_cerebras", "cerebras_type", "p_decisions", "decisions_type",
   "lat_regex_ms", "lat_cerebras_ms", "lat_decisions_ms", "cerebras_tps", "err_cerebras", "err_decisions"}

Usage (keys only in the environment, never in files):
  python3 ensemble/score_arms.py --split dev  --arms regex,cerebras,decisions --out out/scores_dev.jsonl
  python3 ensemble/score_arms.py --split test --arms regex,cerebras,decisions --out out/scores_test.jsonl
Then: python3 ensemble/tune_ensemble.py out/scores_dev.jsonl out/scores_test.jsonl --md

Request shapes follow the docs read on 1 Nov 2026:
  Cerebras Chat Completions https://inference-docs.cerebras.ai/api-reference/chat-completions (time_info, usage,
  strict json_schema, reasoning_effort low|medium|high for gpt-oss-120b, no "none").
  Decisions https://developers.openai.com/api/docs/guides/decisions (answers[] with name/probability).
Confirm both against the docs again before a scored run; a changed field fails loudly, it never scores SAFE.
"""
import argparse, concurrent.futures as cf, json, os, sys, threading, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

SPLITS = {"dev": "detection_real_dev.jsonl", "test": "detection_real_test.jsonl"}
CEREBRAS_URL = os.environ.get("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1") + "/chat/completions"
CEREBRAS_MODEL = os.environ.get("CEREBRAS_DETECT_MODEL", "gpt-oss-120b")
DECISIONS_URL = "https://api.openai.com/v1/decisions"
DECISIONS_MODEL = os.environ.get("DECISIONS_MODEL", "gpt-6-luna")

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["is_scam", "p_scam", "scam_type", "risk"],
    "properties": {
        "is_scam": {"type": "boolean"},
        "p_scam": {"type": "number", "minimum": 0, "maximum": 1},
        "scam_type": {"type": "string"},
        "risk": {"type": "string", "enum": ["none", "low", "medium", "high", "critical"]},
    },
}


def load_rows(split):
    with open(os.path.join(ROOT, SPLITS[split]), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class Pacer:
    """Client-side pacing so a scored run stays under the Cerebras per-model RPM (Free Trial: 5 RPM per model,
    https://inference-docs.cerebras.ai/support/rate-limits). rpm <= 0 disables pacing."""
    def __init__(self, rpm):
        self.gap, self.lock, self.next = (60.0 / rpm if rpm > 0 else 0.0), threading.Lock(), 0.0

    def wait(self):
        if not self.gap:
            return
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        time.sleep(max(0.0, t - now))


CEREBRAS_PACER = Pacer(float(os.environ.get("CEREBRAS_RPM", "5")))   # set by --cerebras-rpm in main()


def post_cerebras(body, retries=3):
    """Paced POST; on 429 retry on the SAME model, honouring Retry-After if the server sends it (else 15 s)."""
    for attempt in range(retries + 1):
        CEREBRAS_PACER.wait()
        try:
            return post(CEREBRAS_URL, body, {"Authorization": "Bearer " + os.environ["CEREBRAS_API_KEY"]})
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries:
                raise
            ra = e.headers.get("retry-after") if e.headers else None
            try:
                delay = float(ra) if ra else 15.0
            except ValueError:
                delay = 15.0
            time.sleep(min(delay, 60.0))


def post(url, body, headers, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.load(r)
    return out, (time.perf_counter() - t0) * 1000


def arm_regex(row):
    from providers import regex_only  # imported lazily: needs SCAMBAIT_REPO
    v = row["vars"]
    res = regex_only.call_api(v["message"], {"config": {"mode": "detect", "min_hits": 2}}, {"vars": v})
    out = json.loads(res["output"])
    return {"p_regex": float(out["p_scam"]), "lat_regex_ms": res["metadata"]["latency_ms"]}


PROMPT = open(os.path.join(ROOT, "prompts", "detect.txt"), encoding="utf-8").read()


def arm_cerebras(row):
    v = row["vars"]
    prompt = PROMPT.replace("{{channel}}", v.get("channel", "")).replace("{{message}}", v["message"])
    body = {
        "model": CEREBRAS_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": SCHEMA}},
        "reasoning_effort": os.environ.get("CEREBRAS_REASONING_EFFORT", "low"),
        "temperature": 0, "seed": 20261101,
        "max_completion_tokens": int(os.environ.get("CEREBRAS_MAX_TOKENS", "1024")),  # reasoning tokens count here
    }
    try:
        out, ms = post_cerebras(body)
        verdict = json.loads(out["choices"][0]["message"]["content"])
        ti, usage = out.get("time_info") or {}, out.get("usage") or {}
        tps = None
        if ti.get("completion_time") and usage.get("completion_tokens"):
            tps = round(usage["completion_tokens"] / ti["completion_time"], 1)
        p = float(verdict["p_scam"])
        if verdict["is_scam"] and p < 0.5:      # keep the boolean and the number consistent
            p = 0.5
        return {"p_cerebras": p, "cerebras_type": verdict.get("scam_type"), "lat_cerebras_ms": round(ms, 1),
                "cerebras_server_ms": round(1000 * ti["total_time"], 1) if ti.get("total_time") else None,
                "cerebras_tps": tps, "err_cerebras": None}
    except Exception as e:  # recorded, never turned into "safe"
        return {"p_cerebras": None, "err_cerebras": f"{type(e).__name__}: {str(e)[:200]}"}


def arm_decisions(row):
    from providers.decisions_provider import QUESTIONS
    body = {"model": DECISIONS_MODEL, "input": row["vars"]["message"], "questions": QUESTIONS}
    try:
        out, ms = post(DECISIONS_URL, body, {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
        ans = {a.get("name"): a for a in out.get("answers", [])}
        a = ans.get("is_scam")
        if a is None or a.get("type") == "refusal" or "probability" not in a:
            raise ValueError("no is_scam probability in answers")
        st = ans.get("scam_type") or {}
        return {"p_decisions": float(a["probability"]), "decisions_type": st.get("choice"),
                "lat_decisions_ms": round(ms, 1), "err_decisions": None}
    except Exception as e:
        return {"p_decisions": None, "err_decisions": f"{type(e).__name__}: {str(e)[:200]}"}


ARMS = {"regex": arm_regex, "cerebras": arm_cerebras, "decisions": arm_decisions}


def score_row(row, split, arms):
    m, v = row.get("metadata", {}), row["vars"]
    rec = {"id": m.get("id"), "split": split, "gold": v.get("expected") == "scam",
           "scam_type": m.get("scam_type"), "lookalike": bool(m.get("lookalike")), "language": m.get("language")}
    for a in arms:
        rec.update(ARMS[a](row))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--arms", default="regex,cerebras,decisions")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4, help="keep low on the Cerebras Free Trial (5 RPM)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cerebras-rpm", type=float, default=float(os.environ.get("CEREBRAS_RPM", "5")),
                    help="max Cerebras requests/min (Free Trial 5; Developer gpt-oss-120b 1000, qwen-3.8-27b 300; 0 = no pacing)")
    a = ap.parse_args()
    global CEREBRAS_PACER
    CEREBRAS_PACER = Pacer(a.cerebras_rpm)
    arms = [x for x in a.arms.split(",") if x]
    rows = load_rows(a.split)[: a.limit or None]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with cf.ThreadPoolExecutor(a.workers) as ex, open(a.out, "w", encoding="utf-8") as f:
        for rec in ex.map(lambda r: score_row(r, a.split, arms), rows):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {a.out}")


if __name__ == "__main__":
    main()
