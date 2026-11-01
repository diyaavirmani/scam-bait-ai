# Evaluation results

Measured numbers only. Anything that did not run says "not run" and why.

| Run | Value |
|---|---|
| Date | 1 Nov 2026 |
| Offline arms | started 13:53:39 IST, ended 13:53:39 IST (`.venv/bin/python -B scripts/eval_offline.py`) |
| Git commit | `534ea2d` (local; the evaluated app code is identical to pushed `6467dd1`) |
| Model IDs called | offline arms: none. Real-API test run later the same day: see section 6 |
| RPM settings | not configured (`.env` missing); defaults would be `CEREBRAS_RPM_OSS=5`, `CEREBRAS_RPM_QWEN=5` |
| DEMO_MODE | 0 (unset) |
| Data | `testset/detection_real_test.jsonl` (122 rows: 79 scam, 43 legit look-alikes), `testset/detection_real_dev.jsonl` (280 rows, used only to pick the prefilter threshold), `testset/extraction_gold.jsonl` (28 rows) |
| Raw outputs | `out/eval/detection_offline_test.jsonl`, `out/eval_summary.json` (git-ignored) |

## Summary: detection, 122-row test split

| Arm | P | R | F1 | Look-alike FPs | p50 ms | p95 ms | Cost per 1k messages |
|---|---|---|---|---|---|---|---|
| a. Old keyword baseline (scambait-old `extract_keywords`, scam if 2+ hits) | 0.70 | 0.35 | 0.47 | 12 of 43 | 0.012 | 0.017 | $0 (local) |
| b. New regex prefilter (scam if any feature fires; threshold 0.05 picked on dev, F1 0.74 there) | 0.71 | 0.84 | 0.77 | 27 of 43 | 0.062 | 0.094 | $0 (local) |
| c. Cerebras qwen-3.8-27b flag | not run | not run | not run | not run | not run | not run | not run |
| d. Cerebras gpt-oss-120b flag | not run | not run | not run | not run | not run | not run | not run |
| e. OpenAI Decisions gpt-6-luna | not run | not run | not run | not run | not run | not run | not run |
| f. Final E2 ensemble as shipped | not run | not run | not run | not run | not run | not run | not run |

Arms c to f need the API keys. Latencies for a and b are local CPU time per message on the build laptop, with no network.

## 1. Detection details

### Accuracy, confusion matrix, errors

| Arm | Accuracy | TP | FP | FN | TN | Errors / UNKNOWN | Cerebras tokens/s |
|---|---|---|---|---|---|---|---|
| a. Old keyword baseline | 0.48 | 28 | 12 | 51 | 31 | 0 | n/a (no model) |
| b. New regex prefilter | 0.67 | 66 | 27 | 13 | 16 | 0 | n/a (no model) |
| c to f | not run | | | | | | |

The re-run of arm a matches the kit's earlier figures exactly (P 0.70, R 0.35, F1 0.47, 12 of 43).

### Per language (test split)

| Language | Rows | Scam rows | a: TP / FP / FN / TN | b: TP / FP / FN / TN |
|---|---|---|---|---|
| en | 106 | 78 | 27 / 10 / 51 / 18 | 65 / 18 / 13 / 10 |
| hinglish | 6 | 1 | 1 / 1 / 0 / 4 | 1 / 3 / 0 / 2 |
| hi | 6 | 0 | 0 / 0 / 0 / 6 | 0 / 4 / 0 / 2 |
| mixed (hi+en, te+en) | 4 | 0 | 0 / 1 / 0 / 3 | 0 / 2 / 0 / 2 |

The non-English rows are almost all legit look-alikes (1 scam out of 16), so per-language recall cannot be judged from this split.

### Per scam type recall

The brief asks for the final ensemble; it was not run. The two arms that ran:

| Scam type | Scam rows | a. Old baseline | b. New prefilter |
|---|---|---|---|
| kyc_sim_wallet | 11 | 11 | 11 |
| utility_disconnect | 11 | 0 | 8 |
| kyc_bank_pan | 9 | 9 | 9 |
| job_task | 8 | 2 | 7 |
| investment_trading | 5 | 1 | 3 |
| lottery_kbc | 5 | 3 | 5 |
| customer_care | 4 | 0 | 4 |
| upi_collect_qr | 4 | 0 | 4 |
| voice_trai_telecom | 4 | 0 | 4 |
| courier_fedex_drugs | 3 | 0 | 3 |
| loan_app_harassment | 3 | 0 | 2 |
| sextortion | 3 | 0 | 1 |
| bank_reward_points | 2 | 2 | 2 |
| courier_indiapost | 2 | 0 | 2 |
| e_challan | 2 | 0 | 1 |
| romance_pig_butchering | 2 | 0 | 0 |
| digital_arrest | 1 | 0 | 0 |

### 10 worst misses of the new prefilter (ids only, no message text)

