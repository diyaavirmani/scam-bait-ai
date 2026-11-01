"""Builds the SB starter test set. Run: python3 build_testset.py  (needs /tmp/hf_all.json and /tmp/sms/SMSSpamCollection)
Created 29 Oct 2026 (IST). Every row carries source_url, license, synthetic."""
import json, random, re, hashlib, collections
random.seed(20261101)
rows = []
def rid(prefix, text): return prefix + "-" + hashlib.sha1(text.encode()).hexdigest()[:10]
def add(**r):
    r.setdefault("gold", {}); r.setdefault("edge_tags", []); r.setdefault("notes", None); r.setdefault("based_on", None)
    r["id"] = rid(r["origin"], r["text"]); rows.append(r)

# 1) Real, verbatim, official source (synthetic: false)
add(origin="official", text="Due to Social Media Platform's risk control measures, our previous group has been banned. This new group will provide daily recommendations of quality stock information and trading guidance. Please join the group.",
    label="scam", scam_type="investment_trading", modality="whatsapp", language="en",
    source_url="https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1792675550417.pdf",
    license="Government of India press release (SEBI PR 65/2026); quoted verbatim for research, no explicit open licence",
    synthetic=False, edge_tags=["group_reinvite"], notes="Quoted by SEBI as a typical re-invite message")

# 2) Real, verbatim messages quoted in public X posts by recipients (legit / ambiguous look-alikes)
X = [
 ("Dear Customer,Our technician shall visit your premises today to replace the meter. Your kind presence is solicited.Adani Electricity","https://x.com/Swapnil08742602/status/2076970609234620417","legit","utility"),
 ("Dear Customer, based on your request; Our technician shall visit today for verification purpose. Your kind presence is solicited. Adani Electricity","https://x.com/parmarravi/status/2063139369846992927","legit","utility"),
 ("Dear Customer, Your eKYC is pending. Complete it via IndianOil ONE App to book refills.","https://x.com/kaushalkishore_/status/2110951574436753551","legit","kyc_lookalike"),
 ("Dear Customer,Your Re-KYC request against 1-1621450672241 has been approved. INDANE","https://x.com/gd_as28972/status/2095393927113363701","legit","kyc_lookalike"),
 ("Dear Customer, your AutoPay mandate is successfully revoked towards BAJAJ FINANCE L for Rs 9900.00, RRN 102529333509-ICICI Bank.","https://x.com/Posc123/status/2014610222535606413","legit","bank_alert"),
 ("Dear Customer, This is to inform you that your JioFiber Service Request No. SR00002YR6TB for has been successfully processed. For any further support, please call us on 1800 896 9999.","https://x.com/vasanst/status/2021219648813813913","legit","service_update"),
 ("Dear customer, your docket has been closed. Docket Number-B0626106692212. BSNL Call Centre.","https://x.com/Sanjay_Pinto/status/2019713825185177896","legit","service_update"),
 ("Dear Customer, your account has been temporarily frozen due to non-compliance with KYC norms. Please update your KYC documents at the nearest branch - PNB.","https://x.com/vishawjitkumar/status/2029435004158443773","ambiguous","kyc_lookalike"),
 ("Dear Customer, Credit Turnover in your A/C X1665 exceeds the Threshold Limit. Please visit nearby branch to avoid digital blocking of account. -Indian Bank","https://x.com/_fatguy28/status/2109318700054782410","ambiguous","bank_alert"),
 ("Dear Your e-KYC for K-No. *71898******** is still pending.-----a DJB representative will visit your home to help complete the e-KYC process.- Thank you. Delhi Jal Board (DJB)","https://x.com/subirbi46211051/status/2105943962741817652","ambiguous","kyc_lookalike"),
 ("KYC Alert! A Periodic KYC update is needed for your HDFC Bank Cust ID xxxx as per RBI Guidelines. Link to Complete [link]","https://x.com/PehleTum/status/2059622528369537262","ambiguous","kyc_lookalike"),
]
for t,u,lab,sub in X:
    add(origin="xpost", text=t, label=lab, scam_type="none" if lab=="legit" else "unknown", modality="sms", language="en",
        source_url=u, license="Public X post quoted for research; X Terms of Service apply (share post IDs, not bulk text)",
        synthetic=False, edge_tags=["hard_negative", sub],
        notes=("Sender legitimacy not independently verified; recipient's post suggests genuine service message" if lab=="legit"
               else "Recipient was unsure if genuine; exclude from P/R, use for manual review"))

