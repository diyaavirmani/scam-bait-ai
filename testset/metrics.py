"""Summarise a promptfoo detection run: P/R/F1, false-positive rate on legit look-alikes, message-only slice,
non-English slice, per-type recall, p50/p95 latency, parse failures. Usage:
  python3 metrics.py out/real_test.json [--threshold 0.5] [--md]
Latency uses the provider-measured metadata.latency_ms when present (excludes promptfoo/python overhead),
otherwise promptfoo latencyMs. With --repeat N runs, every repeat is a latency sample."""
import json, sys, os, statistics
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "asserts"))
from _parse import verdict

def pct(xs, q):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs) - 1) * q; f = int(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

def prf(rows):
    tp = sum(1 for g, p in rows if g and p); fp = sum(1 for g, p in rows if not g and p)
    fn = sum(1 for g, p in rows if g and not p); tn = sum(1 for g, p in rows if not g and not p)
    P = tp / (tp + fp) if tp + fp else 0.0; R = tp / (tp + fn) if tp + fn else 0.0
    F = 2 * P * R / (P + R) if P + R else 0.0
    return dict(n=len(rows), TP=tp, FP=fp, FN=fn, TN=tn, P=round(P, 3), R=round(R, 3), F1=round(F, 3))

def main(path, thr=0.5, md=False):
    res = json.load(open(path))["results"]["results"]
    by = defaultdict(lambda: dict(rows=[], mo=[], nonen=[], look=[], lat=[], types=defaultdict(list), parse_fail=0))
    for r in res:
        prov = r["provider"].get("label") or r["provider"]["id"]; b = by[prov]
        resp = r.get("response") or {}
        meta = r["testCase"].get("metadata", {}) or {}
        gold = r["vars"].get("expected") == "scam"
        pred, _ = verdict(resp.get("output", ""), thr)
        lat = (resp.get("metadata") or {}).get("latency_ms", r.get("latencyMs"))
        if lat is not None: b["lat"].append(float(lat))
        if pred is None: b["parse_fail"] += 1; pred = False      # unparseable counts as "not flagged"
        b["rows"].append((gold, pred))
        if meta.get("message_only"): b["mo"].append((gold, pred))
        if meta.get("language", "en") != "en": b["nonen"].append((gold, pred))
        if meta.get("lookalike"): b["look"].append(pred)
        if gold: b["types"][meta.get("scam_type")].append(pred)
    out = {}
    for prov, b in by.items():
        out[prov] = dict(overall=prf(b["rows"]), message_only=prf(b["mo"]), non_english=prf(b["nonen"]),
            lookalike_fp=f"{sum(b['look'])}/{len(b['look'])}",
            latency_ms=dict(p50=round(pct(b["lat"], .5), 1), p95=round(pct(b["lat"], .95), 1), n=len(b["lat"])),
            parse_fail=b["parse_fail"],
            recall_by_type={t: f"{sum(v)}/{len(v)}" for t, v in sorted(b["types"].items())})
    if md:
        print("| arm | P | R | F1 | msg-only F1 | non-en F1 | look-alike FP | p50 ms | p95 ms | parse fail |\n|---|---|---|---|---|---|---|---|---|---|")
        for p, o in out.items():
            print(f"| {p} | {o['overall']['P']} | {o['overall']['R']} | {o['overall']['F1']} | {o['message_only']['F1']} | {o['non_english']['F1']} | {o['lookalike_fp']} | {o['latency_ms']['p50']} | {o['latency_ms']['p95']} | {o['parse_fail']} |")
    else:
        print(json.dumps(out, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    a = sys.argv[1:]; thr = float(a[a.index("--threshold") + 1]) if "--threshold" in a else 0.5
    main(a[0], thr, "--md" in a)
