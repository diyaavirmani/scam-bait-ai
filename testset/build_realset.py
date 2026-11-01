"""Curate REAL public posts (raw_x/posts.jsonl) into real_messages.jsonl + 70/30 split.
No synthetic rows. Victim PII masked (phones/account-like numbers format-preserving, @handles -> @user).
Rows are rule-classified; drop_ids.txt holds manual rejections after review."""
import json, re, hashlib, random, collections, unicodedata, os
D = os.path.dirname(os.path.abspath(__file__))
SEED = 20261101
raw = [json.loads(l) for l in open(f"{D}/raw_x/posts.jsonl")]
drop = set(l.split()[0] for l in open(f"{D}/drop_ids.txt") if l.strip() and not l.startswith('#')) if os.path.exists(f"{D}/drop_ids.txt") else set()
LIC = "X post, public; quoted for non-commercial research/eval under X ToS fair-use excerpting; do not redistribute bulk"

def norm(t): return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", t).lower())
def mask_num(m):
    s = m.group(0); d = [c for c in s if c.isdigit()]
    if len(d) < 6: return s
    keep = set(range(2)) | set(range(len(d)-2, len(d))); out=[]; i=0
    for c in s:
        if c.isdigit(): out.append(c if i in keep else "X"); i+=1
        else: out.append(c)
    return "".join(out)
def mask(t):
    t = re.sub(r"https?://t\.co/\w+", "[link]", t)
    t = re.sub(r"[\w.+-]+@(gmail|yahoo|hotmail|outlook|rediffmail|icloud|proton\w*)\.\w+", "[email]", t, flags=re.I)
    t = re.sub(r"(?<![\w.])@\w{2,}", "@user", t)
    t = re.sub(r"(\+?\d[\d \-]{7,}\d)", mask_num, t)
    t = re.sub(r"\b([A-Z]{1,4}\d{6,})\b", lambda m: m.group(1)[:3] + "X"*(len(m.group(1))-5) + m.group(1)[-2:], t)
    t = t.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
    return re.sub(r"[ \t]+", " ", t).strip()
def clean_tail(t):
    t = re.sub(r"^(\s*@user\s*)+", "", t)
    t = re.sub(r"(\s*(@user|#\w+|\[link\]))+\s*$", "", t)
    return t.strip(" /\n-:")

SCRIPTS = [("hi","\u0900","\u097F"),("bn","\u0980","\u09FF"),("pa","\u0A00","\u0A7F"),("gu","\u0A80","\u0AFF"),("ta","\u0B80","\u0BFF"),("te","\u0C00","\u0C7F"),("kn","\u0C80","\u0CFF"),("ml","\u0D00","\u0D7F")]
HING = r"\b(hai|hain|kya|aap|aapka|apka|nahi|nahin|karo|kare|karein|kijiye|mera|mere|mujhe|paise|bhai|rha|raha|gaya|ho gya|ji|se|ka|ki|ke)\b"
def lang(t):
    c = collections.Counter()
    for ch in t:
        for code,a,b in SCRIPTS:
            if a <= ch <= b: c[code]+=1
    if c and c.most_common(1)[0][1] > 15: return c.most_common(1)[0][0] + ("+en" if re.search(r"[A-Za-z]{4,}.*[A-Za-z]{4,}", t) else "")
    if len(re.findall(HING, t.lower())) >= 3: return "hinglish"
    return "en"

