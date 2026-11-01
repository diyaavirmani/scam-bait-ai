"""Tune detection thresholds and ensemble rules on the DEV split, report once on the held-out TEST split.

Input: per-row score files written by ensemble/score_arms.py (dev and test).
Detectors compared (same rows):
  regex_only       p_regex >= t
  cerebras_only    p_cerebras >= t
  decisions_only   p_decisions >= t
  ens_weighted     w*p_decisions + (1-w)*p_cerebras >= t           (both run in parallel; latency = max of the two)
  ens_escalate     Cerebras decides when confident (p<=lo or p>=hi); borderline rows go to Decisions (p_d >= t)
                   (Decisions as calibrator on borderline; both still run in parallel, latency = max of the two)
  ens_stacked      logistic regression on [logit p_cerebras, logit p_decisions, p_regex], fitted on dev, then t
                   (both run in parallel)
  ens_or / ens_and either / both arms above their own tuned single-arm thresholds (reference rules)

Selection: every knob is chosen on DEV only (max F1; ties -> lower look-alike FPR). The overall winner is the
detector with the best DEV F1; if two are within 0.01 F1, the lower DEV p50 latency wins. TEST is then reported
for every detector, once, with a 95% bootstrap interval for F1. Never re-tune after looking at TEST.

A missing score (API error) counts as NOT flagged here and is reported in the "err" column; the app itself must
never treat an error as safe.

Usage:
  python3 ensemble/tune_ensemble.py out/scores_dev.jsonl out/scores_test.jsonl --md [--json out/ensemble_report.json]
  python3 ensemble/tune_ensemble.py --selftest      # wiring check on random numbers; NOT a result
"""
import json, math, random, sys, statistics
from collections import defaultdict

GRID = [i / 100 for i in range(5, 96, 1)]
WGRID = [i / 10 for i in range(0, 11)]


