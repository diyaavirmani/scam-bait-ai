# Sources for based_on references
- SEBI PR 65/2026 (group re-invite quote): https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1792675550417.pdf
- SEBI PR 20/2026: https://www.sebi.gov.in/sebi_data/attachdocs/mar-2026/1774448914437.pdf
- SEBI PR 64/2025 (@valid UPI handles): https://www.sebi.gov.in/sebi_data/attachdocs/oct-2025/1759322811695.pdf
- SEBI PR 22/2025: https://www.sebi.gov.in/sebi_data/attachdocs/may-2025/1746621138080.pdf
- SEBI PR 27/2025: https://www.sebi.gov.in/sebi_data/attachdocs/may-2025/1747825040886.pdf
- NSE press releases: https://www.nseindia.com/resources/exchange-communication-press-releases
- The Hindu 24 Jun 2026, Rs 122 crore case: https://www.thehindu.com/news/cities/Hyderabad/hyderabad-police-arrest-six-in-122-crore-investment-fraud/article71141696.ece
- TOI 18 Jan 2026, Rs 3 crore IPO scam: https://timesofindia.indiatimes.com/city/hyderabad/hyderabad-techie-falls-prey-to-online-trading-ipo-investment-scam-loses-3-crore/articleshow/126624733.cms
- TOI, fake Barclays advisory group: https://timesofindia.indiatimes.com/city/hyderabad/2-city-victims-lose-over-4cr-in-fake-stock-trading-frauds/articleshow/128045038.cms
- Tribune, pig butchering Rs 19.8 crore: https://www.tribuneindia.com/news/punjab/pig-butchering-how-trust-turned-into-a-rs-19-8-crore-crypto-fraud/
- FBI, crypto + recovery scams: https://www.fbi.gov/news/press-releases/cryptocurrency-and-ai-scams-bilk-americans-of-billions
- PIB Fact Check: MUDRA fee https://x.com/PIBFactCheck/status/2099098810396115076 ; FM deepfake investment https://x.com/PIBFactCheck/status/2092963236706730177 ; laptop scheme https://x.com/PIBFactCheck/status/2101969051866272194 ; India Post survey https://x.com/PIBFactCheck/status/2090665041360200112 ; Jan Dhan scratch card https://x.com/PIBFactCheck/status/2094632772057145578
- e-challan phishing reports: https://x.com/AnkitNayak_dev/status/2099474648748708001 , https://x.com/ankitvyas19/status/2098258899761779136 ; Mahanagar Gas APK: https://x.com/here_pooh/status/2073409233597681678
- NCRP checklist: https://cybercrime.gov.in ; 1930 instructions: https://cybercrime.gov.in/UploadMedia/instructions_citizenreportingcyberfrauds.pdf

## Real set sources and leads (29 Oct 2026 IST)
- Used: X public posts via x API search_posts_all (14 query batches, ~1,340 raw posts screened -> 315 kept). Licence: X Terms; internal eval only, do not redistribute bulk text.
- Blocked / leads only (not in the set):
  - Reddit (r/LegalAdviceIndia, r/india, r/IndianScams): direct fetch blocked, Arctic Shift mirror timed out. Lead for sextortion threat texts, loan-app harassment, task scams.
  - Facebook cyber-cell pages (state cyber police, Cyber Dost): need login; not logged in by rule.
  - Government advisories (PIB Fact Check, I4C/Cyber Dost, SEBI, RBI, CERT-In, TRAI): good for scammer templates and identifiers; not ingested this round.
  - HF datasets rejected for real-only set (rows not marked real vs synthetic): gandharvbakshi/SMS-dataset-OTP-OTP_INTENT_Phishing (MIT, gated, mixed), anmolshrivastav/scam-ham-india (no licence, mixed), Shade63/scam-classification-multiclass (provenance unclear).
  - Kaggle/GitHub SMS spam corpora: not checked this round (licence and real-vs-synthetic need per-dataset review); not used.

## v2 sources (Task 7)
- X search (public posts; IDs and URLs are in each row): sextortion threat reports, UPI QR/collect reports, loan-app recovery threats, e-challan SMS, courier/customs scripts, romance and job/investment spam.
- News, verified verbatim by curl on 2026-10-29 IST:
  - Inc42, Moneed loan-reference message: https://inc42.com/buzz/digital-lenders-get-aggressive-as-loan-recovery-stalls-in-pandemic/
  - TOI Kolkata, e-challan template from the Kolkata Police cyber cell: https://timesofindia.indiatimes.com/city/kolkata/articleshow/125570472.cms
  - BBC "You are under digital arrest", 3 scammer lines: https://www.bbc.com/news/articles/cdrdyxk4k4ro
  - India Today 2024-09-17: the quote "You are under [digital] arrest" was verified, but it was deduped because it matches a synthetic base row.
- Kaggle nikhilchauhan02 (CC BY 4.0): only 13 of 228 "real" scam rows matched their cited page at fuzzy score 0.95 or above. 10 of those were used, 8 survived dedupe, and each is cited to the original page, not to Kaggle. The rest were rejected as unverifiable.
- Unavailable or rejected:
  - Reddit: the evidence is mostly screenshots with no text.
  - Facebook: needs a login, so it was not accessed.
  - HF scam-hum-india and Indian_Cyber_Scam_PhoneCall_Hinglish: synthetic or curated, or not flagged as real.
  - X e-challan APK posts: screenshot only.
  - Most digital-arrest and romance X posts: awareness posts or third-person narration with no verbatim scammer text.
  - BBC and News18 pig-butchering pieces: no verbatim scam text.