# (scam_type, regex on lowercased raw text). Order matters.
CATS = [
 ("bank_reward_points", r"reward points?.{0,160}(expir|redeem)"),
 ("utility_disconnect", r"(gas connection|gas\W? connection|\bgas\b|electric\w*|el[e3]ctr\S*|eiectr\S*|बिजली|power).{0,160}(disconnect|cut|officer|bill.{0,20}not.{0,10}updat|कट)"),
 ("courier_indiapost", r"india\s*post.{0,200}(warehouse|address|redeliver|24 hours|12 hours|48 hours|update)"),
 ("kyc_sim_wallet", r"(paytm|pytm|patyam|payt\w*|airt\S*|jio|bsnl|vi |vodafone|s\.?i\.?m\b|sim card|e-?kyc).{0,200}(block|suspend|expire|deactivat|band|reject|pending|panding|cancel)"),
 ("kyc_bank_pan", r"(yono|kyc|pan card|pan number|\bpan\b).{0,200}(block|suspend|expire|deactivat|band|reject|pending)|(block|suspend|expire).{0,120}(yono|kyc|pan card)"),
 ("voice_trai_telecom", r"(trai|telecom|dot\b|mobile number|phone number|connections?).{0,200}(block|disconnect|press 9|ivr|2 hours|suspend)"),
 ("courier_fedex_drugs", r"(fedex|dhl|courier|parcel).{0,250}(drug|mdma|narcotic|press|customs|illegal|cancel|returned)"),
 ("digital_arrest", r"digital(ly)? arrest|डिजिटल अरेस्ट|(cbi|crime branch|police|narcotics).{0,120}(money laundering|aadhaar|arrest warrant|video call)"),
 ("lottery_kbc", r"(kbc|kaun banega|lucky draw|lottery|congratulation).{0,250}(lakh|lac|winner|won|prize|claim|₹|rs|number)"),
 ("e_challan", r"(challan|चालान|traffic violation|parivahan).{0,250}(apk|link|pay|fine|evidence)"),
 ("job_task", r"(part[\s-]?time|work from home|prepaid task|telegram task|daily (income|salary|earn)|youtube.{0,20}like).{0,250}(salary|earn|daily|per day|wa\.me|₹|rs|\$|lakh|task)"),
 ("loan_app_harassment", r"loan.{0,250}(contact|morph|threat|harass|nude|abus|viral|dhamki)"),
 ("sextortion", r"sextortion|सेक्सटॉर्शन|nude (video )?call|blackmail.{0,80}video|video viral kar dunga"),
 ("customer_care", r"customer care number|complaint number|(fake|fraud)\W{0,3}customer[\s-]?care|customer care.{0,80}(fake|fraud|anydesk|teamviewer|quick ?support)|(anydesk|teamviewer|quick ?support)"),
 ("investment_trading", r"dear investor|intraday|nifty|tips provider|vip subscriber|(stock|trading|ipo|investment|invest|share market|crypto|usdt).{0,250}(whatsapp|telegram|group|returns|profit|app|platform)"),
 ("upi_collect_qr", r"(collect request|qr code|scan.{0,30}qr|army officer.{0,80}(olx|qr))"),
 ("govt_scheme_fake", r"#pibfactcheck|yojana|free laptop"),
]
LEGIT = r"(हम से संपर्क करने के लिए|प्रिय ग्राहक|thank you for contacting|docket number|dear applicant|your req\.? ?no|service request\s+no|processing fee within|request money|is your otp)"
AWARE = r"(beware|alert|awareness|advisory|never (share|ask)|do not|don'?t|stay safe|report (at|on|to)|1930|#fake|is #?fake|be aware|सावधान|explainer|tips:|busted|arrested|गिरफ्तार|fraud|scam|fake|victim|lost|cheated|duped|help me|take action|complain)"
STRONG = r"(?i:India\s*Post\s*:|Indiapost\s*:|Dear\W{0,3}(C\S{0,3}stomer|Consum\w*|SBI [Uu]ser|[Uu]ser|Airtel SIM customer)\b|Many Congrat\w*|Your package has|Your (FedEx|Fedex) parcel|Challan\s+[A-Z]{2}\d|I'?m\s+\w+\s+\w+\s+[Ff]rom\s+KBC|Your HDFC Credit Card Reward)|प्रिय उपभोक्ता"
QUOTE = re.compile(r"(?:(?<=^)|(?<=[\s:(\-]))(?:“([^”“\"]{40,600})”|\"([^\"“”]{40,600})\")")
REPORT = r"(received|recieved|recd|rcvd|got|getting|i get|msg from|message from|sms from|called me|call from|calling me|someone called|fraud msg|this msg|this message|following|similar msg|look at this|saying|stating|claimed|it said|says)"
CUE = r"(wa\.me|whatsapp|telegram|call|contact|\d{10}|\[link\]|\bdm\b|message me|join|private message)"
OVR = json.load(open(f"{D}/overrides.json")) if os.path.exists(f"{D}/overrides.json") else {}