def load(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    f = int(k); c = min(f + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 1)


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def stats(rows, preds):
    tp = sum(1 for r, y in zip(rows, preds) if r["gold"] and y)
    fp = sum(1 for r, y in zip(rows, preds) if not r["gold"] and y)
    fn = sum(1 for r, y in zip(rows, preds) if r["gold"] and not y)
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    F = 2 * P * R / (P + R) if P + R else 0.0
    look = [y for r, y in zip(rows, preds) if r.get("lookalike")]
    fpr = sum(look) / len(look) if look else 0.0
    return dict(P=P, R=R, F1=F, TP=tp, FP=fp, FN=fn, look_fp=sum(look), look_n=len(look), look_fpr=fpr)


def g(r, k):
    v = r.get(k)
    return None if v is None else float(v)


# ---- detectors: each returns (predict(row)->bool, latency(row)->ms|None) for a given parameter dict ----
def single(key, lat_key):
    def make(t):
        return (lambda r: g(r, key) is not None and g(r, key) >= t), (lambda r: r.get(lat_key))
    return make


def weighted(w, t):
    def p(r):
        c, d = g(r, "p_cerebras"), g(r, "p_decisions")
        if c is None and d is None:
            return False
        if c is None: return d >= t
        if d is None: return c >= t
        return w * d + (1 - w) * c >= t
    return p, lambda r: max_lat(r)


def max_lat(r):
    xs = [x for x in (r.get("lat_cerebras_ms"), r.get("lat_decisions_ms")) if x is not None]
    return max(xs) if xs else None


def escalate(lo, hi, t):
    def p(r):
        c, d = g(r, "p_cerebras"), g(r, "p_decisions")
        if c is not None and c >= hi: return True
        if c is not None and c <= lo: return False
        return d is not None and d >= t if d is not None else (c is not None and c >= 0.5)
    return p, max_lat   # both arms always run in parallel; Decisions only decides borderline rows


def fit_stack(rows, iters=3000, lr=0.1, l2=1e-3):
    X = [[logit(g(r, "p_cerebras") if g(r, "p_cerebras") is not None else 0.5),
          logit(g(r, "p_decisions") if g(r, "p_decisions") is not None else 0.5),
          g(r, "p_regex") or 0.0, 1.0] for r in rows]
    y = [1.0 if r["gold"] else 0.0 for r in rows]
    w = [0.0] * 4
    for _ in range(iters):
        grad = [0.0] * 4
        for xi, yi in zip(X, y):
            z = sum(a * b for a, b in zip(w, xi)); p = 1 / (1 + math.exp(-max(min(z, 30), -30)))
            for j in range(4): grad[j] += (p - yi) * xi[j]
        w = [wj - lr * (gj / len(X) + l2 * wj) for wj, gj in zip(w, grad)]
    return w


def stacked(w, t):
    def score(r):
        x = [logit(g(r, "p_cerebras") if g(r, "p_cerebras") is not None else 0.5),
             logit(g(r, "p_decisions") if g(r, "p_decisions") is not None else 0.5), g(r, "p_regex") or 0.0, 1.0]
        z = sum(a * b for a, b in zip(w, x)); return 1 / (1 + math.exp(-max(min(z, 30), -30)))
    return (lambda r: score(r) >= t), (lambda r: max_lat(r))


def best(rows, candidates):
    """candidates: list of (params, (pred, lat)). Max F1 on rows; ties -> lower look-alike FPR."""
    top = None
    for params, (pred, lat) in candidates:
        s = stats(rows, [pred(r) for r in rows])
        key = (round(s["F1"], 4), -s["look_fpr"])
        if top is None or key > top[0]:
            top = (key, params, pred, lat)
    return top[1], top[2], top[3]


def tune(dev):
    tuned = {}
    for name, key, lk in [("regex_only", "p_regex", "lat_regex_ms"), ("cerebras_only", "p_cerebras", "lat_cerebras_ms"),
                          ("decisions_only", "p_decisions", "lat_decisions_ms")]:
        if all(r.get(key) is None for r in dev):
            continue
        mk = single(key, lk)
        tuned[name] = best(dev, [({"t": t}, mk(t)) for t in GRID])
    have_c = any(r.get("p_cerebras") is not None for r in dev)
    have_d = any(r.get("p_decisions") is not None for r in dev)
    if have_c and have_d:
        tuned["ens_weighted"] = best(dev, [({"w": w, "t": t}, weighted(w, t)) for w in WGRID for t in GRID[::2]])
        cands = []
        for lo in [0.05, 0.1, 0.15, 0.2, 0.3]:
            for hi in [0.6, 0.7, 0.8, 0.85, 0.9, 0.95]:
                for t in GRID[::5]:
                    cands.append(({"lo": lo, "hi": hi, "t": t}, escalate(lo, hi, t)))
        tuned["ens_escalate"] = best(dev, cands)
        sw = fit_stack(dev)
        tuned["ens_stacked"] = best(dev, [({"coef": [round(x, 3) for x in sw], "t": t}, stacked(sw, t)) for t in GRID])
        tc = tuned["cerebras_only"][0]["t"]; td = tuned["decisions_only"][0]["t"]
        for nm, fn in [("ens_or", any), ("ens_and", all)]:
            pr = (lambda fn: lambda r: fn([g(r, "p_cerebras") is not None and g(r, "p_cerebras") >= tc,
                                           g(r, "p_decisions") is not None and g(r, "p_decisions") >= td]))(fn)
            tuned[nm] = ({"t_cerebras": tc, "t_decisions": td}, pr, max_lat)
    return tuned


def bootstrap_f1(rows, preds, n=2000, seed=20261101):
    rnd = random.Random(seed); idx = list(range(len(rows))); f = []
    for _ in range(n):
        s = [rnd.choice(idx) for _ in idx]
        f.append(stats([rows[i] for i in s], [preds[i] for i in s])["F1"])
    f.sort(); return round(f[int(0.025 * n)], 3), round(f[int(0.975 * n) - 1], 3)


def report(rows, tuned, split):
    out = {}
    for name, (params, pred, lat) in tuned.items():
        preds = [pred(r) for r in rows]
        s = stats(rows, preds)
        lats = [lat(r) for r in rows]
        by_type = defaultdict(list)
        for r, y in zip(rows, preds):
            if r["gold"]:
                by_type[r.get("scam_type")].append(y)
        errs = sum(1 for r in rows if (name != "regex_only" and (r.get("err_cerebras") or r.get("err_decisions"))))
        out[name] = dict(split=split, params=params, P=round(s["P"], 3), R=round(s["R"], 3), F1=round(s["F1"], 3),
                         TP=s["TP"], FP=s["FP"], FN=s["FN"], lookalike_fp=f'{s["look_fp"]}/{s["look_n"]}',
                         lookalike_fpr=round(s["look_fpr"], 3), p50_ms=pct(lats, .5), p95_ms=pct(lats, .95),
                         recall_by_type={t: f"{sum(v)}/{len(v)}" for t, v in sorted(by_type.items(), key=lambda kv: str(kv[0]))},
                         err_rows=errs)
        if split == "test":
            out[name]["F1_95ci"] = bootstrap_f1(rows, preds)
        if name == "ens_escalate":
            p = params
            out[name]["escalated_share"] = round(sum(1 for r in rows if g(r, "p_cerebras") is None or p["lo"] < g(r, "p_cerebras") < p["hi"]) / len(rows), 3)
    return out


def pick_winner(dev_rep):
    ranked = sorted(dev_rep.items(), key=lambda kv: (-kv[1]["F1"], kv[1]["p50_ms"] or 1e9))
    top = ranked[0]
    for name, r in ranked[1:]:
        if top[1]["F1"] - r["F1"] <= 0.01 and (r["p50_ms"] or 1e9) < (top[1]["p50_ms"] or 1e9):
            top = (name, r)
    return top[0]


def md(dev_rep, test_rep, winner):
    print(f"Winner (chosen on dev: best F1, latency breaks ties within 0.01): {winner}\n")
    print("| detector | dev F1 | test P | test R | test F1 (95% CI) | look-alike FP (test) | p50 ms | p95 ms | params |")
    print("|---|---|---|---|---|---|---|---|---|")
    for n in test_rep:
        t, d = test_rep[n], dev_rep[n]
        print(f"| {n} | {d['F1']} | {t['P']} | {t['R']} | {t['F1']} {tuple(t['F1_95ci'])} | {t['lookalike_fp']} | {t['p50_ms']} | {t['p95_ms']} | {json.dumps(t['params'])} |")
    print("\nPer-scam-type recall on test:")
    types = sorted({k for r in test_rep.values() for k in r["recall_by_type"]}, key=str)
    print("| type | " + " | ".join(test_rep) + " |\n|---|" + "---|" * len(test_rep))
    for ty in types:
        print(f"| {ty} | " + " | ".join(test_rep[n]["recall_by_type"].get(ty, "-") for n in test_rep) + " |")


def selftest():
    rnd = random.Random(1)
    def fake(n, split):
        rows = []
        for i in range(n):
            gold = rnd.random() < 0.6
            rows.append(dict(id=f"{split}{i}", gold=gold, scam_type=rnd.choice(["kyc", "investment", "job"]) if gold else "legit_lookalike",
                             lookalike=not gold, p_regex=rnd.choice([0, .25, .5, .75]),
                             p_cerebras=min(1, max(0, (0.7 if gold else 0.3) + rnd.gauss(0, .25))),
                             p_decisions=min(1, max(0, (0.75 if gold else 0.25) + rnd.gauss(0, .2))),
                             lat_regex_ms=1, lat_cerebras_ms=rnd.uniform(100, 400), lat_decisions_ms=rnd.uniform(100, 600)))
        return rows
    dev, test = fake(280, "dev"), fake(122, "test")
    tuned = tune(dev)
    d, t = report(dev, tuned, "dev"), report(test, tuned, "test")
    md(d, t, pick_winner(d))
    print("\nSELFTEST ONLY: random numbers, proves the script runs. These are NOT results.")


def main():
    a = sys.argv[1:]
    if "--selftest" in a:
        return selftest()
    dev, test = load(a[0]), load(a[1])
    assert all(r["split"] == "dev" for r in dev) and all(r["split"] == "test" for r in test), "split mix-up"
    tuned = tune(dev)
    d, t = report(dev, tuned, "dev"), report(test, tuned, "test")
    w = pick_winner(d)
    if "--json" in a:
        json.dump({"winner": w, "dev": d, "test": t}, open(a[a.index("--json") + 1], "w"), indent=1, ensure_ascii=False)
    if "--md" in a:
        md(d, t, w)
    else:
        print(json.dumps({"winner": w, "dev": d, "test": t}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
