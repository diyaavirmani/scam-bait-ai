"""Shared output parsing for detection arms. Accepts Cerebras/Responses JSON ({"is_scam":..,"p_scam":..}),
the Decisions provider output (answers keyed by question name; predicate may carry a probability), or mock output."""
import json, re

def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj: return obj[key]
        for v in obj.values():
            r = _find(v, key)
            if r is not None: return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, key)
            if r is not None: return r
    return None

def verdict(output, threshold=0.5):
    """Return (is_scam: bool|None, p_scam: float|None)."""
    if isinstance(output, str):
        m = re.search(r"\{.*\}", output, re.S)
        try: output = json.loads(m.group(0)) if m else {}
        except Exception: return None, None
    if isinstance(output, dict) and isinstance(output.get("answers"), list):   # Decisions API: answers[{name, probability}]
        a = next((x for x in output["answers"] if x.get("name") == "is_scam"), None)   # shape per decisions guide, 1 Nov 2026
        if a is None or a.get("type") == "refusal" or a.get("probability") is None: return None, None
        p = float(a["probability"]); return p >= threshold, p
    v = _find(output, "is_scam")
    p = _find(output, "p_scam")
    if isinstance(v, dict):                       # Decisions-style {"value": true, "probability": 0.93} (field names unverified)
        p = v.get("probability", v.get("p", p)); v = v.get("value", v.get("answer"))
    if isinstance(v, str): v = v.strip().lower() in ("true", "yes", "scam")
    if p is not None:
        try: p = float(p)
        except Exception: p = None
    if v is None and p is not None: v = p >= threshold
    if p is not None and v is not None and threshold != 0.5: v = p >= threshold
    return v, p
