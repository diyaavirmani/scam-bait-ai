"""Write real_messages.jsonl + stratified 70/30 dev/test split (seed 20261101) for the real-only X set.
Input: /tmp/real_rows.json produced by build_realset.py (re-run that first)."""
import json, random, collections, hashlib
SEED = 20261101
R = json.load(open("/tmp/real_rows.json"))
MSG_MODS = {"quoted_scam_msg","direct_spam_post","call_script_reported","threat_reported","genuine_service_msg","casual_chat","promo_ad"}
for r in R:
    r["message_only"] = r["modality"] in MSG_MODS        # text is (or reads as) a single message, not a post about scams
    r["lookalike"] = r["label"] == "legit"
R.sort(key=lambda r: r["id"])
with open("real_messages.jsonl","w") as f:
    for r in R: f.write(json.dumps(r, ensure_ascii=False)+"\n")
rng = random.Random(SEED); strata = collections.defaultdict(list)
for r in R: strata[(r["label"], r["scam_type"] if r["label"]=="scam" else r["modality"])].append(r)
dev, test = [], []
for k in sorted(strata):
    g = strata[k][:]; rng.shuffle(g)
    n_test = round(len(g)*0.3) if len(g) > 1 else (1 if rng.random() < 0.3 else 0)
    test += g[:n_test]; dev += g[n_test:]
def to_pf(r):
    return {"vars": {"message": r["text"], "expected": r["label"], "channel": r["channel"]},
            "metadata": {k: r[k] for k in ("id","scam_type","modality","language","channel","message_only","lookalike","source_url","edge_tags","topic")}}
for name, rows in (("dev", dev), ("test", test)):
    with open(f"detection_real_{name}.jsonl","w") as f:
        for r in sorted(rows, key=lambda r: r["id"]): f.write(json.dumps(to_pf(r), ensure_ascii=False)+"\n")
C = collections.Counter
def host(u): return u.split("/")[2] if u else "?"
summ = {"total": len(R), "dev": len(dev), "test": len(test), "seed": SEED,
  "label": C(r["label"] for r in R), "scam_type": C(r["scam_type"] for r in R),
  "lookalike_topics": C(r["topic"] for r in R if r["label"]=="legit"),
  "modality": C(r["modality"] for r in R), "language": C(r["language"] for r in R), "channel": C(r["channel"] for r in R),
  "source": C(host(r["source_url"]) for r in R), "edge_tags": C(t for r in R for t in r["edge_tags"]),
  "message_only": C(r["label"] for r in R if r["message_only"]),
  "test_label": C(r["label"] for r in test), "year": C(r["date"][:4] for r in R),
  "sha1_real_messages": hashlib.sha1(open("real_messages.jsonl","rb").read()).hexdigest()}
json.dump(summ, open("summary_real.json","w"), indent=1, ensure_ascii=False)
print(json.dumps(summ, ensure_ascii=False))
