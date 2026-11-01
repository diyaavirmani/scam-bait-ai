"""Offline (no network, no keys) evaluation arms: old keyword baseline, new regex prefilter, old vs new regex
extraction on the 28 gold rows, and local step latencies. Writes raw outputs under out/eval/ and out/eval_summary.json.

  .venv/bin/python -B scripts/eval_offline.py
The prefilter threshold is chosen on the dev split only; the test split is scored once.
"""
import asyncio
import contextlib
import importlib.util
import io
import json
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True  # never write .pyc files into the read-only old repo
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.detection.prefilter import prefilter  # noqa: E402
from app.events import Bus  # noqa: E402
from app.extraction import extract, validate  # noqa: E402
from app.models import Event  # noqa: E402
from app.store import Store  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
OLD_REPO = pathlib.Path.home() / "Projects/scambait/scambait-old"
OUT = ROOT / "out/eval"


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def old_extraction_module():
    spec = importlib.util.spec_from_file_location("old_extraction", OLD_REPO / "app/agents/extraction.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # The old extract_apk_links backtracks exponentially (AUDIT X-01); swap in a linear pattern so the baseline
    # finishes, exactly as the kit's regex_only.py provider did (safe_apk: true).
    mod.extract_apk_links = lambda t: list(set(re.findall(r'https?://[^\s<>"\']+?\.apk\b', t, re.I)))[:5]
    return mod


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))] if xs else None


def metrics(rows, pred_key):
    tp = sum(1 for r in rows if r["y"] and r[pred_key])
    fp = sum(1 for r in rows if not r["y"] and r[pred_key])
    fn = sum(1 for r in rows if r["y"] and not r[pred_key])
    tn = sum(1 for r in rows if not r["y"] and not r[pred_key])
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(p, 3), "recall": round(rc, 3),
            "f1": round(f1, 3), "accuracy": round((tp + tn) / len(rows), 3) if rows else 0.0}


def lang_group(lang):
    return lang if lang in ("en", "hinglish", "hi") else "mixed"