def classify(p):
    t = p["text"]; lo = t.lower(); pid = p["id"]
    if pid in drop or t.startswith("RT @"): return None
    if p.get("lang") not in (None,"en","hi","und","in","te","ta","kn","ml","mr","bn","gu","pa","qme","zxx","qht"): return None
    if re.search(r"nigeria|naira|fccpc|₦|\bngn\b|kenya|ghana|philippin|\brm\s?\d", lo): return None
    m = mask(t)
    if pid in OVR:
        o = OVR[pid]
        if o == "drop": return None
        if o in ("disc","casual","promo"):
            st0 = next((st for st, rx in CATS if re.search(rx, lo, re.S)), "other")
            return dict(label="legit", scam_type="legit_lookalike", modality={"disc":"scam_discussion","casual":"casual_chat","promo":"promo_ad"}[o], text=clean_tail(m), topic=st0)
        txt = m
        if o.get("from"):
            i = m.find(o["from"]); txt = m[i:] if i >= 0 else m
            txt = re.split(r"\s*(Take action|\(1/4\)|Report this asap)", txt)[0]
        return dict(label=o["label"], scam_type=o["scam_type"], modality=o["modality"], text=clean_tail(txt), topic=o.get("topic", o["scam_type"]))
    if re.search(LEGIT, lo) and not re.search(r"fraud|scam|fake", lo):
        return dict(label="legit", scam_type="legit_lookalike", modality="genuine_service_msg", text=clean_tail(m), topic="genuine_service")
    for st, rx in CATS:
        if not re.search(rx, lo, re.S): continue
        q = [a or b for a,b in QUOTE.findall(m) if len(a or b) >= 40]
        is_report = re.search(REPORT, lo); aware = re.search(AWARE, lo)
        sm = re.search(STRONG, m)
        if sm and len(m) - sm.start() >= 50:
            seg = re.split(r"\n\s*\n|\n(?=(PL|Pls|Please|Kindly take|Regards|Sir|@user|#))", m[sm.start():])[0]
            if len(seg) >= 40:
                return dict(label="scam", scam_type=st, modality="quoted_scam_msg", text=clean_tail(seg), topic=st)
        if q and is_report:
            return dict(label="scam", scam_type=st, modality="quoted_scam_msg", text=clean_tail(max(q, key=len)), topic=st)
        if st in ("voice_trai_telecom","courier_fedex_drugs","digital_arrest","customer_care","e_challan","loan_app_harassment","sextortion","lottery_kbc") and is_report:
            cm = re.search(r"\b(saying|stating|stated|says|said|claim(?:ed|ing)? (?:that|to be)|telling|told me|it said|informing|dhamki de (?:raha|rha) hai ki|that)\b", m, re.I)
            if cm:
                seg = m[cm.end():].strip(" :,'\"“”")
                seg = re.split(r"\n\s*\n|(?<=[.!?])\s+(?=(Please|Pls|Kindly|Sir|I |This is|Is this|Request|Can |@user))", seg)[0][:400]
                if len(seg) >= 30:
                    mod = "threat_reported" if st in ("loan_app_harassment","sextortion") else "call_script_reported"
                    return dict(label="scam", scam_type=st, modality=mod, text=clean_tail(seg), topic=st)
        if st in ("job_task","lottery_kbc","customer_care","investment_trading") and not aware and re.search(CUE, lo):
            return dict(label="scam", scam_type=st, modality="direct_spam_post", text=clean_tail(m), topic=st)
        return dict(label="legit", scam_type="legit_lookalike", modality="scam_discussion", text=clean_tail(m), topic=st)
    if re.search(r"video viral kar", lo):
        return dict(label="legit", scam_type="legit_lookalike", modality="casual_chat", text=clean_tail(m), topic="sextortion_keyword_casual")
    return None

