# SB starter test set (built 29 Oct 2026 IST)

Rebuild: `python3 build_testset.py` (needs /tmp/hf_all.json and /tmp/sms/SMSSpamCollection; seed 20261101).

## Files
- messages.jsonl: 158 rows. Fields: id, text, label (scam/legit/ambiguous), scam_type, modality, language, synthetic (true/false), source_url, based_on, license, edge_tags, gold, notes, origin
- detection_eval.jsonl: 154 rows (ambiguous excluded) for promptfoo
- extraction_gold.jsonl: 28 rows with gold fields (upiIds, bankAccounts, ifscCodes, groupLinks, appLinks, claimedRegNos, ...)
- conversations.jsonl: 6 synthetic scammer-playbook seeds for the persona A/B (investment x2, crypto, digital arrest, task job, customer care)
- promptfooconfig.detection.yaml / .extraction.yaml / .persona.yaml + providers/: skeletons (asserts/ and prompts/ still to write)

## Composition
| origin | rows | synthetic | licence |
|---|---|---|---|
| SEBI PR 65/2026 verbatim quote | 1 | false | Govt press release, quoted |
| Public X posts (recipients quoting SMS) | 11 (7 legit, 4 ambiguous) | false | X ToS; share post IDs, not bulk text |
| UCI SMS Spam Collection (UK/SG 2011) | 30 (15 prize spam, 15 ham) | false | readme terms, cite Almeida et al. 2011 |
| HF bhavya2910/indian-scam-sms-synthetic-audited | 70 (5 per label x 7 languages) | true | CC BY 4.0 + generator terms |
| SB hand-written | 46 | true | CC0 |

Labels: 82 scam, 72 legit, 4 ambiguous. Real 42 / synthetic 116.
Languages: en 80, hinglish 21, ta_en 12, hi 11, mr_en 11, te_en 11, bn_en 10, bn 1, ta 1.
Modalities: sms 128, whatsapp 17, voice_transcript 8, telegram 3, email 2.
Investment-related: 14 (investment_trading 12, crypto 1, recovery 1) + 5 investment legit look-alikes.

## Caveats
- Synthetic rows do not measure real-world accuracy (the HF card says the same). Report metrics split by synthetic true/false.
- UCI rows are UK/Singapore 2011: out-of-domain controls only.
- X-post legit labels rely on the recipient's post; sender not independently verified. Ambiguous rows are excluded from P/R.
- All SB numbers, UPI IDs, accounts are invented; links use the reserved .example TLD. Never dial, pay or visit anything here.
- Before sharing the repo publicly, replace X-post text with post IDs (X ToS).

## Real public-message set (added 29 Oct 2026 IST)
- real_messages.jsonl: 315 real rows, synthetic:false, all from public X posts (x API search), 2020 to Oct 2026. Every row has text, label, scam_type, channel, language, source_url, date, license, pii note, edge_tags, modality, message_only, lookalike.
- Labels: 173 scam (scammer-authored text only: quoted SMS/WhatsApp, direct spam posts, call scripts reported verbatim) and 142 legit look-alikes (victim reports, news/awareness posts, genuine bank/utility notices, casual chat that uses scam words).
- Split: detection_real_dev.jsonl 221 (tune here) / detection_real_test.jsonl 94 (51 scam, 43 legit; report once). Stratified by label x type, seed 20261101. Deduped against messages.jsonl.
- PII: victim phones/IDs masked (first2+last2), personal emails -> [email], handles -> @user, t.co -> [link]. Scammer numbers in official advisories kept.
- Shortfall: scam-authored rows are 173, not 300. Zero or one scam-authored rows for sextortion, UPI collect/QR, loan-app harassment, e-challan, digital arrest, romance. These appear only as legit discussion look-alikes. Do not claim coverage for them.

## Eval wiring
- promptfooconfig.detection_real.yaml: A Decisions stage 3 (providers/decisions_provider.py) vs B cerebras:gpt-oss-120b stage 2 (strict JSON incl. p_scam) vs C regex keyword floor, same test split. Single arms only.
- ensemble/score_arms.py: per-row p_regex, p_cerebras, p_decisions and latencies for --split dev|test (keys in env; --workers 1 on the Cerebras Free Trial). ensemble/tune_ensemble.py: tunes E1 weighted / E2 Cerebras-unless-borderline / E3 stacked logistic (+ OR/AND) on dev, reports every arm once on test (P/R/F1 + 95% bootstrap CI, look-alike FP, per-type recall, p50/p95). `--selftest` uses random numbers: wiring check only, NOT results.
- promptfooconfig.mock_dryrun.yaml: same split/asserts with providers/mock_provider.py. Wiring proof only; mock numbers are not model results.
- promptfooconfig.extraction_regex.yaml: keyless regex baseline on extraction gold.
- asserts/label_match.py (TP/FP/FN/TN + FP_lookalike), asserts/field_f1.py (field micro P/R/F1), asserts/_parse.py (parses Decisions/Cerebras/mock output; Decisions field names unverified).
- metrics.py out/x.json [--threshold t] [--md]: P/R/F1, message-only and non-English slices, look-alike FP, per-type recall, p50/p95 latency (provider-measured).
- Commands: npx promptfoo@latest eval -c promptfooconfig.detection_real.yaml --no-cache --repeat 3 -o out/real_test.json && python3 metrics.py out/real_test.json --md
- Keyless results (real, deterministic): regex keyword floor on real test: P 0.69 R 0.53 F1 0.60, look-alike FP 12/43. Regex extraction on gold (synthetic texts): field micro P 0.58 R 0.26, exact 4/28.
- Repo bug found: app/agents/extraction.py extract_apk_links backtracks exponentially on URLs not ending in .apk (20-char host 1.5 s; a 167-char gold message took 281 s). regex_only.py uses a linear pattern by default (config safe_apk). Fix suggestion: r'https?://[^\s<>"\']+?\.apk\b'.

## v2 append (Task 7, 2026-10-29 IST)
- +87 real scam rows (synthetic:false) via `append_realset.py` from the hand-curated `curated_v2_spec.py`. Every X extract was checked to be an exact substring of the post (HTML-unescaped, whitespace-collapsed) before masking.
- Totals: 402 rows (260 scam / 142 legit). Dev 280 (+59), test 122 (+28). v1 rows were not moved. Only the new rows were split 70/30, stratified by (label, scam_type) with Random(20261101), and appended.
- New scam types: sextortion 11, upi_collect_qr 14, loan_app_harassment 9, e_challan 5. Boosted: digital_arrest 1->5, romance 1->7, job_task 7->27, investment 8->17, courier_fedex_drugs 6->9.
- Origins of new rows: x_search 71, advisory_quote 4, news_quote 4 (Inc42, BBC), kaggle_verified_source 8.
- Labelling: a row is scam only when the text is the scammer's own words (a quoted message, a direct spam post, or a reported call or threat clause). For call_script_reported and threat_reported rows the text is the reporter's rendering of what the caller said, so it may be indirect speech.
- Sextortion rows hold threat or extortion text only. They contain no explicit content.
- Backup of v1 files: /tmp/bak_v1/ (box-local).