| Message id | Gold | Type | Lang | a. Old baseline | b. Prefilter (score) |
|---|---|---|---|---|---|
| rx_016b8d9101 | scam | utility_disconnect | en | not scam | not scam (0.0) |
| rx_0be7f48e0a | scam | investment_trading | en | not scam | not scam (0.0) |
| rx_11d103eeac | scam | investment_trading | en | scam | not scam (0.0) |
| rx_5aa74e7539 | scam | utility_disconnect | en | not scam | not scam (0.0) |
| rx_5b168a01c3 | legit | legit_lookalike | hinglish | scam | scam (1.0) |
| rx_fedec42ed7 | scam | utility_disconnect | en | not scam | not scam (0.0) |
| rx_22119d4ff4 | scam | loan_app_harassment | en | not scam | not scam (0.0) |
| rx_370d519284 | scam | digital_arrest | en | not scam | not scam (0.0) |
| rx_3d12b6e913 | scam | job_task | en | not scam | not scam (0.0) |
| rx_90cfa96cbf | scam | e_challan | en | not scam | not scam (0.0) |

Model arms' verdicts for these rows: not run.

## 2. Extraction, 28 gold rows

The combined persona call (intel inside the one strict-JSON persona call) and a separate extraction call both need Cerebras: not run. What ran is the regex half of the pipeline: the new `extract()` + `validate()` against the old regex extractor. Scoring covers the 7 intel fields in the brief. URL gold is phishing, group, app and APK links together; "name" gold is `beneficiaryNames` (1 row).

The old extractor ran with its exponential APK regex swapped for a linear one, as the kit's own baseline did; as shipped, it hangs on gold row sb-f9df47e303 (AUDIT X-01).

| Field | Old regex TP / FP / FN | New regex TP / FP / FN |
|---|---|---|
| UPI | 6 / 3 / 0 | 6 / 0 / 0 |
| Phone | 3 / 0 / 0 | 3 / 0 / 0 |
| Bank account | 1 / 4 / 0 | 1 / 0 / 0 |
| IFSC | 1 / 0 / 0 | 1 / 0 / 0 |
| URL | 4 / 1 / 3 | 7 / 1 / 0 |
| APK | 1 / 0 / 0 | 1 / 0 / 0 |
| Name | 0 / 0 / 1 (no name extraction) | 0 / 1 / 1 |
| **All 7 fields: precision / recall** | **0.67 / 0.80** | **0.90 / 0.95** |
| **Exact-match rows** | **20 of 28** | **26 of 28** |
| p50 / p95 per row | 0.27 / 0.54 ms | 0.16 / 0.39 ms |

The kit's earlier old-regex figure (P 0.58, R 0.26, 4 of 28 exact) scored more gold fields, including ones no regex can produce (impersonated entities, investment stage, platforms), so it is not comparable with this 7-field scoring. Both columns above use the same scoring.

**False positives listed.**
- **Old regex (8):**
  - UPI `available@22`, `seized@customs`, `tonight@9`: the "at" to "@" rewrite, the same bug as "call me at 5pm".
  - Bank account `9000012345`, `919000012345`, `9000054321`, `9000067890`: phone numbers counted twice.
  - URL `whatsapp.example/abcdef123`.
- **New regex (2):**
  - URL `coinvault-pro.example`: a bare platform domain the gold row does not list as a link.
  - Name `anika`.

The "call me at 5pm" class of error and the phone-as-account duplicates are gone.

## 3. Persona memory

The 3-chat test as specified was not run. One real 16-turn chat ran (section 6): before the persona fix, turn 15 did not recall the message-1 code (0 of 1); after the fix it recalled GOLD77 (1 of 1). No AI admission in either run.

## 4. Latency end to end

A real Telegram message-to-reply run (20+ messages through Telegram) was not done. The real 16-turn chat through the API is in section 6. Measured instead, the local steps on the build laptop (200 runs each, no network):

| Step | p50 ms | p95 ms |
|---|---|---|
| Regex prefilter | 0.034 | 0.039 |
| Extraction + validators | 0.163 | 0.179 |
| DB write (`add_message`, SQLite WAL) | 0.248 | 0.345 |
| Event store + SSE fan-out to one subscriber queue | 0.323 | 0.430 |
| Cerebras flag, Decisions, persona | not run | not run |

Regex freeze fixes, measured earlier at 13:44 IST (median of 5):

| Input (old time from AUDIT.md 6.3) | New prefilter | New extraction |
|---|---|---|
| `http://` + 160 x `a` (old APK regex: did not finish in 330 s) | 0.07 ms | 0.07 ms |
| `you are now ` to 2,880 chars (old jailbreak regex: 35.2 s) | 0.45 ms | 2.30 ms |
| `txn of ` to 10k chars (old trusted-sender regex: 13.7 s) | 0.72 ms | 2.57 ms |
| `http://` repeated to 10k chars (suggested lazy APK regex: 0.175 s) | 0.47 ms | 1.22 ms |

