"""Task 7: append hand-curated real scam rows (curated_v2_spec.py) to the real set WITHOUT moving existing rows.
New rows only are split 70/30 stratified by (label, scam_type) with Random(20261101) and appended to dev/test."""
import json, re, hashlib, random, collections, unicodedata, html, os, sys
SEED = 20261101
src = open("build_realset.py").read().splitlines()
exec("\n".join(src[10:44]))           # norm, mask_num, mask, clean_tail, SCRIPTS, HING, lang
exec("\n".join(src[126:136]))          # edge
from curated_v2_spec import X, NEWS, KAGGLE_IDX
XLIC = "X post, public; excerpted for internal research/eval only; X Terms apply; do not redistribute bulk text (share post IDs/URLs instead)"
PII = "victim phones/ids masked first2+last2, handles->@user, t.co->[link]"
MSG_MODS = {"quoted_scam_msg","direct_spam_post","call_script_reported","threat_reported"}
raw = {}
for l in open("raw_x/posts.jsonl"):
    p = json.loads(l); raw.setdefault(p["id"], p)
def ws(t): return re.sub(r"\s+", " ", html.unescape(t)).strip()
def mk(text, scam_type, modality, channel, url, date, lic, origin, tags, note, batch):
    t = mask(text)
    return {"id": "rx_"+hashlib.sha1(t.encode()).hexdigest()[:10], "text": t, "label": "scam", "scam_type": scam_type,
            "channel": channel, "modality": modality, "language": lang(t), "source_url": url, "date": date, "license": lic,
            "synthetic": False, "edge_tags": sorted(set(edge(t, text)) | set(tags)), "pii": PII, "origin": origin,
            "query_batch": batch, "topic": scam_type, "message_only": modality in MSG_MODS, "lookalike": False, "curation_note": note}
new, errs = [], []
for pid, ext, st, mod, ch, tags, note in X:
    p = raw.get(pid)
    if not p: errs.append(("missing", pid)); continue
    body = ws(p["text"])
    if ws(ext) not in body: errs.append(("not_substring", pid, ext[:50])); continue
    if note.startswith("FULL"):
        t = clean_tail(mask(p["text"]))
        t = re.sub(r"(\s*(@user|#\w+|\[link\]))+\s*$", "", t).strip()
    else: t = ws(ext)
    origin = "advisory_quote" if note.startswith("advisory_quote") else "x_search"
    new.append(mk(t, st, mod, ch, p["url"], p["date"], XLIC, origin, tags, note, "v2_"+p.get("q","x")[:12]))
for n in NEWS:
    new.append(mk(n["text"], n["scam_type"], n["modality"], n["channel"], n["source_url"], n["date"], n["license"], n["origin"], [], n["note"], "v2_news"))
KV = {r["idx"]: r for r in json.load(open("../ext/kaggle_verify.json"))}
CH = {"sms":"sms","whatsapp":"whatsapp","call":"voice_call","phone":"voice_call","voice":"voice_call","email":"email"}
for i, st in KAGGLE_IDX.items():
    r = KV[i]; ch = CH.get(str(r.get("platform","")).lower(), "sms")
    new.append(mk(r["text"], st, "quoted_scam_msg", ch, r["url"], "", 
        "Excerpt from the cited public page (found via Kaggle nikhilchauhan02 dataset, CC BY 4.0, verified verbatim against source, fuzzy>=0.95); internal research/eval only",
        "kaggle_verified_source", [], f"kaggle idx {i}, match score {r['score']}", "v2_kaggle"))
# dedupe vs synthetic base, existing real set, and within batch (exact norm + 60-char prefix rule)
base = set(norm(json.loads(l)["text"]) for l in open("messages.jsonl"))
old = [json.loads(l) for l in open("real_messages.jsonl")]
seen = set(norm(r["text"]) for r in old); oldids = {r["id"] for r in old}
keep, dropped = [], []
for r in new:
    k = norm(r["text"])
    if len(r["text"]) < 20 or k in base or k in seen or r["id"] in oldids or any(k[:60]==s[:60] for s in seen if len(k)>60 and len(s)>60):
        dropped.append((r["scam_type"], r["text"][:60])); continue
    seen.add(k); keep.append(r)
print("errors", errs); print("dropped", dropped); print("kept", len(keep))
if "--dry" in sys.argv: sys.exit()
with open("real_messages.jsonl","a") as f:
    for r in sorted(keep, key=lambda r: r["id"]): f.write(json.dumps(r, ensure_ascii=False)+"\n")
rng = random.Random(SEED); strata = collections.defaultdict(list)
for r in keep: strata[(r["label"], r["scam_type"])].append(r)
dev, test = [], []
for k in sorted(strata):
    g = sorted(strata[k], key=lambda r: r["id"]); rng.shuffle(g)
    n_test = round(len(g)*0.3) if len(g) > 1 else (1 if rng.random() < 0.3 else 0)
    test += g[:n_test]; dev += g[n_test:]
def to_pf(r):
    return {"vars": {"message": r["text"], "expected": r["label"], "channel": r["channel"]},
            "metadata": {k: r[k] for k in ("id","scam_type","modality","language","channel","message_only","lookalike","source_url","edge_tags","topic")}}
for name, rows in (("dev", dev), ("test", test)):
    with open(f"detection_real_{name}.jsonl","a") as f:
        for r in sorted(rows, key=lambda r: r["id"]): f.write(json.dumps(to_pf(r), ensure_ascii=False)+"\n")
json.dump({"added": len(keep), "dev_added": len(dev), "test_added": len(test), "per_type": collections.Counter(r["scam_type"] for r in keep),
           "test_per_type": collections.Counter(r["scam_type"] for r in test), "origin": collections.Counter(r["origin"] for r in keep)},
          open("append_v2_log.json","w"), indent=1)
print("dev+", len(dev), "test+", len(test))