# 3) UCI SMS Spam Collection (real, UK/SG, 2011): 15 prize-style spam + 15 ham
uci = [l.rstrip("\n").split("\t",1) for l in open("/tmp/sms/SMSSpamCollection", encoding="latin-1")]
spam = [t for c,t in uci if c=="spam" and re.search(r"(?i)(won|prize|claim|urgent|winner|award)", t)]
ham = [t for c,t in uci if c=="ham" and len(t) > 40]
for t in random.sample(spam, 15):
    add(origin="uci", text=t, label="scam", scam_type="prize_premium_rate_uk", modality="sms", language="en",
        source_url="https://archive.ics.uci.edu/dataset/228/sms+spam+collection",
        license="SMS Spam Collection v.1 readme terms: free use, copyright T. Almeida & J.M. Gomez Hidalgo, cite Almeida et al. 2011 (DOI 10.24432/C5CC84)",
        synthetic=False, edge_tags=["non_indian","out_of_domain"])
for t in random.sample(ham, 15):
    add(origin="uci", text=t, label="legit", scam_type="none", modality="sms", language="en",
        source_url="https://archive.ics.uci.edu/dataset/228/sms+spam+collection",
        license="SMS Spam Collection v.1 readme terms (see above)", synthetic=False, edge_tags=["non_indian","everyday"])

# 4) HF synthetic, audited, CC BY 4.0: 5 per (label, language) = 70
hf = json.load(open("/tmp/hf_all.json"))
by = collections.defaultdict(list)
for r in hf:
    if r.get("audit_action") in ("keep","unreviewed","flip"): by[(r["label"], r["language"])].append(r)
for k in sorted(by):
    for r in random.sample(by[k], min(5, len(by[k]))):
        add(origin="hf", text=r["text"], label="scam" if r["label"]=="scam" else "legit",
            scam_type=r["scam_type"] if r["label"]=="scam" else "none", modality="sms", language=r["language"],
            source_url="https://huggingface.co/datasets/bhavya2910/indian-scam-sms-synthetic-audited",
            license="CC BY 4.0 (plus generator terms: "+r["generator"]+")", synthetic=True,
            edge_tags=(["hard_negative"] if r["label"]!="scam" else [])+(["regional"] if r["language"] not in ("en","hinglish") else []),
            notes="hf row_id "+r["row_id"]+"; audit_action "+r["audit_action"])

# 5) SB hand-written synthetic
ns = {}; exec(open("synthetic_seed.py").read(), ns)
for s in ns["S"]:
    add(origin="sb", text=s["text"], label=s["label"], scam_type=s["scam_type"], modality=s["modality"], language=s["language"],
        source_url=None, based_on=s["based_on"], license="CC0 (written by SB team for this test set)", synthetic=True,
        gold=s["gold"], edge_tags=s["edge_tags"], notes=s["notes"])

FIELDS = ["id","text","label","scam_type","modality","language","synthetic","source_url","based_on","license","edge_tags","gold","notes","origin"]
with open("messages.jsonl","w") as f:
    for r in rows: f.write(json.dumps({k:r.get(k) for k in FIELDS}, ensure_ascii=False)+"\n")
# eval subsets
with open("detection_eval.jsonl","w") as f:
    for r in rows:
        if r["label"] in ("scam","legit"):
            f.write(json.dumps({"vars":{"message":r["text"],"modality":r["modality"]},"assert_label":r["label"],"id":r["id"],"scam_type":r["scam_type"]}, ensure_ascii=False)+"\n")
with open("extraction_gold.jsonl","w") as f:
    for r in rows:
        if r["gold"]: f.write(json.dumps({"id":r["id"],"text":r["text"],"gold":r["gold"]}, ensure_ascii=False)+"\n")
c = collections.Counter
summary = {
 "total": len(rows),
 "by_label": c(r["label"] for r in rows), "by_synthetic": c(str(r["synthetic"]) for r in rows),
 "by_origin": c(r["origin"] for r in rows), "by_language": c(r["language"] for r in rows),
 "by_modality": c(r["modality"] for r in rows), "by_scam_type": c(r["scam_type"] for r in rows),
 "with_gold_extraction": sum(1 for r in rows if r["gold"]),
}
json.dump(summary, open("summary.json","w"), indent=1, ensure_ascii=False)
print(json.dumps(summary, indent=1, ensure_ascii=False))