# ---------------- detection ----------------
def detection():
    old = old_extraction_module()
    dev = load(ROOT / "testset/detection_real_dev.jsonl")
    test = load(ROOT / "testset/detection_real_test.jsonl")

    def scores(rows):
        out = []
        for r in rows:
            text = r["vars"]["message"]
            t0 = time.perf_counter()
            with contextlib.redirect_stdout(io.StringIO()):
                hits = old.extract_keywords(text)
            old_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            pf = prefilter(text)
            new_ms = (time.perf_counter() - t0) * 1000
            out.append({"id": r["metadata"].get("id"), "y": r["vars"]["expected"] == "scam",
                        "lang": lang_group(r["metadata"].get("language")), "type": r["metadata"].get("scam_type"),
                        "old_hits": len(hits), "old_ms": old_ms, "score": pf["score"], "hits": pf["hits"],
                        "new_ms": new_ms})
        return out

    dev_s, test_s = scores(dev), scores(test)
    # choose the prefilter threshold on dev only (max F1, ties -> higher threshold)
    best = (-1.0, None)
    for th in sorted({s["score"] for s in dev_s} | {0.05}):
        for r in dev_s:
            r["pf"] = r["score"] >= th and r["score"] > 0
        f1 = metrics(dev_s, "pf")["f1"]
        if f1 > best[0] or (f1 == best[0] and best[1] is not None and th > best[1]):
            best = (f1, th)
    th = best[1]
    for r in test_s:
        r["old"] = r["old_hits"] >= 2  # kit baseline: min_hits 2
        r["pf"] = r["score"] >= th and r["score"] > 0
    arms = {}
    for key, name, ms_key in (("old", "a. Old keyword baseline (scambait-old extract_keywords, min_hits 2)", "old_ms"),
                              ("pf", f"b. New regex prefilter (score >= {th}, threshold from dev)", "new_ms")):
        m = metrics(test_s, key)
        m.update({"arm": name, "lookalike_fp": f"{m['fp']} of 43", "errors_unknown": 0,
                  "p50_ms": round(pct([r[ms_key] for r in test_s], 0.5), 3),
                  "p95_ms": round(pct([r[ms_key] for r in test_s], 0.95), 3), "cost_per_1k_usd": 0.0})
        m["per_language"] = {}
        for lg in ("en", "hinglish", "hi", "mixed"):
            sub = [r for r in test_s if r["lang"] == lg]
            if sub:
                mm = metrics(sub, key)
                m["per_language"][lg] = {"rows": len(sub), "scam": sum(r["y"] for r in sub), "tp": mm["tp"],
                                         "fp": mm["fp"], "fn": mm["fn"], "tn": mm["tn"], "f1": mm["f1"]}
        m["per_type_recall"] = {}
        for t in sorted({r["type"] for r in test_s if r["y"]}):
            sub = [r for r in test_s if r["y"] and r["type"] == t]
            m["per_type_recall"][t] = f"{sum(1 for r in sub if r[key])} of {len(sub)}"
        arms[key] = m
    # 10 worst misses of the new prefilter: scams with the lowest score, legit with the highest
    misses = [r for r in test_s if r["y"] != r["pf"]]
    misses.sort(key=lambda r: (r["score"] if r["y"] else 1 - r["score"]))
    worst = [{"id": r["id"], "gold": "scam" if r["y"] else "legit", "type": r["type"], "lang": r["lang"],
              "old_baseline": "scam" if r["old"] else "not scam", "prefilter": "scam" if r["pf"] else "not scam",
              "prefilter_score": r["score"]} for r in misses[:10]]
    with open(OUT / "detection_offline_test.jsonl", "w") as fh:
        for r in test_s:
            fh.write(json.dumps({k: v for k, v in r.items()}) + "\n")
    return {"threshold_from_dev": th, "dev_f1_at_threshold": best[0], "arms": arms, "worst_misses": worst,
            "rows": len(test_s)}


# ---------------- extraction ----------------
FIELDS = ["upi", "phone", "bank_account", "ifsc", "url", "apk", "name"]


def norm(kind, v):
    v = str(v).strip()
    if kind == "phone":
        d = re.sub(r"\D", "", v)
        return d[-10:]
    if kind == "bank_account":
        return re.sub(r"\D", "", v)
    if kind == "ifsc":
        return v.upper()
    if kind in ("url", "apk"):
        v = v.lower().rstrip(".,;)/")
        v = re.sub(r"^https?://", "", v)
        return re.sub(r"^www\.", "", v)
    return re.sub(r"\s+", " ", v.lower())


def gold_sets(g):
    links = g.get("phishingLinks", []) + g.get("groupLinks", []) + g.get("appLinks", []) + g.get("apkLinks", [])
    raw = {"upi": g.get("upiIds", []), "phone": g.get("phoneNumbers", []), "bank_account": g.get("bankAccounts", []),
           "ifsc": g.get("ifscCodes", []), "url": links, "apk": g.get("apkLinks", []),
           "name": g.get("beneficiaryNames", [])}
    return {k: {norm(k, v) for v in vals} for k, vals in raw.items()}


