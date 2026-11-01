"""Promptfoo python provider: the repo's current regex extractor (app/agents/extraction.py) as a no-LLM baseline.
config.mode = "extract" (default) -> JSON of extracted fields mapped to gold field names.
config.mode = "detect" -> keyword baseline: scam if >= config.min_hits suspicious keywords (default 2).
Repo path from env SCAMBAIT_REPO (default /workspace/scambait)."""
import contextlib, importlib.util, io, json, os, time
# Load extraction.py by file path: importing the app.agents package pulls in heavy deps (sklearn etc.).
_spec = importlib.util.spec_from_file_location("sb_extraction", os.path.join(
    os.environ.get("SCAMBAIT_REPO", "/workspace/scambait"), "app", "agents", "extraction.py"))
_mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)
extract_intelligence = _mod.extract_intelligence
_ORIG_APK = _mod.extract_apk_links
# BUG in repo extract_apk_links (commit f419b59): the alternation (?:[a-zA-Z]|[0-9]|[$-_@.&+]|...)+ overlaps
# ([$-_] already contains letters/digits), so a URL that does NOT end in .apk backtracks exponentially
# (~4x per 2 extra chars; 20-char host = 1.5 s, the 167-char gold row sb-f9df47e303 took 281 s).
# config.safe_apk: true swaps in a linear pattern so evals don't hang; false measures the repo as-is.
import re as _re
def _safe_apk(text):
    return list(set(_re.findall(r'https?://[^\s<>"\']+?\.apk\b', text, _re.IGNORECASE)))[:5]

MAP = {"upiIds": "upiIds", "phoneNumbers": "phoneNumbers", "bankAccounts": "bankAccounts", "ifscCodes": "ifscCodes",
       "phishingLinks": "phishingLinks", "apkLinks": "apkLinks", "cryptoWallets": "cryptoWallets",
       "socialHandles": "socialHandles", "emails": "emails"}

def call_api(prompt, options, context):
    cfg = (options or {}).get("config", {}) or {}
    v = context.get("vars", {})
    text = v.get("text") or v.get("message") or prompt
    _mod.extract_apk_links = _safe_apk if cfg.get("safe_apk", True) else _ORIG_APK
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):          # extractor prints; keep promptfoo output clean
        intel = extract_intelligence([{"text": text}])
    ms = (time.perf_counter() - t0) * 1000
    if cfg.get("mode", "extract") == "detect":
        hits = intel.get("suspiciousKeywords", [])
        is_scam = len(hits) >= int(cfg.get("min_hits", 2))
        out = {"is_scam": is_scam, "p_scam": min(1.0, len(hits) / 4), "hits": hits}
    else:
        out = {MAP[k]: sorted(vals) for k, vals in intel.items() if k in MAP and vals}
    return {"output": json.dumps(out), "metadata": {"latency_ms": round(ms, 3)}}