## 5. Rate-limit drill

The 10-messages-in-30-seconds drill was not run. In the real chat runs (section 6), the limiter held `gpt-oss-120b` to 5 requests per minute, and one real 429 was retried on the same model after 56 s with the reply delivered. The mocked drill is in `tests/test_a1_providers.py`.

## 6. Real-API test run (1 Nov 2026, 15:24 to 16:00 IST)

Real calls with the user's keys, local app on commit `ce80fd2` plus the persona fix later pushed as `f2593c9`. The 122-row model eval (arms c to f) was not part of this run and is still not run.

| Check | Result |
|---|---|
| Cerebras model list | HTTP 200 in 584 ms; `gpt-oss-120b` and `qwen-3.8-27b` served |
| `qwen-3.8-27b` tiny strict-JSON call | HTTP 200, 472 ms wall, 2,661 tokens/s from `time_info`; rate-limit headers: 450 requests/min, 27,000/hour, 648,000/day |
| `gpt-oss-120b` tiny strict-JSON call | HTTP 200, 1,308 ms wall (722 ms queue), 1,513 tokens/s; rate-limit headers: 5 requests/min, 150/hour, 2,400/day, 1M tokens/day |
| Decisions `gpt-6-luna` | Real response saved redacted to `tests/fixtures/decisions_sample.json`; parser mapping matched (p_scam 0.88, investment_trading) |
| Moderation | 2,046 ms, flagged false |
| GPT-Live `gpt-live-1` | Access yes. With audio frames flowing, the greeting "Hello? Who is this?" started 1.7 s after the session opened; output audio and transcript events arrived. Caller transcript not checked (needs real speech) |
| 16-turn DEMO chat, first run | Scam flagged at turn 1. **Bug:** the persona looped on asking for the phone number, and turn 15 did not recall GOLD77 |
| 16-turn DEMO chat after the persona fix | Flagged at turn 1 (qwen 0.95, Decisions 0.74); turn 15 recalled GOLD77; no AI admission (turn 13); injection deflected (turn 14); Hinglish reply at turn 3; closed on "ok bye" at turn 18 |
| Intel vs DEMO checklist | 2 links, 1 APK, 1 UPI, 1 phone, 1 bank account, 1 IFSC, 3 names; no `me@5pm`; phone not counted as an account |
| Latency per turn (16 turns, fixed run) | p50 807 ms, p95 56,409 ms. The slow turns are the 5 requests/min limiter on `gpt-oss-120b`. Persona p50 846 ms; qwen flag 791 ms; Decisions p50 266 ms, p95 749 ms; extraction not timed per turn |
| 429s | Fixed run: 0. First run: 1 real 429, waited 56 s per Retry-After, retried on the same model, reply delivered |
| Report, CSV, PDF | Report written on close (1,071 ms); CSV 8,121 B and PDF 37,935 B, SHA-256 headers match the files |
| Legit look-alikes L1, L2 | Not flagged (qwen 0.05 each). Decisions alone scored them 0.56 and 0.67; the E2 rule let Cerebras decide |
| Live SSE during the chat | message.received, persona.reply, scam.detected, intel.extracted, case.summary, metrics.speed, ratelimit.status and network.updated all arrived live |
| Scammer network | The two test chats sharing the fake UPI formed 1 network of 2 cases |
| Dashboard in a browser | Not verified; routes return 200, but a headless page dump cannot finish while the live stream is open |

## What this means

The new regex prefilter catches far more scams than the old keyword list (recall 0.84 against 0.35), but it also flags 27 of the 43 legitimate look-alikes. It is a first-pass feature, not the final judge, and the shipped design leaves the verdict to the Cerebras flag and Decisions. On the 28 gold rows the new regex extraction is cleaner than the old one: 26 against 20 exact rows, and none of the "at" to "@" or phone-as-account errors. The later real-API run (section 6) shows the live chat path working end to end, and it found and fixed a persona repetition bug. The 122-row model eval is still not run, so there is no model-based detection accuracy yet. The regex freezes that could stall the old server for minutes now take a few milliseconds.

## Not run

- Detection arms c (Cerebras qwen-3.8-27b), d (Cerebras gpt-oss-120b), e (Decisions gpt-6-luna), f (E2 ensemble) on the 122-row split: not run yet (about 25 minutes at 5 requests/min). Therefore also not run: per-type recall of the ensemble, token speeds and costs.
- Extraction: combined persona-call intel vs a separate Cerebras extraction call: no API keys.
- Persona memory as specified (3 simulated 16-turn chats); one real chat ran instead (section 6).
- End-to-end latency over 20+ real Telegram messages; the API chat latency is in section 6.
- Rate-limit drill (10 messages in 30 s against real Cerebras).