def extraction():
    old = old_extraction_module()
    gold = load(ROOT / "testset/extraction_gold.jsonl")
    res = {}
    for arm in ("old", "new"):
        per = {f: {"tp": 0, "fp": 0, "fn": 0} for f in FIELDS}
        exact, fps, ms = 0, [], []
        for row in gold:
            g = gold_sets(row["gold"])
            t0 = time.perf_counter()
            if arm == "new":
                pred = {f: set() for f in FIELDS}
                for c in validate(extract(row["text"])):
                    if c.kind in pred:
                        pred[c.kind].add(norm(c.kind, c.value))
            else:
                with contextlib.redirect_stdout(io.StringIO()):
                    intel = old.extract_intelligence([{"text": row["text"]}])
                pred = {"upi": intel["upiIds"], "phone": intel["phoneNumbers"], "bank_account": intel["bankAccounts"],
                        "ifsc": intel["ifscCodes"], "url": intel["phishingLinks"] + intel["apkLinks"],
                        "apk": intel["apkLinks"], "name": []}
                pred = {k: {norm(k, v) for v in vals} for k, vals in pred.items()}
            ms.append((time.perf_counter() - t0) * 1000)
            row_ok = True
            for f in FIELDS:
                tp = len(pred[f] & g[f])
                per[f]["tp"] += tp
                per[f]["fp"] += len(pred[f] - g[f])
                per[f]["fn"] += len(g[f] - pred[f])
                for v in sorted(pred[f] - g[f]):
                    fps.append({"id": row["id"], "field": f, "value": v})
                if pred[f] != g[f]:
                    row_ok = False
            exact += row_ok
        tot = {k: sum(per[f][k] for f in FIELDS) for k in ("tp", "fp", "fn")}
        for f in FIELDS + ["ALL"]:
            d = tot if f == "ALL" else per[f]
            d["precision"] = round(d["tp"] / (d["tp"] + d["fp"]), 3) if d["tp"] + d["fp"] else None
            d["recall"] = round(d["tp"] / (d["tp"] + d["fn"]), 3) if d["tp"] + d["fn"] else None
        res[arm] = {"per_field": per, "all": tot, "exact_rows": f"{exact} of {len(gold)}", "false_positives": fps,
                    "p50_ms": round(pct(ms, 0.5), 3), "p95_ms": round(pct(ms, 0.95), 3)}
    return res


# ---------------- local step latencies ----------------
async def local_steps():
    text = "Pay to UPI fakeinvest.demo@okaxis or call +91 90000 00001, account 000123456789 IFSC ABCD0001234"
    out = {}
    for name, fn in (("regex prefilter", lambda: prefilter(text)), ("extraction + validators",
                                                                     lambda: validate(extract(text)))):
        xs = []
        for _ in range(200):
            t0 = time.perf_counter()
            fn()
            xs.append((time.perf_counter() - t0) * 1000)
        out[name] = (round(pct(xs, 0.5), 3), round(pct(xs, 0.95), 3))
    with tempfile.TemporaryDirectory() as d:
        store = Store(str(pathlib.Path(d) / "lat.db"))
        await store.init()
        case = await store.new_case("telegram", "tg:lat")
        xs = []
        for i in range(200):
            t0 = time.perf_counter()
            await store.add_message(case["id"], "scammer", f"{text} {i}")
            xs.append((time.perf_counter() - t0) * 1000)
        out["DB write (add_message, WAL)"] = (round(pct(xs, 0.5), 3), round(pct(xs, 0.95), 3))
        bus = Bus(store)
        q = bus.subscribe()
        xs = []
        for i in range(200):
            t0 = time.perf_counter()
            await bus.emit(Event(case_id=case["id"], channel="telegram", type="message.received", data={"i": i}))
            await q.get()
            xs.append((time.perf_counter() - t0) * 1000)
        out["event store + SSE fan-out (emit to subscriber queue)"] = (round(pct(xs, 0.5), 3), round(pct(xs, 0.95), 3))
        await store.close()
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(IST)
    summary = {"run": {"date": f"{started:%Y-%m-%d}", "start_ist": f"{started:%H:%M:%S}",
                       "git_commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                                    text=True, cwd=ROOT).stdout.strip(),
                       "network": "none (offline arms only)"},
               "detection": detection(), "extraction": extraction(), "local_steps_ms_p50_p95": asyncio.run(local_steps())}
    summary["run"]["end_ist"] = f"{datetime.now(IST):%H:%M:%S}"
    (ROOT / "out/eval_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=1)[:6000])


if __name__ == "__main__":
    main()
