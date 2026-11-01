"""Promptfoo python assert: compare predicted scam/legit with vars.expected; emit TP/FP/FN/TN named scores
plus FP_lookalike (false alarm on a legit look-alike). Threshold via env SB_THRESHOLD (default 0.5)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from _parse import verdict

def get_assert(output, context):
    exp = context["vars"].get("expected", context["vars"].get("assert_label"))
    pred, p = verdict(output, float(os.environ.get("SB_THRESHOLD", "0.5")))
    if pred is None:
        return {"pass": False, "score": 0, "reason": "unparseable output", "named_scores": {"PARSE_FAIL": 1}}
    gold = exp == "scam"
    cell = ("TP" if pred else "FN") if gold else ("FP" if pred else "TN")
    ns = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}; ns[cell] = 1
    if cell == "FP": ns["FP_lookalike"] = 1
    return {"pass": cell in ("TP", "TN"), "score": 1 if cell in ("TP", "TN") else 0,
            "reason": f"{cell} expected={exp} pred={'scam' if pred else 'legit'} p={p}", "named_scores": ns}
