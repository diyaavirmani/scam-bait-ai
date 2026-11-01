"""Promptfoo python assert for extraction: per-field micro P/R/F1 against test 'gold' (vars.gold or metadata.gold).
List fields compared as normalised sets; scalar fields (investmentStage, promisedReturn) as exact match.
Score = micro-F1 over all gold+predicted values; pass when F1 >= SB_F1_PASS (default 0.8)."""
import json, os, re

SCALAR = {"investmentStage", "promisedReturn"}
def norm(v):
    if isinstance(v, dict): return json.dumps({k: norm(x) for k, x in sorted(v.items())}, sort_keys=True)
    s = str(v).strip().lower()
    s = re.sub(r"^(https?://)?(www\.)?", "", s).rstrip("/")
    digits = re.sub(r"\D", "", s)
    if re.fullmatch(r"[+\d\s\-()]{10,}", str(v).strip()): s = digits[-10:]   # phone: compare last 10 digits
    return s

def as_set(v):
    if v is None: return set()
    if isinstance(v, list): return {norm(x) for x in v}
    return {norm(v)}

def get_assert(output, context):
    gold = context["vars"].get("gold") or (context.get("test", {}).get("metadata", {}) or {}).get("gold") or {}
    if isinstance(gold, str): gold = json.loads(gold)
    try:
        pred = json.loads(re.search(r"\{.*\}", output, re.S).group(0)) if isinstance(output, str) else output
    except Exception:
        return {"pass": False, "score": 0, "reason": "output is not JSON"}
    tp = fp = fn = 0; per = {}
    keys = set(gold) | {k for k in pred if pred.get(k) not in (None, [], "", {})}
    for k in keys:
        g, p = as_set(gold.get(k)), as_set(pred.get(k))
        t = len(g & p); tp += t; fp += len(p - g); fn += len(g - p)
        per[k] = {"tp": t, "fp": len(p - g), "fn": len(g - p)}
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    exact = int(fp == 0 and fn == 0)
    return {"pass": f1 >= float(os.environ.get("SB_F1_PASS", "0.8")), "score": f1,
            "reason": f"P={prec:.2f} R={rec:.2f} F1={f1:.2f} per_field={per}",
            "named_scores": {"field_tp": tp, "field_fp": fp, "field_fn": fn, "exact_match": exact}}
