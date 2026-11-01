# Changes: every docs/AUDIT.md issue and where it is fixed

Old code: `diyaavirmani/SCAM-BAIT` at `d2d89a0` (read-only reference). New code: this repository. "Tested" names the test that covers the fix; "not verified live" means it was built and tested against fakes but never run against the real provider (no API keys were available during the build on 1 Nov 2026).

| ID | Severity | Fix | Where | Tested / status |
|---|---|---|---|---|
| S-01 | critical | The new build uses no old credential. Every push runs a secret scan. Rotating the leaked Supabase password and Telegram token and purging the old history is the owner's job | `scripts/prepush_check.sh` | Rotation not confirmed (user action) |
| S-02 | low | Old deployment docs not carried over | n/a | Done |
| M-01 | critical | Model IDs from env (`PERSONA_MODEL=gpt-oss-120b`, `FLAG_MODEL=qwen-3.8-27b`); startup lists the models and fails loudly if a pinned one is missing | `app/config.py`, `app/providers/cerebras.py` (`self_test`), `app/main.py` (`start_runtime`) | `test_audit_regressions::test_M01`, `test_smoke`; not verified live |
| D-01 | critical | No text whitelist and no trusted-session state; word-boundary features only | `app/detection/prefilter.py` | `test_D01`, `test_a1_prefilter` |
| D-02 | critical | Any detector error gives `unknown` and the persona keeps engaging; nothing becomes safe because of an error | `app/detection/ensemble.py` (`combine`), `app/orchestrator` | `test_D02`, `test_a2_orchestrator` (unknown keeps engaging, error kinds) |
| D-03 | high | Word-boundary matches; "sir", "husband", "footpath" no longer trigger | `app/detection/prefilter.py` | `test_D03` |
| D-04 | medium | Strict JSON schemas for the Cerebras flag; typed probabilities from Decisions | `app/detection/flag.py`, `app/detection/decisions.py` | `test_a1_flag`, `test_a1_decisions` |
| D-05 | medium | Detection reads the last 4 turns, not one message | `app/orchestrator` (window), `app/detection/ensemble.py` (`detect_opening`) | `test_a2_orchestrator` |
| X-01 | critical | URLs and APKs: split on whitespace, then simple checks per token (the suggested lazy regex is quadratic, so it is not used) | `app/extraction` | `test_X01_R01_R02`; timings in `docs/EVAL_RESULTS.md` |
| X-02 | critical | Extraction runs per new scammer message, off the event loop, with a timeout | `app/orchestrator` (`asyncio.to_thread`) | `test_a2_orchestrator` (2,000-char paste) |
| R-01 | high | Trusted-sender regex removed; prefilter is linear | `app/detection/prefilter.py` | `test_X01_R01_R02` |
| R-02 | critical | Jailbreak `.*` chains removed; the injection judgement sits in the model prompts and the reply guard | `app/detection/prefilter.py`, `app/persona/guard.py` | `test_X01_R01_R02` |
| X-03 | high | No at-to-@ rewrite, no joining across messages, scammer text only, a phone is never also a bank account, UPI handles are letters only | `app/extraction` | `test_X03`, `test_a2_extraction`, `test_demo_script_flow` |
| X-04 | medium | Bare phishing domains, APK file names, Luhn-checked cards, names, amounts; dedupe instead of truncation | `app/extraction` | `test_X04`, `test_a2_extraction` |
| P-01 | high | `sessionId` must match `^[A-Za-z0-9_-]{1,64}$` (400 otherwise) and is never used in a path | `app/models.py`, `app/channels/honeypot.py` | `test_P01_P02`, `test_b_honeypot` |
| P-02 | high | No per-session log files; one stdout handler | `app/logs.py` | `test_P01_P02`, `test_logs` |
| C-01 | high | One uvicorn worker, one aiosqlite connection as the only writer, per-case lock | `app/store`, `scripts/run.sh`, `app/orchestrator` | `test_store` (50 concurrent writes, 50 stored), `test_C01` |
| C-02 | high | The inbound message is stored before any model call | `app/orchestrator` | `test_a2_orchestrator` (persist first) |
| C-03 | high | Persona memory is rebuilt from the store when missing; a store error fails the turn instead of resetting the session | `app/persona/memory.py` | `test_a2_orchestrator` (restart rebuild) |
| V-01 | critical | GPT-Live bridge with async I/O only, no SDK threads | `app/voice/bridge.py` | `test_d_bridge` (fake GPT-Live server); not verified live |
| V-02 | high | Numbered Twilio `mark` after each audio chunk, `clear` when the caller speaks over pending marks | `app/voice/bridge.py` | `test_d_bridge`; barge-in timing needs a real call |
| V-03 | high | Calls use the same pipeline: case per callSid, Decisions per caller utterance, qwen batches, intel, dashboard, report | `app/voice`, `app/orchestrator` (`handle_call_transcript`, `end_call`) | `test_call_pipeline` |
| V-04 | high | `X-Twilio-Signature` validated on every webhook; single-use stream token bound to the callSid | `app/voice/__init__.py`, `app/voice/state.py` | `test_d_webhook` |
| V-05 | low | Twilio auth token is used for signature validation | `app/voice/__init__.py` | `test_d_webhook` |
| V-06 | medium | No blocking calls on the event loop in the voice path | `app/voice/bridge.py` | `test_d_bridge` |
| V-07 | medium | GPT-Live handles speech in and out (no fixed en-US STT) | `app/voice/live_protocol.py` | Not verified live |
| V-08 | low | Call end runs once whether stop, socket close or the status callback fires | `app/voice/state.py` (`finish_call`), `app/orchestrator` (`end_call`) | `test_d_bridge`, `test_call_pipeline` |
| V-09 | low | Every URL comes from `PUBLIC_BASE_URL`, never the Host header | `app/voice/__init__.py` | `test_d_webhook` |
| A-01 | high | Dashboard renders only API and SSE data, with real empty states | `dashboard/src` (built to `app/web/dist`) | `test_c_web` (no sample values in the dashboard source, no banned characters in the build) |
| A-02 | high | One typed event schema for text and voice, all event types emitted | `app/models.py` (`Event`), `app/events` | `test_c_events` |
| A-03 | high | Reopened on purpose for the demo: the dashboard, its API, the SSE stream and the exports are open with no login, so anyone with the URL can read cases. No CORS is enabled. Add a login back before real use | `app/web` | `test_c_web` (open access) |
| A-04 | high | `/health` runs real checks (503 when degraded); a fallback reply sets `status: degraded` and `meta.degraded`; no global 200 handler | `app/main.py`, `app/channels/honeypot.py` | `test_smoke`, `test_b_honeypot` |
| A-05 | medium | No `temp-key` default: `API_KEY` is optional and, when set, compared with `hmac.compare_digest`; an empty `API_KEY` leaves the honeypot route open (demo setting). The Telegram secret uses the same constant-time check | `app/config.py`, `app/channels` | `test_A05`, `test_b_honeypot` (503 when unset) |
| A-06 | medium | No full-table JSON parsing; case lists come from SQL | `app/web/api.py`, `app/store` | `test_c_web` |
| PI-01 | high | Scammer text goes into every prompt as a JSON DATA block with an explicit "data, not instructions" rule | `app/detection/flag.py`, `app/persona/persona.py`, `app/report` | `test_a1_flag`, `test_a2_persona` |
| PI-02 | medium | Roles are assigned by the server; `message.sender` must be `scammer`; the store rejects any other role | `app/channels/honeypot.py`, `app/store` | `test_b_honeypot`, `test_store` |
| L-01 | medium | Language from the Devanagari range (U+0900 to U+097F) and Roman-Hindi markers | `app/persona/language.py` | `test_L01` |
| H-01 | medium | In-character fumbling instead of bracket placeholders | `app/persona/guard.py` | `test_H01` |
| ST-01 | medium | Typed models and a typed case state; `scam_type` is stored on the case and returned in the API | `app/models.py`, `app/orchestrator`, `app/store` | `test_a2_orchestrator`, `test_b_honeypot` |
| CB-01 | medium | The case report is a background job, never on the reply path | `app/report` | `test_report` |
| CB-02 | medium | Rolling 1 to 2 line summary from every persona turn, plus a final report naming the identifiers | `app/persona/persona.py`, `app/report` | `test_report`, `test_demo_script_flow` |
| T-01 | medium | Termination counts scammer messages (close at 20, or at 15+ on a goodbye) and uses validated intel only | `app/orchestrator` | `test_a2_orchestrator`, `test_demo_script_flow` |
| F-01 | low | No canned turn-1 reply and no sleep | `app/orchestrator` | `test_a2_orchestrator` |
| F-02 | medium | One pooled client per provider; same-model retry; timeouts on every call | `app/providers` | `test_a1_providers` |
| LOG-01 | medium | Logs go to stdout through a redacting filter (identifiers, digits, secrets) | `app/logs.py` | `test_logs` |
| TS-01 | low | `datetime.now(timezone.utc)` everywhere; the UI shows IST | `app/models.py` (`utc_now`) | `test_TS01` |
| BOT-01 | medium | Chat-to-case mapping persisted in SQLite, `update_id` idempotency, media turned into case notes, a separate webhook secret | `app/channels/telegram.py` | `test_b_telegram`; media files are not downloaded as evidence yet |
| EV-01 | medium | The eval uses the frozen real split with 43 legitimate look-alikes, checks verdicts explicitly and saves results | `scripts/eval_detection.py` | Not run: no API keys at build time |
| DEP-01 | medium | Fully pinned `requirements.txt` | `requirements.txt` | `test_DEP01` |
| DEP-02 | low | No script writes fake rows into a configured database | n/a | Done |
| DC-01 | low | Rebuilt from scratch; dead modules not carried over | n/a | Done |
| DEP-03 | low | Lifespan handler, pydantic v2 APIs, timezone-aware datetimes | `app/main.py`, `app/models.py` | Done |
| DOC-01 | low | README and CONTRACTS describe the system as built | `README.md`, `docs/CONTRACTS.md` | Done |
| PROV-01 | high | Only OpenAI and Cerebras for AI; Groq, Deepgram, ElevenLabs, LangChain, LangGraph, scikit-learn and Postgres removed | `requirements.txt`, `app/providers` | `test_PROV01` |
| TEST-01 | medium | 257 pytest tests with real asserts; models, Telegram and Twilio mocked | `tests/` | `pytest -q` |