def channel(lo, mod):
    if mod in ("direct_spam_post",): return "x_post"
    if mod in ("scam_discussion","casual_chat") and not re.search(r"\b(i|my|me)\b", lo): return "x_post"
    if mod=="genuine_service_msg" and "thank you for contacting" in lo and "docket" not in lo: return "x_post"
    if re.search(r"\bivr\b|press \d|called|call from|calling|voice call|video call|phone call", lo): return "voice_call"
    if "whatsapp" in lo or "wa.me" in lo: return "whatsapp"
    if "telegram" in lo: return "telegram"
    if re.search(r"\bsms\b|msg|text message|message from", lo): return "sms"
    return "unknown"

def edge(text, raw):
    tags=[]
    if any(ord(c)>0x2000 and unicodedata.category(c)=="So" for c in text): tags.append("emoji")
    if re.search(r"[A-Za-z][\u00C0-\u024F][A-Za-z]|incompIete|\b[A-Za-z]+[0-9][A-Za-z]+\b", text): tags.append("obfuscation_homoglyph")
    if re.search(r"\b(pls|plz|ur|u r|immediatly|recharg|updatd|tonight\s*\.|nite|ofice|officar|discon\b)", text.lower()): tags.append("typo_slang")
    if len(text) < 60: tags.append("short")
    if re.search(r"\$|usd|us dollars|philippin", text.lower()): tags.append("non_india_locale")
    if "[link]" in text: tags.append("link_redacted_tco")
    if "/apk" in text.lower() or ".apk" in text.lower() or " apk" in text.lower(): tags.append("apk")
    return tags

rows=[]; seen=set(); base=set(norm(json.loads(l)["text"]) for l in open(f"{D}/messages.jsonl"))
percap=collections.Counter(); CAP={"quoted_scam_msg":40,"direct_spam_post":12,"genuine_service_msg":16,"casual_chat":6,"call_script_reported":14,"threat_reported":10}
AW_CAP=6
for p in sorted(raw, key=lambda p: p["id"]):
    c = classify(p)
    if not c or len(c["text"]) < 25: continue
    k = norm(c["text"])
    if k in seen or k in base or any(k[:60]==s[:60] for s in seen if len(k)>60): continue
    capk = (c["topic"], c["modality"])
    cap = (AW_CAP+5 if lang(c["text"])!="en" else AW_CAP) if c["modality"]=="scam_discussion" else CAP.get(c["modality"], 12)
    if percap[capk] >= cap: continue
    percap[capk]+=1; seen.add(k)
    lo = p["text"].lower()
    rows.append(dict(
        id="rx_"+hashlib.sha1(c["text"].encode()).hexdigest()[:10], text=c["text"], label=c["label"], scam_type=c["scam_type"],
        channel=channel(lo, c["modality"]), modality=c["modality"], language=lang(c["text"]),
        source_url=p["url"], date=(p.get("date") or "")[:10], license=LIC, synthetic=False,
        edge_tags=edge(c["text"], p["text"]), pii="victim phones/ids masked first2+last2, handles->@user, t.co->[link]",
        origin="x_search", query_batch=p.get("q"), topic=c["topic"]))
# multi-message sequences: consecutive posts by same victim thread are rare; tag rows whose text has >=2 quoted msgs
for r in rows:
    if len(QUOTE.findall(r["text"])) >= 2: r["edge_tags"].append("multi_message")
json.dump(rows, open("/tmp/real_rows.json","w"), ensure_ascii=False, indent=0)
print(len(rows)); print(collections.Counter(r["scam_type"] for r in rows)); print(collections.Counter(r["modality"].split(":")[0] for r in rows)); print(collections.Counter(r["language"] for r in rows)); print(collections.Counter(r["channel"] for r in rows))
