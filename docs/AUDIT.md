# SCAM-BAIT (old) - Phase 1 audit

| | |
|---|---|
| Repo audited | `diyaavirmani/SCAM-BAIT` (private), cloned read-only to `~/Projects/scambait/scambait-old/` |
| Commit audited | `d2d89a03ae42a2010c19cacf2027a4b2cf9a7bad 2026-09-14 15:43:54 +0530 Update README.md` (matches the expected `d2d89a0`; 41 commits, single branch `main`) |
| Audit date | 2026-11-01 |
| Scratch area (never inside the old repo) | `~/Projects/scambait/audit-work/` (venv, scratch clone `run-copy/`, scripts, logs, `tests-report.md`) |
| Python used | 3.11 (repo pins 3.11.9). Unpinned deps resolved today to: langgraph 1.2.19, langchain-core 1.7.3, langchain-cerebras 0.8.2, langchain-groq 1.1.3, deepgram-sdk 4.8.1, elevenlabs 2.75.0, twilio 9.12.0, fastapi 0.109.0, sqlalchemy 2.1.6, scikit-learn 1.9.1 |

Evidence labels used throughout:

- **code**: read in the source, with file:line.
- **measured**: run locally on the scratch copy, with the command (no real API keys; dummy env values only).
- **docs**: provider documentation fetched on 2026-11-01 (links in section 5).
- **not measured**: no number is claimed.

No secret value was copied, used or tested during this audit, and none appears in this document. Secrets are referred to only by file, line and kind. One exception, disclosed in S-01: a sub-agent's masking command missed the `deploy_bot_manual.md:34` table cell, so that value appeared once in the sub-agent's own tool output.

The test sub-agent was stopped early at your request. Section 6.6 lists what was not run.

---

## 0. Summary of the most important findings

1. **Secrets are committed** in `deploy_bot_manual.md:34` (a full Supabase Postgres URL with a real password) and `:35` (a Telegram bot token), added in `58858d8` (2026-02-22) and still at HEAD. Both must be rotated and purged from history.
2. **Both LLM model IDs are dead.** `zai-glm-4.7` (Cerebras, `app/config.py:26`) was deprecated on 2026-08-17. `llama-3.1-8b-instant` (Groq, `app/config.py:30`) was shut down on 2026-08-16. So every persona reply today is a canned fallback, and every detection "LLM vibe check" fails.
3. **Detection is inverted.** A substring whitelist runs *before* the scam rules (`detection.py:113-144`). "hdfc bank", "sbi bank", "amazon", "delivery", "sent you", "credited", "ola" (inside "violation", "solar"...) all return SAFE with confidence 0.0. The graph then marks the session `isTrusted` (`graph.py:116-119`) and replies "Thank you for your message. Have a great day!". Any LLM error also returns SAFE 0.0 (`detection.py:384-386`), and with the dead models that means every message the rules and ML don't catch gets the same treatment.
4. **The voice path is dead after the greeting.** Deepgram calls `on_transcript` on its own thread, where `asyncio.get_running_loop()` raises `RuntimeError`, and the error is swallowed with `pass` (`audio_orchestrator.py:113-121`). The caller hears "Hello? Who is this?" and then silence. Voice also has no detection, extraction, DB, dashboard, callSid, Twilio signature check, or barge-in.
5. **One message can freeze a whole worker.** These patterns run synchronously on the event loop:
   - The APK-link regex (`extraction.py:108`, called at `graph.py:149`) takes 86-97 s for a single ~30-character URL without `.apk`, and the 167-character input did not finish in 330 s.
   - The jailbreak regex (`detection.py:393-411`) takes 35.2 s for a 2,880-character message.
   - The trusted-sender regex takes 13.7 s for a 10k-character message.

   All measured, in 6.3. Every session on that worker stalls, and the 35 s `wait_for` guard (`main.py:224`) cannot fire while the loop is blocked.
6. **sessionId is used unsanitised in a log path** (`logger.py:165`). `logging.FileHandler` calls `os.path.abspath`, so `..` segments are collapsed and a crafted ID appends to any writable `*.log` path (measured). Each unique session also leaks one open file descriptor for the life of the process (measured: 200 sessions = 200 FDs).
7. **Multi-worker data loss.** Locks, the semaphore and the dashboard WebSocket list are all per-process (`main.py:32-44`, `websockets.py:50`). Session state is a read-modify-write JSON blob (`graph.py:51-65`, `database.py:107-127`), and `run.py:20` defaults to 4 workers.
8. **Failures are hidden.** Every exception returns HTTP 200 `"status":"success"` (`main.py:285-303`), `/health` is hard-coded "healthy" with `"llm":"groq-connected"` (`main.py:112-123`), and most `except` blocks just log and continue.
9. **No test checks what it claims to.** `tests/test_detection.py` crashes with the reported TypeError. `tests/test_backend_v2.py` fails because an LLM error turns a cashback scam into SAFE. The others pass without asserting anything (6.2).

---

## 1. Architecture

### 1.1 Components

| Component | Files | What it is |
|---|---|---|
| HTTP API | `app/main.py` | FastAPI app: `/`, `/health`, `/api/v1/stats`, `/ws/dashboard`, `/api/v1/honeypot`; mounts the voice router at `/voice` (`main.py:62-63`). CORS `*` with credentials (`main.py:65-71`). |
| Workflow | `app/workflow/graph.py` | LangGraph `StateGraph(AgentState)` with 6 nodes: `load_session`, `detection`, `persona`, `extraction`, `not_scam`, `save_session` (`graph.py:446-545`), compiled once at import (`graph.py:557`). |
| Detection agent | `app/agents/detection.py` | Cascade: jailbreak regex, then text normalisation, then rules/whitelist, then TF-IDF + LinearSVC trained at first use on 115 in-file samples (65 scam / 50 legit, measured), then an LLM "vibe check". |
| Persona agent | `app/agents/persona.py` | "Meena, 60+", a strategy-driven prompt. Primary Cerebras `zai-glm-4.7`, secondary Groq `llama-3.1-8b-instant`, then canned replies. |
| Extraction agent | `app/agents/extraction.py` | Regex only, no LLM. Runs over the whole conversation (both sides), twice per turn. |
| Anti-hallucination filter | `app/agents/hallucination_filter.py` | Replaces digits, UPI-like, URL-like strings in persona output with bracket placeholders. |
| Timeline / summary | `app/agents/timeline.py` | Rule-based phase detection and the end-of-chat summary string, plus a confidence level. No LLM. |
| Termination + callback | `app/utils/callbacks.py` | `should_send_callback` thresholds; `send_final_callback` POSTs the intel to `_CALLBACK_URL` (the only "export"). |
| Persistence | `app/database.py` | SQLAlchemy, a single table `sessions(session_id, state_json, created_at, updated_at)`. SQLite by default, Postgres/Supabase via `DATABASE_URL`. |
| Dashboard push | `app/websockets.py` | In-process `ConnectionManager` broadcasting JSON to connected dashboards. |
| Voice | `app/voice_router.py`, `app/services/audio_orchestrator.py` | Twilio webhook returning TwiML `<Connect><Stream>`; Media Streams WebSocket: Deepgram STT, persona LLM, ElevenLabs TTS. |
| Logging | `app/utils/logger.py` | Console logger plus one file logger per session at `logs/sessions/session-{sessionId}.log`. |
| Telegram demo bot | `bot/`, `run_bot.py` | See section 1.6 (sub-agent report). |
| React dashboard | `dashboard/` | See section 1.6 (sub-agent report). |
| Evaluation | `evaluation/` | See section 1.6 (sub-agent report). |

### 1.2 Text chat flow, end to end

```mermaid
flowchart TD
  C[Client: Telegram bot / judge harness / evaluation script] -->|POST /api/v1/honeypot<br/>header x-api-key| E[main.py:158 honeypot_endpoint]
  E -->|key != API_KEY| X401[401]
  E --> BC[main.py:198 broadcast new_message<br/>to dashboards connected to THIS worker]
  BC --> SEM[main.py:209 semaphore 30 per process]
  SEM --> LCK[main.py:215 per-process asyncio.Lock per sessionId]
  LCK --> WF[main.py:224 wait_for run_honeypot_workflow, 35 s]
  WF --> LS[graph.py:32 load_session<br/>DB JSON blob, append new message,<br/>request.conversationHistory is ignored]
  LS -->|scamDetected already true| P
  LS -->|not yet| D[graph.py:73 detection on LATEST message only]
  D -->|scam| P[graph.py:125 persona<br/>extract_intelligence sync on event loop<br/>turn 1 canned + 0.5 s sleep, else LLM<br/>then hallucination filter]
  D -->|isTrusted, i.e. confidence == 0.0| NS[graph.py:282 not_scam<br/>'Thank you for your message...']
  D -->|not scam, totalMessages <= 3| P
  D -->|not scam, > 3| NS
  P --> EX[graph.py:236 extraction again, full history]
  EX --> SS[graph.py:311 save_session<br/>should_send_callback? summary + POST callback, sync<br/>then DB save]
  NS --> SS
  SS --> R[graph.py:649-737 JudgeResponse<br/>reply = last history item]
  WF -->|timeout| FB1[main.py:244 canned reply, turn=1, state NOT saved]
  WF -->|exception| FB2[main.py:262 canned reply, status success]
```

Per-turn state lives in one JSON blob per session (`sessions.state_json`). Memory between turns is that blob: `load_session` reads it, merges it into the new state, and appends the new message (`graph.py:51-65`). The persona sees the *entire* history every turn, with no truncation (`persona.py:96-99`). Any history the client sends in `request.conversationHistory` is ignored (`graph.py:598-605` uses only `request.message`).

### 1.3 Phone call flow, end to end

```mermaid
sequenceDiagram
  participant Caller
  participant Twilio
  participant API as FastAPI /voice
  participant DG as Deepgram live client (own thread)
  participant EL as ElevenLabs
  participant LLM as Persona LLM
  Caller->>Twilio: dials the number
  Twilio->>API: POST /voice/incoming (no X-Twilio-Signature check)
  API-->>Twilio: TwiML Connect/Stream url=wss://{Host header}/voice/stream
  Twilio->>API: WebSocket /voice/stream (no auth)
  API->>DG: listen.live.v("1").start(nova-2, en-US, mulaw 8 kHz), sync, on event loop
  Twilio->>API: event "connected" (ignored)
  Twilio->>API: event "start" (streamSid kept, callSid ignored)
  API->>EL: convert("Hello? Who is this?", eleven_turbo_v2, ulaw_8000), sync iterator
  EL-->>API: audio chunks
  API-->>Twilio: event "media" frames (no "mark")
  Twilio-->>Caller: greeting is heard
  loop every ~20 ms
    Twilio->>API: event "media" (base64 mulaw)
    API->>DG: send(bytes), sync, on event loop
  end
  DG-->>API: Transcript callback, runs on Deepgram's _listen_thread
  Note over API: asyncio.get_running_loop() raises RuntimeError and the except does pass.<br/>process_response is never scheduled: no LLM, no TTS, the caller hears silence.
  Twilio->>API: event "stop", cleanup, finish()
  Note over API: then WebSocketDisconnect, cleanup again (double finish)
```

### 1.4 Every route, webhook and WebSocket

| Method + path | Defined at | Auth | Who calls it | Notes |
|---|---|---|---|---|
| `GET /` | `main.py:93-110` | none | anyone / uptime pings | Static feature list; `active_sessions` = size of this worker's lock dict. |
| `GET /health` | `main.py:112-123` | none | Render health check | Hard-coded `"healthy"`, `"database":"connected"`, `"llm":"groq-connected"`; checks nothing. |
| `GET /api/v1/stats` | `main.py:129-132`, `database.py:167-212` | none | dashboard (see 1.6) | Sync DB call inside `async def` (blocks the loop); loads and parses every session JSON per call. |
| `WS /ws/dashboard` | `main.py:134-152` | none | dashboard (see 1.6) | Answers `ping` with `pong`; receives `new_message` broadcasts only (`main.py:198`). No `intelligence_found` / `scam_detected` event is ever sent, despite the docstring (`main.py:137-138`). |
| `POST /api/v1/honeypot` | `main.py:158-278` | `x-api-key` header equals `API_KEY` | Telegram bot, `evaluation/scripts/run_evaluation.py`, the hackathon judge harness | Request/response models in `models.py:15-124`. |
| `GET/POST /voice/incoming` | `voice_router.py:9-39` | none (no Twilio signature validation) | Twilio voice webhook | GET returns plain text; POST returns TwiML. |
| `WS /voice/stream` | `voice_router.py:42-48` | none | Twilio Media Streams | Hands the socket to `AudioOrchestrator`. |
| `GET /docs`, `/redoc`, `/openapi.json` | FastAPI defaults | none | anyone | Exposed in production. |

Outbound calls: `POST {_CALLBACK_URL}` at session end (`callbacks.py:229-234`); Cerebras / Groq chat completions via LangChain (`persona.py:29-51`, `detection.py:375`); Deepgram WebSocket (`audio_orchestrator.py:30-50`); ElevenLabs TTS HTTP (`audio_orchestrator.py:154-159`).

### 1.5 Agents in detail

| Agent | Entry point | Input | Output | Prompt | Model | State / memory |
|---|---|---|---|---|---|---|
| Detection | `detect_scam(text)` `detection.py:432-497`, called at `graph.py:95` | **Latest message text only** (`graph.py:92`) | `(is_scam, confidence, scam_type)` | LLM step only: `detection.py:355-367` (system: "Return ONLY 'SCAM' or 'SAFE'"; user: `Message: '{text}'`) | LLM: Cerebras `zai-glm-4.7` (temp 0.8, max_tokens 200, `persona.py:29-34`), or Groq `llama-3.1-8b-instant` when no Cerebras key. ML: TF-IDF (1-2 grams) + LinearSVC (`detection.py:294-305`) | Runs every turn until a scam is found, then the latch skips it (`graph.py:403-405`). `confidence == 0.0` sets `metadata.isTrusted` (`graph.py:116-119`), which persists in the DB. |
| Persona | `generate_persona_response(history, metadata, extracted_intelligence)` `persona.py:79-178` | Full history + intel from the first extraction pass | Reply string | System: Meena base personality `persona.py:373-408` + strategy block `persona.py:414-489`; user: transcript ("Caller:" if sender == "scammer", else "You:") + language instruction + formatting rules `persona.py:117-139` | Primary Cerebras `zai-glm-4.7`, 12 s timeout (`persona.py:153-157`); secondary Groq `llama-3.1-8b-instant`, 12 s (`persona.py:162-170`); then canned context-aware lines (`persona.py:539-604`) | No own memory: rebuilt each turn from the DB history. Turn-1 shortcut skips the LLM (`graph.py:173-187`). Regex jailbreak gate on the last `sender=="scammer"` message (`persona.py:90-93`). Output passes the leak sanitizer (`persona.py:504-519`), then the hallucination filter (`graph.py:201`). |
| Strategy selector | `determine_context_strategy` `persona.py:181-365` | History + intel | `{mode, focus, hints}`: `generic_confusion` / `active_reference` (phone, upi, link, account, verification) / `probe_for_more` | n/a | n/a | Pure function of the inputs. |
| Extraction | `extract_intelligence(history)` `extraction.py:26-55`, called twice per turn (`graph.py:149`, `graph.py:254`) | **All** messages joined with spaces, both sides (`extraction.py:29-32`) | Dict of 10 lists (`bankAccounts, upiIds, phishingLinks, phoneNumbers, emails, apkLinks, cryptoWallets, socialHandles, ifscCodes, suspiciousKeywords`) | n/a (regex) | none | Recomputed from scratch each turn; written to `state.extractedIntelligence` (`graph.py:258`). |
| Summary | `get_conversation_summary` `timeline.py:164-213`, called at `graph.py:344-360` only when the session closes | History + intel + detection confidence | One string, e.g. "Detection: SCAM (confidence: 0.95) \| Scam executed in N-phase attack: ... \| Pattern: ... \| Intelligence: 1 phone(s), ..." | n/a (keywords) | none | Saved as `fullSummaryForCallback` in the same node. It holds counts only, not the actual identifiers or a natural-language 1-2 line summary. |
| Termination | `should_send_callback` `callbacks.py:61-158` | `totalMessages`, `scamDetected`, intel categories (phone, upi, link, bank only) | bool | n/a | none | Thresholds `callbacks.py:21-26`: never before 5, hard max 20, 3+ categories ends, 2 categories ends at 6, 1 category at 12, 0 at 12. `totalMessages` counts both sides, so 20 means 10 scammer messages. |

### 1.6 Dashboard, Telegram bot, evaluation, deploy

Mapped by a sub-agent that read every file outside `app/`. The lead spot-checked the key claims against the source (App.tsx mocks and URL, AlertsView mocks, bot payload, render.yaml commands).

**Dashboard (`dashboard/`, React 18 + Vite 5 + Tailwind + Recharts).** Tabs are held in component state, with no router (`App.tsx:51`, `Layout.tsx:28-35`).

| Widget | Data source | Evidence |
|---|---|---|
| API / WS host | Hard-coded production URL `https://honey-api-wr74.onrender.com`; `VITE_API_URL` (render.yaml) is never read; the Vite proxy to `localhost:8000` is dead | `App.tsx:40-41`, `vite.config.ts:15-24` |
| "Scams Intercepted" | Mock `124`, replaced by backend `active_now` (sessions updated in the last 5 min, not scams) only when it is > 0 | `App.tsx:49`, `:54-64`; `StatsHeader.tsx:16-17` |
| "Hours Wasted", "84% Load" | Mock constants | `App.tsx:50`, `StatsHeader.tsx:26-34` |
| Scam volume chart ("LIVE TRAFFIC • LAST 24 HOURS") | Mock seed + `Math.random()` point per incoming message | `App.tsx:15-23`, `:78`; `ScamVolumeChart.tsx:21` |
| Live Intelligence card | Mock `HDFC **** 1234`, `helper@paytm`, `+91 98765 00000`, never updated because the backend never sends `intelligence_update`; hides apk/social/IFSC/keywords | `App.tsx:25-36`, `:84-88`; `IntelCard.tsx:10-17` |
| Live Feed | **Real**: WS `new_message` (scammer text only, last 10, all sessions interleaved) | `LiveFeed.tsx:11-38`, `main.py:198-204` |
| Live Monitor (call view) | Only the transcript list is real (same global feed, never voice). Phone number, call timer, waveform, "92% scam probability", "Detected intent" are hard-coded or random | `LiveMonitor.tsx:22-40`, `:74-86` |
| Threat Alerts ("Intelligence" tab) | 100% mock rows; search/filter/details not wired | `AlertsView.tsx:4-10`, `:28-36`, `:101-103` |
| System Status | 100% mock ("Healthy", CPU 12%, fake logs); never calls `/health` | `SystemStatus.tsx:10-13`, `:35-59` |
| Settings | Local state only; Save button has no handler; personas offered (grandfather/student/executive) do not exist in the backend | `SettingsPanel.tsx:6-10`, `:23-26`, `:66` |
| Export | **None** (no download/CSV/Blob anywhere; no backend export route) | grep over `dashboard/src` and `app/` |
| Auth | **None**; public static site | `render.yaml:71-79` |

WebSocket contract: the backend emits only flat `new_message` events for inbound scammer text (`main.py:198-204`). The dashboard also handles `intelligence_update` and `stats_update` (expects a `data` envelope, `App.tsx:84-93`) and declares `scam_detected` (`types.ts:39`); the backend never sends any of them. Persona replies and voice turns are never broadcast. `useWebSocket` keeps only `lastMessage`, so bursts can be dropped by React batching (`useWebSocket.ts:6,25`).

**Telegram bot (`bot/`, `run_bot.py`, python-telegram-bot 21.9).**
- Each text message makes one `POST {API_BASE_URL}/api/v1/honeypot` with header `x-api-key` and payload `{sessionId, message:{sender:"scammer", text, timestamp}, metadata:{channel:"Telegram", ...}}`, with **no** `conversationHistory` (`bot_service.py:96-121`).
- The session id is `telegram_{user_id}_{unix_ts}`, held in an in-memory dict keyed by user id. It is lost on restart, with no timeout, and `/start` does not reset it (`bot_service.py:51-66`).
- When the backend reports `closed`/`completed`, the bot drops the session, and the next message starts a new one (`bot_service.py:184-193`).
- On HTTP errors it returns a canned in-persona reply, and the scammer's message never reaches the backend (`bot_service.py:122-147`). The retry is not idempotent.
- Non-text messages (APK documents, QR photos, voice notes) are ignored (`bot_service.py:205`). In webhook mode a non-text update crashes the log line `update.message.text[:20]` (`run_bot.py:67`).
- The webhook secret is the backend API key, and its first 4 characters are logged (`run_bot.py:35,54`).
- `drop_pending_updates=True` on every start discards messages that arrive while the bot is cold (`run_bot.py:102,138`).
- `API_BASE_URL` defaults to production in one file and to localhost in another (`bot_config.py:25-26` vs `run_bot.py:170`).

**Evaluation (`evaluation/`).**
- The dataset is 18 scam-only prompts with no labels and no legitimate negatives (`dataset/reddit_scams.json`). `expand_prompts.py` makes 6 unseeded variants each (108).
- `run_evaluation.py` defines "detected" as `"Have a great day" not in reply` (`:55`). Because the backend's timeout, exception and global-handler fallbacks return HTTP 200 with persona-like text (`main.py:244-303`), crashes and timeouts count as detections.
- Results are written to a gitignored folder (`.gitignore:82-83`). No accuracy or latency number in the README/docs is backed by any artifact in the repo.

**Other scripts.**
- `run.py` defaults to **3-4 uvicorn workers** (`run.py:18-22,47`), on port 8002 (README/Vite/eval assume 8000).
- `verify_db.py` writes a fake `test-123` scam row into whatever `DATABASE_URL` points to, production included.
- `check_models.py` imports `cerebras.cloud.sdk`, which is not in requirements.
- `check_models_openai.py` uses the OpenAI SDK against `https://api.cerebras.ai/v1`. That pattern fits the rebuild rule.

**Deploy (`render.yaml`, free plan, Singapore).**
- The API runs as `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, with no `--workers` flag, so 1 worker unless Render injects `WEB_CONCURRENCY` (not verified).
- The bot runs as a web service in webhook mode, while `deploy_bot_manual.md` describes a background worker in polling mode. Running both with one token conflicts.
- The dashboard is built and served with `serve -s dashboard/dist`.
- `LLM_MODEL` in render.yaml is ignored (the model is hard-coded in `config.py:26`). The Twilio env vars are set but never read.

**Docs against code.**
- The README graph (`README.md:208`) does not match the real graph.
- Barge-in and a silence prompt are promised (`README.md:214`, `PRD3:55-58`) but not implemented.
- "Report to authorities" and the architecture image's "callback to law enforcement" are not real; the callback goes to a configurable judge URL.
- Export and dashboard auth are listed as future work (`README.md:219-220`).
- `images/architecture.png` is a 1-byte file.

---

## 2. Twilio call flow, step by step

| # | Step | file:line | What it does | Works? | Failure |
|---|---|---|---|---|---|
| 1 | Incoming call webhook | `app/voice_router.py:9-16` | `GET` answers plain text; `POST` continues | Yes | No `X-Twilio-Signature` validation (`RequestValidator` never used; the twilio package is installed but never imported); no CallSid/From captured |
| 2 | Build stream URL | `app/voice_router.py:20-28` | `wss://{Host header}/voice/stream` | Yes behind Render/ngrok | Trusts the `Host` header; no configured public URL; no `<Parameter>` to pass CallSid/From into the stream |
| 3 | Return TwiML | `app/voice_router.py:32-39` | `<Connect><Stream url=.../></Connect>` | Yes | No `statusCallback`; no fallback `<Say>` if the stream fails |
| 4 | Media Stream WebSocket opens | `app/voice_router.py:42-48` | Creates `AudioOrchestrator(websocket)` and awaits `start()` | Yes | Unauthenticated: anyone can open it and burn Deepgram/ElevenLabs/LLM credit |
| 5 | Orchestrator init | `app/services/audio_orchestrator.py:14-22` | Deepgram client, ElevenLabs client, default voice id, empty in-memory history | Yes (with keys) | Clients built per call; keys read directly with `os.getenv` |
| 6 | Accept + start STT | `audio_orchestrator.py:26-56` | `listen.live.v("1")` (deprecated since deepgram-sdk 3.4.0, still present in 4.8.1, `deepgram/clients/listen_router.py:78-87`); options nova-2, `en-US`, mulaw, 8 kHz, endpointing 500 ms, no interim results; `start()` | Starts | `start()` is a blocking sync handshake on the event loop; `language="en-US"` only (Hindi/Hinglish callers are poorly transcribed) |
| 7 | Receive loop | `audio_orchestrator.py:58-69` | `receive_text`, `json.loads`, dispatch | Yes | Any exception ends the call silently (logged only) |
| 8 | `connected` event | `audio_orchestrator.py:71-92` (no branch) | Ignored | n/a | Harmless |
| 9 | `start` event | `audio_orchestrator.py:75-82` | Stores `streamSid`; queues the greeting TTS task | Yes | `callSid`, `customParameters`, `mediaFormat` ignored; no DB row or dashboard event created |
| 10 | Greeting TTS out | `audio_orchestrator.py:150-177` | ElevenLabs `convert(..., eleven_turbo_v2, ulaw_8000)`, base64, `{"event":"media"}` frames | **Yes, the greeting is heard** | `for chunk in audio_stream` is a sync HTTP iterator on the event loop (blocks inbound media handling while it streams); no `mark` sent |
| 11 | Inbound audio | `audio_orchestrator.py:84-88` | base64 decode, `deepgram_connection.send(bytes)` | Yes | `send` is a sync WebSocket write on the event loop, every ~20 ms |
| 12 | Transcript | `audio_orchestrator.py:94-109` | Final transcripts appended to the in-memory history as `sender: "scammer"` | Runs | Runs on Deepgram's `_listen_thread` (`deepgram/clients/common/v1/abstract_sync_websocket.py:170-171`, `_emit` in `clients/listen/v1/websocket/client.py:214`) |
| 13 | Schedule reply | `audio_orchestrator.py:113-121` | `asyncio.get_running_loop().create_task(process_response(...))` | **No** | In a non-loop thread `get_running_loop()` raises `RuntimeError: no running event loop` (measured, see 6.x), and `except RuntimeError: pass` swallows it. No reply is ever generated: the caller hears the greeting, then silence |
| 14 | Persona | `audio_orchestrator.py:126-148` | Would call `generate_persona_response(history, metadata)` | Never reached | Even if reached: no detection, no extraction, no DB, no dashboard broadcast; history held only in memory |
| 15 | Reply TTS | `audio_orchestrator.py:145`, then step 10 | Same TTS path as the greeting | Never reached | No sentence-level streaming; the whole reply is synthesised before playback starts |
| 16 | Barge-in | (absent) | | **No** | No `mark` sent or handled, no `clear` sent when the caller talks over the bot, `vad_events` requested but no SpeechStarted handler |
| 17 | `mark` / `dtmf` events | (absent) | Ignored | n/a | |
| 18 | `stop` event | `audio_orchestrator.py:90-92` | `cleanup()` and `finish()` (joins the Deepgram thread, on the event loop) | Partly | Loop keeps waiting; then `WebSocketDisconnect`, and `finally: cleanup()` runs a second time (`:68-69`) |
| 19 | Persist call | (absent) | | **No** | No call record, no transcript saved, no intel, no summary; `callSid` never stored; `TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_PHONE_NUMBER` are listed (`.env.example:18-20`, `render.yaml`) but never read by any code |

---

## 3. Database schema, what is stored, export

**Schema** (`app/database.py:53-59`): one table.

| Column | Type | Notes |
|---|---|---|
| `session_id` | String, PK | Client-supplied `sessionId`, unvalidated |
| `state_json` | Text | `json.dumps(AgentState, default=str)` of the whole session |
| `created_at` | DateTime, default `now()` | |
| `updated_at` | DateTime, `onupdate=now()` | Used by `/api/v1/stats` "active in last 5 min" |

**What is inside `state_json`** (`models.py:198-209` plus extra keys): `sessionId`, `conversationHistory` (list of `{sender, text, timestamp}`, both sides), `metadata` (channel/language/locale + `isTrusted`), `scamDetected`, `extractedIntelligence` (dict of lists), `totalMessages`, `startTime`, `lastUpdated`, `agentNotes`, `sessionStatus`, `callbackSent`, and `fullSummaryForCallback` (only when closed).

**Not stored:** `scamType`. It is written at `graph.py:101`, but LangGraph drops keys that `AgentState` does not declare (measured, see 6.x), so it never reaches the DB or the API response. Also missing: per-message detection results, per-item provenance (which message an identifier came from, and when), anything from voice calls, `callSid`, caller number.

**Engine:** SQLite file `honeypot.db` relative to the CWD by default (`config.py:16-20`), or Postgres via `DATABASE_URL` (`database.py:20-41`). Sync SQLAlchemy; `get_session`/`save_session` retry `OperationalError` with `time.sleep(1, 2, 4)` (`database.py:84-105`, `:114-140`). On other errors `get_session` returns `None`, which silently starts a **new empty session** (`database.py:98-100`), and `save_session` gives up, losing the turn (`database.py:133-136`).

**Export:** there is no export endpoint and no file export in the backend. The only outbound record is the end-of-session callback (`callbacks.py:161-255`, payload `models.py:171-190`), sent only when `MODE == "prod"` and `_CALLBACK_URL` is set, once per session. For `verify_db.py` and any dashboard export, see 1.6.

---

## 4. Config and environment variables (names only)

| Name | Read at | Default if unset | Notes |
|---|---|---|---|
| `API_KEY` / `HACKATHON_API_KEY` | `config.py:11` | `"temp-key"` | Weak default: the API is open with a guessable key if unset |
| `CEREBRAS_API_KEY` | `config.py:9` | `None` (then Groq is used) | |
| `GROQ_API_KEY` | `config.py:12` | `"temp-key"` | Non-allowed provider |
| `DATABASE_URL` | `config.py:16` | SQLite | Postgres/Supabase in production |
| `DATABASE_PATH` | `config.py:19` | `honeypot.db` | |
| `MODE` | `config.py:33` | `prod` | `dev` skips the callback |
| `_CALLBACK_URL` | `callbacks.py:15` | unset (callback skipped) | Name starts with an underscore; looks like a redacted judge-platform name |
| `DEEPGRAM_API_KEY` | `audio_orchestrator.py:16` | `None` | Non-allowed provider |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | `audio_orchestrator.py:17-18` | voice id `21m00Tcm4TlvDq8ikWAM` (a public ElevenLabs premade voice id, not a secret) | Non-allowed provider |
| `PORT`, `UVICORN_WORKERS` | `run.py:22-24` | 8002, `min(2*CPU+1, 4)` | |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | **never read** | | Listed in `.env.example:18-20` and `render.yaml` only |
| `TELEGRAM_BOT_TOKEN`, `API_BASE_URL`, `HONEYPOT_API_KEY`, `LOG_LEVEL`, `RENDER_EXTERNAL_URL`, `PRODUCTION_BOT_URL` | `bot/bot_config.py:15-70`, `run_bot.py:95-175` | | Telegram bot |
| `HONEYPOT_API_URL` | `evaluation/scripts/run_evaluation.py:13` | `http://127.0.0.1:8000/api/v1/honeypot` | |

Hard-coded config: `LLM_PROVIDER="cerebras"`, `LLM_MODEL="zai-glm-4.7"`, `FALLBACK_PROVIDER="groq"`, `FALLBACK_MODEL="llama-3.1-8b-instant"` (`config.py:24-30`); concurrency `MAX_CONCURRENT=30` (`main.py:31`); request timeout 35 s (`main.py:226`); persona LLM timeouts 12 s + 12 s (`persona.py:155,166`).

---

## 5. Every model ID and external service

| Model / service | Where | Provider | Status (checked 2026-11-01) | Allowed in rebuild? |
|---|---|---|---|---|
| `zai-glm-4.7` | `config.py:26`, used `persona.py:29-34` (persona + detection fallback) | Cerebras | **Deprecated 2026-08-17**, no replacement named (docs: Cerebras deprecations page) | Provider yes, model no. Cerebras shared inference today lists `gpt-oss-120b` and `qwen-3.8-27b` |
| `llama-3.1-8b-instant` | `config.py:30`, used `persona.py:46-51` | Groq | **Shut down 2026-08-16**; "requests to deprecated model IDs will return errors" (docs: Groq deprecations) | **No** (Groq) |
| TF-IDF + LinearSVC | `detection.py:294-337` | local scikit-learn, trained at first request on 115 hard-coded samples | Works; 30 ms to train, 2.5 ms per message (measured) | **No** (local classifier, outside the OpenAI/Cerebras rule) |
| Deepgram `nova-2` live STT | `audio_orchestrator.py:30-47` | Deepgram | SDK entry `listen.live` deprecated since deepgram-sdk 3.4.0 (warning in the installed 4.8.1). Model status not checked | **No** |
| ElevenLabs `eleven_turbo_v2` TTS | `audio_orchestrator.py:154-159` | ElevenLabs | Not checked | **No** |
| Postgres on Supabase | `config.py:16`, `database.py:20-41`, `deploy_bot_manual.md:34` | Supabase | Credentials leaked | Not AI, but you listed Postgres/Supabase as not wanted. The rebuild uses SQLite |
| LangChain / LangGraph | `requirements.txt` (unpinned) | glue | Behaviour drifts with unpinned versions (see the dropped `scamType`) | Glue; the rebuild can drop it |
| Twilio | `voice_router.py` (TwiML only; SDK never imported) | telephony | | Yes (glue) |
| Telegram Bot API | `bot/`, `run_bot.py` | messaging | | Yes (glue) |
| Render | `render.yaml`, `tests/simulate_voice_webhook.py:5` (hard-coded production URL) | hosting | | n/a |

Sources: [Cerebras models](https://inference-docs.cerebras.ai/models/overview), [Cerebras deprecations](https://inference-docs.cerebras.ai/support/deprecation), [Groq deprecations](https://console.groq.com/docs/deprecations).

---

## 6. Test results and measurements

**Environment.**
- uv Python 3.11.16. `requirements.txt` and pytest are installed in `audit-work/venv`, and `bot/requirements.txt` in `audit-work/venv-bot`.
- Commands ran from the scratch clone `audit-work/run-copy` with fake keys (`audit-work/scripts/dummy_env.sh`).
- Side effect: the LLM calls reached Cerebras and Groq with the fake keys and got `401` back (Cerebras "Wrong API Key", Groq "Invalid API Key"). No real key was used.
- Logs are in `audit-work/logs/` and scripts in `audit-work/scripts/` and `audit-work/lead-checks/`.

**Stopped early at your request.** The test sub-agent was stopped before it wrote its own report. Everything below comes from its saved logs or my own runs. Not done (see 6.6): the runtime reproduction of the multi-worker race, the live-server event-loop freeze demo, and the timing of a realistic 167-character SMS.

### 6.1 Import check

Command: `audit-work/scripts/import_check.py`, run with dummy env and with no env (`logs/import-*.log`).

- Every `app/` module imports.
- `bot.bot_service` and `run_bot` fail in the main venv with `ModuleNotFoundError: telegram` (bot deps live in `bot/requirements.txt`). They are fine in the bot venv.
- `check_models.py:1` fails everywhere with `ModuleNotFoundError: No module named 'cerebras'` (the package is not in any requirements file).
- With no env, `bot/bot_config.py:17` raises `ValueError: TELEGRAM_BOT_TOKEN not found` (by design).

### 6.2 Tests

All commands were run from `run-copy` as `../venv/bin/python ...`.

| Test file | Command | Result | Why |
|---|---|---|---|
| `tests/test_detection.py` | `python -m pytest tests/test_detection.py -v -p no:cacheprovider` | **0 tests collected** | It is a script (`run_tests()`), with no `test_` functions |
| `tests/test_detection.py` | `python tests/test_detection.py` | **Crash**: `TypeError: cannot unpack non-iterable coroutine object` at `tests/test_detection.py:69`, plus `RuntimeWarning: coroutine 'detect_scam' was never awaited` | `detect_scam` is `async` (`detection.py:432`) and returns 3 values; the test calls it without `await` and unpacks 2. **Confirmed** |
| `tests/test_backend_v2.py` | `python -m pytest tests/test_backend_v2.py -v -p no:cacheprovider` | 1 failed: "async def functions are not natively supported" | pytest-asyncio is not a dependency |
| `tests/test_backend_v2.py` | same with `-o asyncio_mode=auto` (pytest-asyncio added), and `python tests/test_backend_v2.py` | **1 failed**: `AssertionError: Expected SCAM, got SAFE for 'You received a cashback of Rs 500. Scan QR to receive.'` (`tests/test_backend_v2.py:30`), log `LLM Fallback failed: Error code: 401` (`detection.py:385`) | **This is D-02 measured:** the LLM call fails, so the message is classed SAFE |
| `tests/test_phase1.py` | plain pytest | 3 failed (async unsupported) | |
| `tests/test_phase1.py` | pytest-asyncio, **no server running** | **3 "passed"**, while printing `[x] API Test Failed (Is server running?): All connection attempts failed` (emoji replaced) and `[x] WebSocket Test Failed` | The API and WS tests catch every exception and never re-raise (`tests/test_phase1.py:51-52`, `:65-66`), so they cannot fail |
| `tests/test_phase1.py` | pytest-asyncio and script, with `uvicorn app.main:app --host 127.0.0.1 --port 8002` (1 worker) | 3 passed: extraction found email/APK/crypto/handle/IFSC; `GET /api/v1/stats` returned 200 with all zeros; WS `ping` got `pong` | Genuine pass |
| `tests/test_strict_language.py` | pytest-asyncio and script | **"passed"**, but both LLMs returned 401 and the replies were canned fallbacks ("Let me find my cheque book... one moment."; the Hinglish input got the English "Is it the long number or the short one?") | No assertions; it prints PASS whatever the output |
| `tests/simulate_voice_webhook.py` | `python tests/simulate_voice_webhook.py http://127.0.0.1:8002/voice/incoming` (local; the default target at `:5` is the production Render URL and was not used) | TwiML returned for a **forged POST** with a fake CallSid/AccountSid and no signature; stream URL built from the Host header (`wss://127.0.0.1:8002/voice/stream`) | **V-04 measured** |
| `tests/test_scam.json`, `tests/test_legit.json` | `grep` | Not referenced by any file | Dead fixtures |

**Summary.** No test in the repo checks what it claims to check. One crashes (TypeError), one fails on a real bug (errors become SAFE), and the rest pass vacuously (no asserts, or swallowed exceptions). There is no test for the workflow graph, the persona with a mocked LLM, the voice path, the DB or concurrency.

### 6.3 Regex timings

All timings are measured. Each run is a separate subprocess with a hard wall-clock timeout (`scripts/regex_growth.py`, `regex_167.py`, `regex_scan.py`, `apk_compare.py`).

**Old APK pattern (`extraction.py:108`, `re.IGNORECASE`).** Time roughly doubles with every extra character after the scheme.

| Input | Chars after `http(s)://` | `findall` time |
|---|---|---|
| `http://` + `a`×k | 13 / 17 / 21 / 23 / 25 / 27 / 28 / 29 | 0.0012 s / 0.019 s / 0.29 s / 1.18 s / 4.5 s / 18.4 s / 41.9 s / **86.0 s** |
| Realistic phishing URL without `.apk` (`https://sbi-kyc-update.verify-account.secure-login...`) | 20 / 24 / 27 / 29 / 31 | 0.18 s / 2.7 s / 23.5 s / **97.0 s** / **> 120 s (killed)** |
| `http://` + 160×`a` (167 chars total) | 160 | **Did not finish within 330 s** (killed) |

Your earlier figure of "281 s on 167 characters" was not reproduced exactly; this 167-character input is worse. An ordinary phishing link with about 30 characters after the scheme and no `.apk` already costs about 100 s per pass. Extraction runs twice per turn, over the whole history, on the event loop (X-02).

**Suggested pattern `https?://[^\s<>"']+?\.apk\b` (with IGNORECASE).**
- Every input above takes ≤ 0.00004 s (167 chars: 0.000016 s).
- It is **not** linear for adversarial input. Repeated `http://` with no `.apk` took 0.175 s at 10k chars, 4.58 s at 50k and **17.6 s at 100k** (quadratic). The joined history can reach about 18 × 10k chars.
- Alternatives measured at 100k chars: a bounded `{1,2048}?` took 0.74 s; **split on whitespace and then test each token took 0.0026 s**. The token approach is recommended.
- Behaviour on 28 inputs: it differs from the old pattern on 4, all in the new pattern's favour. `.../app.apkx` and `.../x.apk_backup`: old returned a truncated `...apk`, new returns nothing. `.../a_b~c.apk` and `.../{x}.apk`: old missed them, new catches them.
- Without IGNORECASE it also misses uppercase `.APK` (2 more cases), so keep the flag.

**Other regexes.** These run synchronously inside `async def detect_scam` (`detection.py:445`, `:458`) and the persona (`persona.py:91`), so they also freeze the event loop:

| Function | Pattern | Worst measured |
|---|---|---|
| `is_trusted_message` (`detection.py:69-78`, `:96-102`) | `txn.*of.*debited` / `credited` | 4k chars 0.92 s; 8k 7.2 s; **10k 13.7 s** (10k is the allowed maximum, `models.py:27`) |
| `is_jailbreak_attempt` (`detection.py:393-411`, same list `persona.py:60-77`) | `you.*are.*now.*(dan\|evil\|unrestricted)` | 960 chars 0.41 s; 1,920 chars 6.7 s; **2,880 chars 35.2 s** |
| `is_jailbreak_attempt` | "ignore..." input | 10k chars 0.05 s |
| `extract_emails` (`extraction.py:102`) | | 10k chars 0.25 s |

### 6.4 Detection and extraction behaviour

Measured with `audit-work/lead-checks/quick_behaviour.py`, run as `PYTHONPATH=../run-copy GROQ_API_KEY=dummy CEREBRAS_API_KEY= ../venv/bin/python -B quick_behaviour.py`. All of it is local, with no LLM reached for these inputs.

| Input | `rule_based_score` | `detect_scam` result |
|---|---|---|
| "Dear customer, your HDFC Bank account will be suspended today. Share the OTP to keep it active." | 0.0, **whitelisted** ("hdfc bank") | `(False, 0.0, 'NONE')`, i.e. trusted and polite exit |
| "I sent you Rs 5000 by mistake on GPay, please return it to my UPI immediately." | 0.0, **whitelisted** ("sent you") | `(False, 0.0, 'NONE')` |
| "Your Amazon delivery is on hold. Pay Rs 49 customs fee to release the parcel." | 0.0, **whitelisted** ("amazon", "delivery") | `(False, 0.0, 'NONE')` |
| "Traffic violation challan pending. Pay now to avoid court case." | 0.0, **whitelisted** ("ola" inside "violation") | `(False, 0.0, 'NONE')` |
| "Hi sir, how is your husband doing?" | 0.8, matched `band` (husband), `sir` | `(True, 0.95, 'UNKNOWN')`: false positive |
| "I was walking on the footpath near the bank." | 0.8, matched `otp` (footpath), `bank` | `(True, 0.95, 'UNKNOWN')`: false positive |

| Extraction input | Output (non-empty fields) |
|---|---|
| "Call me at 5pm about the refund" | `upiIds: ['me@5pm']` (false UPI) |
| "Pay to 9876543210 now" | `bankAccounts: ['9876543210']` **and** `phoneNumbers: ['9876543210']`: one number fills two termination categories |
| Two messages "My number is 98765" / "43210 is the rest" | `bankAccounts: ['9876543210']`, `phoneNumbers: ['98765 43210', '9876543210']` (joined across messages; duplicate in two formats) |
| "Visit sbi-kyc-update.in to verify" | `{}`: a phishing domain without a path is missed |

### 6.5 Lead's other runtime checks (measured)

All run from `~/Projects/scambait/audit-work/lead-checks/` against the scratch clone with dummy env values.

| Check | Command | Result |
|---|---|---|
| Log-path traversal through `sessionId` | inline Python in a `mktemp -d` dir replicating `logger.py:165-171` (`SESSIONS_DIR / f"session-{sid}.log"` then `logging.FileHandler`) | `sid="/../../escaped"` wrote `logs/escaped.log` (outside `logs/sessions/`) **without** any pre-existing `session-` directory, because `FileHandler` calls `os.path.abspath`. `sid="a/b"` gave `FileNotFoundError`; a 300-char sid gave `OSError: [Errno 63] File name too long`. Both crash the request into the canned fallback, and the scammer's message is lost |
| FD leak from per-session loggers | `PYTHONPATH=../run-copy GROQ_API_KEY=dummy ../venv/bin/python -B -c "...get_session_logger(f'sess-{i}') for 200 ids; count /dev/fd"` | open FDs **4 before, 204 after 200 sessions**. Handlers are never closed, so a Linux container with the common 1024 soft limit starts failing after about 1,000 sessions per worker |
| LangGraph drops undeclared state keys | `../venv/bin/python -I langgraph_extra_keys.py` (langgraph 1.2.19) | A node writes `state["scamType"]`; the next node sees only the declared keys; final state has no `scamType`. `scamType survived? : False` |
| Deepgram callback thread vs `get_running_loop` | `../venv/bin/python -I -c "...threading.Thread(target=lambda: asyncio.get_running_loop()) inside asyncio.run..."` | `RuntimeError: no running event loop`, exactly what `audio_orchestrator.py:114` hits on Deepgram's `_listen_thread` |
| Local step timings | `../venv/bin/python -B timing_local_steps.py` | ML train (first request) **30.4 ms**; `ml_classify` **2.45 ms**/msg; `rule_based_score` **0.018 ms**; `extract_intelligence` over 18 ordinary messages **32.9 ms**; `validate_persona_output` **0.018 ms** |
| Persona language heuristic | `python3 -c "ord('’'), ord('\u2705')"` | Right single quote = 8217 and emoji = 9989, both `> 2300`, so `persona.py:108` labels an English message containing `I’m` or an emoji as `HINDI (Devanagari)` and instructs "DO NOT use English words" (code + measured ordinals; no LLM run) |

### 6.6 Not done (stopped at your request)

- **Multi-worker race.** The "only ~8 of 24 messages stored" figure was **not reproduced** at runtime. C-01 rests on code evidence only.
- **Live-server freeze.** I did not send a slow-regex message to a running server while timing `/health`. The freeze claim (X-02, R-01, R-02) rests on the measured regex times plus the code path that runs them synchronously on the event loop.
- **Realistic SMS timing.** The 167-character SMS "Dear customer, your SBI KYC has expired. Update now at https://onlinesbi-kyc-update.in/customer/login/verify ..." was still running when the agent was stopped. No time was recorded.
- **Extraction coverage.** Only 4 examples were run, not 10 or more. There is no coverage for card numbers, IFSC in context, Hinglish or shortened links.
- **Model latency.** No latency was measured for any model call: the old model IDs are dead and no real keys were used.

---

## 7. Issues

"Confirmed" means the item was on your earlier-audit list and is confirmed here. "New" means it was found in this audit. "Rejected" means it was on your list and is not confirmed. Evidence type is in brackets: [code], [measured], [docs].

| ID | Severity | Area | file:line | Evidence | Status | Suggested fix |
|---|---|---|---|---|---|---|
| S-01 | critical | Secrets | `deploy_bot_manual.md:34`, `:35` (added `58858d8`, 2026-02-22; still at HEAD `d2d89a0`) | [code] Masked inspection: line 34 is a `postgresql://user:password@...supabase...` URL whose password is not a placeholder; line 35 is a value shaped like a Telegram bot token (46 chars). A full-history scan (41 revisions, gsk_/csk-/sk-/AC.../Telegram/postgres-with-password patterns) found no other credentials. Repo is private (`gh repo view`: PRIVATE). During this audit the line-34 value appeared once in a sub-agent's tool output because a mask missed the table cell; it was not copied or used anywhere | Confirmed | Rotate now: Supabase DB password reset; BotFather `/revoke`. Purge from history (`git filter-repo`) and any forks/clones. Add secret scanning (gitleaks pre-commit + GitHub secret scanning). Docs carry placeholders only. Bot should not receive `DATABASE_URL` (`render.yaml:52-56`) |
| S-02 | low | Secrets / info | `deployment_guide.md:13` | [code] The password is the placeholder `[YOUR-PASSWORD]`, but the host is the real Supabase pooler/project host | New | Replace with a placeholder host |
| M-01 | critical | Models | `app/config.py:26` (`zai-glm-4.7`), `:30` (`llama-3.1-8b-instant`), used at `persona.py:29-51`, `detection.py:353-375` | [docs] Cerebras deprecated `zai-glm-4.7` on 2026-08-17; Groq shut down `llama-3.1-8b-instant` on 2026-08-16 ("requests to deprecated model IDs will return errors"). Consequence [code]: every persona call falls to canned lines (`persona.py:176-178`), and every detection LLM check returns SAFE 0.0 (`detection.py:384-386`), see D-02 | Confirmed | Cerebras `gpt-oss-120b` / `qwen-3.8-27b` via the OpenAI SDK with `base_url=https://api.cerebras.ai/v1`; model IDs from env; startup self-test that lists models and fails loudly |
| D-01 | critical | Detection | `detection.py:32-39` (LEGIT_SENDERS), `:113-116`, `:142-144`, `:461-463`; `graph.py:114-119`, `:426-429` | [code] The substring whitelist runs before the scam rules. Any text containing `ola` (violation, solar, console, hola), `uber`, `amazon`, `delivery`, `sent you`, `paid you`, `credited`, `debited`, `hdfc bank`, `sbi bank`, `order id`... returns `(False, 0.0, "NONE")`. `confidence == 0.0` then sets `metadata.isTrusted=True`, which persists, and routes to `not_scam` ("Thank you for your message. Have a great day!"). Only link+KYC/RBI or electricity patterns override it. Bank- and Amazon-impersonation, "money sent to you by mistake" and parcel-delivery scams, the most common Indian scams, are let through. [measured] 6.4: the HDFC, "sent you", Amazon-delivery and "violation" messages all returned `(False, 0.0, 'NONE')` | Confirmed | Remove the substring whitelist. Trust only verified sender metadata (e.g. DLT sender IDs such as `VM-HDFCBK`), never message text. Classify with an LLM over the conversation context |
| D-02 | critical | Detection / errors | `detection.py:384-386`; `graph.py:116-119` | [code] Any LLM exception returns `(False, 0.0)`, which is treated exactly like a trusted sender: the session is marked trusted and the scammer gets the polite exit. With M-01 this happens on every message the rules and ML don't catch. [measured] 6.2: `tests/test_backend_v2.py` cashback scam returned SAFE after `401` from the LLM | Confirmed | Fail toward engagement: on error return `UNKNOWN`, keep the persona engaged, mark the turn `degraded`, alert |
| D-03 | high | Detection | `detection.py:42-58`, `:150-157`, `:465-469` | [code] The comment says "at least 15% keyword match (4-5 keywords)", but a single substring keyword gives `rule_score` 0.4 ≥ 0.15, so SCAM at confidence 0.95. Keywords like `sir`, `bhai`, `bank`, `video`, `band` (husband, bandwidth), `otp` (footpath), `upi` (cupid), `block` (blockchain) flag ordinary chat. [measured] 6.4: "Hi sir, how is your husband doing?" and "walking on the footpath near the bank" both returned SCAM 0.95 | New | Word-boundary matching only as a feature; final verdict from a calibrated LLM classifier with a labelled eval set |
| D-04 | medium | Detection | `detection.py:376-382` | [code] Verdict parsed as `"SCAM" in result`, so "NOT A SCAM" counts as SCAM; free-text output, no schema | New | Structured output (JSON schema enum) or the Decisions API |
| D-05 | medium | Detection | `graph.py:92` | [code] Only the latest message is classified, with no conversation context; slow-boil scams depend on the 3-message probe | New | Classify over the last N turns |
| X-01 | critical | Extraction / DoS | `extraction.py:107-110` | [code] `(?:[a-zA-Z]\|[0-9]\|[$-_@.&+]\|...)+` overlaps (the `$-_` range already contains digits and A-Z) inside a repeated group, so backtracking is exponential when no `.apk` follows. [measured] 6.3: time doubles per character; 29 URL characters took 86-97 s; the 167-character input did not finish in 330 s (the earlier "281 s" figure was not reproduced exactly; this input is worse) | Confirmed | Split on whitespace and test each token (0.0026 s at 100k chars); the suggested `https?://[^\s<>"']+?\.apk\b` fixes this input but is quadratic on repeated `http://` (17.6 s at 100k, 6.3); also cap input length; run extraction off the event loop with a timeout |
| X-02 | critical | Extraction / concurrency | `graph.py:125`, `:149` (sync call inside `async def persona_node`), `:254` (second full pass) | [code] The regex extraction runs synchronously on the event loop, twice per turn, over the entire conversation. A slow pattern blocks every session, `/health` and every WebSocket on that worker, and `asyncio.wait_for(..., 35)` (`main.py:224`) cannot fire while the loop is blocked. Regex times [measured] in 6.3; the live-server freeze itself was not demonstrated (6.6) | New | Extract incrementally per new scammer message, in a worker thread or process with a hard timeout, using linear regexes |
| R-01 | high | Detection / DoS | `detection.py:69-78` (`txn.*of.*debited`, `txn.*of.*credited`), `:96-102`, called at `:113`, `:458` | [measured] 6.3: 10k-character message (the allowed maximum, `models.py:27`) took 13.7 s; runs synchronously inside `async def detect_scam`, so the worker's event loop is blocked | New | Remove `.*` chains; cap length before matching; run checks off the loop |
| R-02 | critical | Detection / DoS | `detection.py:393-411` (`you.*are.*now.*(dan\|evil\|unrestricted)` and other `.*` chains), called at `:445`; same list `persona.py:60-77`, called at `:91` | [measured] 6.3: a 2,880-character message took 35.2 s (1,920 chars: 6.7 s), well under the 10k limit; on the event loop for every unconfirmed message | New | Replace the regex blocklist with a classifier signal (#1 in section 9); if kept, use linear checks on a length-capped string |
| X-03 | high | Extraction quality | `extraction.py:9`, `:14`, `:29-32`, `:59`, `:65`; `callbacks.py:44-49`, `:133` | [code] `\s+at\s+` → `@` turns "call me at 5pm" into UPI `me@5pm`. A 10-digit phone also matches `bankAccounts` (`\d{9,18}`), so one number fills 2 of the 4 termination categories and ends the chat at 6 total messages. Digits are joined across message boundaries. Persona lines are included. The UPI regex also captures every email. [measured] 6.4: `me@5pm`; one number in both phone and bank lists; digits joined across two messages; `sbi-kyc-update.in` missed | New | Per-message, per-sender extraction; typed validators (UPI handle list, phone vs account disambiguation, Luhn for cards); LLM extraction for names, IDs, claimed bank; dedupe with provenance |
| X-04 | medium | Extraction coverage | `extraction.py:83` (links need a `/path`), `:108` (APK only as URL), `:58-61`, `:79`, `:85`, `:98`, `:104`, `:110`, `:123`, `:131`, `:137` (`list(set(...))[:N]`) | [code] `sbi-kyc.in` with no path is missed; `KYC_update.apk` without URL is missed. No names, employee IDs, claimed bank, card numbers or amounts. Caps keep an arbitrary hash-order subset (nondeterministic across processes) | New | Add the missing fields; keep all items (no silent truncation); deterministic order with first-seen timestamps |
| P-01 | high | Security | `app/utils/logger.py:165-171` | [measured] `sessionId="/../../escaped"` wrote `logs/escaped.log` outside `logs/sessions/`, because `FileHandler` applies `os.path.abspath`. Any writable `*.log` path can be appended to with partly attacker-controlled text. IDs with `/` or > 255 chars crash the turn (`FileNotFoundError` / `OSError`), losing the message | Confirmed | Validate `sessionId` (`^[A-Za-z0-9_-]{1,64}$`) at the API; never build paths from IDs; structured logs to stdout only |
| P-02 | high | Reliability | `app/utils/logger.py:156-182` | [measured] One open FD per unique session, never closed: 200 sessions = 200 extra FDs. A 1024-FD container fails after about 1k sessions per worker (sockets and DB included) | New | No per-session file handlers; session ID as a log field |
| C-01 | high | Concurrency / data | `main.py:32-44`; `websockets.py:50`; `graph.py:51-65`; `database.py:107-127`; `run.py:18-22,47` | [code] Per-process `asyncio.Lock`s and semaphore; the whole session is a JSON blob read, modified and written with no row lock or version check (lost update); `run.py` starts 3-4 workers; SQLite with several writer processes. Dashboard sockets only receive broadcasts from their own worker. Runtime "8 of 24" figure **not reproduced** (6.6) | Confirmed (mechanism) | Single writer per session: append-only message rows + `BEGIN IMMEDIATE`/row lock or optimistic version column; one process for the demo or a shared pub/sub for dashboard events |
| C-02 | high | Memory / data loss | `main.py:224-255`; `graph.py:598-605` | [code] On the 35 s timeout the graph is cancelled before `save_session`, so the scammer's message never enters history and the response claims `turn=1`. `request.conversationHistory` is ignored, so the client cannot repair it | New | Persist the inbound message first (before any model call); build replies from stored history; return the true turn |
| C-03 | high | Memory / data loss | `database.py:98-100`, `:133-136`, `:140` | [code] Any non-`OperationalError` in `get_session` returns `None`, which `load_session` treats as a brand-new session (the persona forgets everything). Save failures log and drop the turn | New | Fail the turn loudly (internal error metric) and keep an in-character reply; never silently reset a session |
| V-01 | critical | Voice | `audio_orchestrator.py:113-121` | [code + measured] Deepgram's sync client emits transcripts on its `_listen_thread` (`deepgram/clients/common/v1/abstract_sync_websocket.py:170-171`); `asyncio.get_running_loop()` there raises `RuntimeError: no running event loop` (measured), and `except RuntimeError: pass` swallows it. No reply is ever produced after the greeting | Confirmed | Capture the loop in `start()` and use `asyncio.run_coroutine_threadsafe`, or (rebuild) an async/WebSocket client or GPT-Live |
| V-02 | high | Voice | `audio_orchestrator.py:150-177` (comment at `:174`) | [code] No `mark` sent or handled, no `clear` on caller speech, no SpeechStarted handler: no barge-in | Confirmed | Send `mark` after each utterance; on caller speech send `{"event":"clear"}` and cancel TTS |
| V-03 | high | Voice | `audio_orchestrator.py:1-11`, `:75-77`, `:126-148` | [code] Voice imports only the persona: no detection, extraction, DB write, dashboard event or summary; `callSid` (and caller number) never stored; history only in memory | Confirmed | Voice turns go through the same session pipeline as text, keyed by `callSid` |
| V-04 | high | Voice / security | `voice_router.py:9-39`, `:42-48` | [code] No `X-Twilio-Signature` validation (the twilio package is never imported); `/voice/stream` accepts any WebSocket, so strangers can burn STT/TTS/LLM credit | Confirmed | `twilio.request_validator.RequestValidator` on the webhook; a one-time token in the `<Stream>` URL or `<Parameter>` checked on `start` |
| V-05 | low | Voice / config | `.env.example:18-20`, `render.yaml:24-29` | [code] `TWILIO_ACCOUNT_SID/AUTH_TOKEN/PHONE_NUMBER` are never read anywhere | Confirmed | Read and use them (signature validation, outbound calls) or remove |
| V-06 | medium | Voice / latency | `audio_orchestrator.py:50`, `:88`, `:154-172`, `:183` | [code] Deepgram `start()`/`send()`/`finish()` and the ElevenLabs chunk iterator are blocking sync calls on the event loop; inbound media is not processed while TTS streams | New | Fully async clients; TTS streamed by sentence on a separate task |
| V-07 | medium | Voice | `audio_orchestrator.py:39` | [code] STT `language="en-US"` only; Hindi/Hinglish callers are poorly transcribed | New | Multilingual STT / speech-to-speech model |
| V-08 | low | Voice | `audio_orchestrator.py:68-69`, `:90-92` | [code] `stop` runs `cleanup()`, the loop continues, then disconnect runs `cleanup()` again (double `finish()`); `connected`/`mark`/`dtmf` are ignored | New | Break the loop on `stop`; idempotent cleanup |
| V-09 | low | Voice | `voice_router.py:20-28` | [code] Stream URL built from the request `Host` header | New | Configured `PUBLIC_BASE_URL` |
| A-01 | high | Dashboard | `App.tsx:15-36`, `:49-50`, `:59`, `:78`; `AlertsView.tsx:4-10`; `LiveMonitor.tsx:22-40`, `:74-86`; `SystemStatus.tsx:10-59`; `StatsHeader.tsx:26-34` | [code, spot-checked] Mock and random data presented as live, including a permanent fake UPI/bank/phone in "Live Intelligence"; the "Scams Intercepted" counter shows `active_now` | Confirmed | Real endpoints only; empty states; delete all mocks |
| A-02 | high | Dashboard / API | `main.py:198-204` vs `App.tsx:84-93`, `types.ts:39` | [code] Backend sends only flat `new_message` (inbound text, before processing). `intelligence_update` / `stats_update` / `scam_detected` are never emitted; persona replies and voice turns never broadcast; the dashboard expects a `data` envelope for the others | New | One typed event schema `{type, sessionId, data, ts}` emitted after each pipeline stage, for text and voice |
| A-03 | high | Security / PII | `main.py:65-71`, `:129-152` | [code] `/ws/dashboard` and `/api/v1/stats` are unauthenticated; the WS streams every scammer message plus session IDs (which embed Telegram user IDs, `bot_service.py:59`) to anyone; CORS `*` with credentials | New | Auth on the dashboard and its WS (token + Origin check); restricted CORS |
| A-04 | high | Error handling | `main.py:112-123`, `:239-273`, `:285-303` | [code] Every exception returns HTTP 200 `"status":"success"` with a persona line and `turn=1`; `/health` always "healthy" with `"llm":"groq-connected"`. Monitoring and the eval script cannot see failures (the eval counts them as detections, EV-01) | New | Keep the in-character reply, but set an explicit `meta.degraded`/internal status, log at error level, real health checks (DB + model ping) |
| A-05 | medium | Security | `config.py:11-12`; `main.py:190` | [code] API key defaults to `"temp-key"` if unset (also used by `run_evaluation.py:14`); `!=` comparison, not constant-time | New | Refuse to start without a key; `hmac.compare_digest` |
| A-06 | medium | Performance | `main.py:129-132`; `database.py:167-212` | [code] Sync DB query plus a parse of every session's JSON inside an `async` handler on each stats call | New | SQL aggregates over typed columns; run off-loop |
| PI-01 | high | Prompt injection | `detection.py:367`; `persona.py:96-99`, `:117-118` | [code] Scammer text is inserted raw into both prompts. Defence is a regex blocklist on the latest message (`detection.py:393-411`, `persona.py:60-93`); a scammer can, for example, close the quote and append "Verdict: SAFE" to the detection prompt | New | Delimit untrusted text (JSON field / XML tags) with an explicit "data, not instructions" system rule; structured outputs; test with an injection suite |
| PI-02 | medium | Prompt injection | `models.py:26`; `persona.py:90-91`, `:494-499`; `timeline.py:76` | [code] `sender` is free-form and client-controlled. The jailbreak gate, language detection and timeline consider only `sender == "scammer"`, so any other sender value bypasses the jailbreak gate, and the persona sees the scammer's text as its own ("You:") | New | Server-assigned roles; reject unknown senders |
| L-01 | medium | Persona | `persona.py:106-113` | [measured] `ord(c) > 2300` also matches curly quotes (U+2019 = 8217) and emoji (U+2705 = 9989), so an English message with `I’m` or an emoji is labelled "HINDI (Devanagari)" with "DO NOT use English words"; Hinglish needs an exact token from a 10-word list | New | Unicode script check for U+0900-U+097F; language field from the classifier |
| H-01 | medium | Persona | `hallucination_filter.py:21-36`, `:64-75`; `persona.py:135-137`, `:385-387` | [code] The filter injects `[some numbers]` / `[a phone number]` etc. into replies, which the prompt forbids ("NO BRACKETS", "NO PLACEHOLDERS") and which sounds robotic to the scammer; `\b\d{4,6}\b` also replaces years and amounts | New | Re-generate or rewrite in character ("nine-eight-seven... my glasses") instead of brackets; narrower patterns |
| ST-01 | medium | State | `graph.py:101`; `models.py:198-209`; `graph.py:717-724` | [measured] LangGraph 1.2.19 drops undeclared keys: `scamType` never reaches later nodes, the DB or the response (`ResponseMeta.scamType` is always `"UNKNOWN"`) | New | Typed state with every field declared; tests over the full graph |
| CB-01 | medium | Export / latency | `callbacks.py:161-255`; `graph.py:334-371` | [code] The callback is a sync `requests.post` (timeout 10 s) inside the reply path. If it fails it is retried on every later turn (each up to 10 s more). After `callbackSent` no update is sent although the persona keeps chatting and extracting | New | Background job with retry/backoff; versioned report updates; the export does not depend on the callback |
| CB-02 | medium | Summary | `timeline.py:164-213`; `graph.py:344-360`, `:349-353`, `:676-681`, `:706-711` | [code] The "summary" is counts only (e.g. "1 phone(s)"), produced only at close, with no identifiers or narrative; confidence is recovered by string-splitting `agentNotes` | New | Incremental 1-2 line LLM summary per turn (Cerebras), stored with the intel; numeric fields stored as numbers |
| T-01 | medium | Termination | `callbacks.py:21-26`, `:44-49`, `:79`, `:109-151`; `graph.py:792-797` | [code] Counts both sides (hard max 20 total = about 10 scammer messages); noisy categories (X-03) end chats at 6 messages; thresholds in `visualize_graph` (8/12/18) disagree with the code (6/12/20) | New | Count scammer turns; 15-20 target; categories from validated intel only |
| F-01 | low | Persona / latency | `graph.py:173-187` | [code] Turn-1 canned reply (e.g. "I don't understand message.") plus an artificial `asyncio.sleep(0.5)` | New | A real fast model reply on turn 1 (Cerebras is fast enough) |
| F-02 | medium | Latency / resilience | `persona.py:21-58`, `:153-170`; `detection.py:353`, `:375` | [code] A new LangChain client per call (fresh connection/TLS each time); persona tries primary (12 s) then secondary (12 s) sequentially; the detection LLM call has no timeout at all | New | One pooled async client; hedged or parallel fallback; per-call timeouts |
| LOG-01 | medium | PII | `main.py:194`; `logger.py:226`, `:250`; `graph.py:162`, `:207`, `:262`, `:594`; `extraction.py:50-53` (`print`); `callbacks.py:194`, `:223`; `run_bot.py:50`, `:54`, `:67` | [code] Raw message text, extracted identifiers and request headers go to stdout and to per-session log files that are never rotated; the bot logs 4 characters of its secret | New | Structured logs with redaction; no secrets or prefixes; retention policy |
| TS-01 | low | Evidence quality | `graph.py:213`, `:328`; `bot_service.py:106` | [code] `datetime.now().isoformat() + "Z"` labels local time as UTC (wrong by 5:30 h on an IST machine) | New | `datetime.now(timezone.utc)` everywhere |
| BOT-01 | medium | Telegram bot | `bot_service.py:51-66`, `:122-147`, `:205`; `run_bot.py:35`, `:54`, `:67`, `:102`, `:138` | [code] In-memory sessions lost on restart; non-idempotent retry; non-text messages (APK files, QR photos, voice notes) ignored and crash the webhook log line; pending updates dropped on every start; webhook secret = API key, partly logged | New | Persist chat to session; idempotency key = Telegram `update_id`; store media as evidence; separate webhook secret |
| EV-01 | medium | Evaluation | `evaluation/scripts/run_evaluation.py:55`; `dataset/reddit_scams.json` | [code] "Detected" means the reply lacks "Have a great day", so crashes and timeouts count as detections; scam-only dataset (no negatives); results gitignored; unseeded variants | New | Labelled set with legitimate negatives; assert on `meta`; save results; seeded |
| DEP-01 | medium | Build | `requirements.txt` (langgraph, langchain-*, twilio, websockets, openai, elevenlabs unpinned); `dashboard` lockfile gitignored (`.gitignore:64`) | [code + measured] Behaviour drifts with installs (ST-01 depends on the langgraph version; Deepgram `listen.live` deprecated) | New | Pinned lockfiles (uv/pip-tools, package-lock) |
| DEP-02 | low | Data hygiene | `verify_db.py:9` | [code] Writes a fake `test-123` scam session into whatever DB is configured, production included | New | Test fixtures only against a temp DB |
| DC-01 | low | Dead code | `persona.py:502` (unreachable), `:24` (unused ChatGroq import); `models.py:162-168` (`ScamType` unused); `database.py:142-165` (`get_all_sessions`, `delete_session` unused); `logger.py:229-232` (`log_response` unused); `audio_orchestrator.py:6` (`websockets` unused); `detection.py:393-411` duplicates `persona.py:60-77`; `graph.py:752-797` stale | [code] grep shows zero call sites | New | Delete |
| DEP-03 | low | Deprecations | `main.py:73`, `:82` (`on_event`); `database.py:174` (`utcnow`); `graph.py:591`, `callbacks.py:231` (`.dict()`); `audio_orchestrator.py:30` (`listen.live`) | [code] | New | Lifespan handler, `model_dump()`, timezone-aware datetimes |
| DOC-01 | low | Docs | `README.md:208`, `:214`, `:23`; `images/architecture.png` (1 byte); `PRD3:55-58` | [code] The documented graph, barge-in, silence prompt and "report to authorities" are not implemented; broken link; conflicting ports, repo names and team names | New | Docs generated from the real system |
| PROV-01 | high | Rule compliance | Groq: `config.py:29-30`, `persona.py:41-51`. Deepgram + ElevenLabs: `audio_orchestrator.py:8-9`, `:16-18`, `:30-47`, `:154-159`. TF-IDF+SVM: `detection.py:20-22`, `:294-337`. Postgres/Supabase: `config.py:16`, `database.py:20-41` | [code] All outside the OpenAI/Cerebras-only rule (Postgres/Supabase is your stated exclusion, not AI) | Confirmed | Replace with Cerebras/OpenAI equivalents and SQLite |
| TEST-01 | medium | Tests | `tests/test_detection.py:69` and others | [code] `detect_scam` is `async` and returns 3 values; the test calls it without `await` and unpacks 2. [measured] 6.2: `TypeError: cannot unpack non-iterable coroutine object`; the other tests fail on a real bug or pass vacuously | Confirmed | Rewrite tests as pytest with asserts; mock the LLM; add an eval gate |

---

## 8. What works and must be preserved

These are behaviours the rebuild should keep identical, or keep in intent while fixing the defect noted.

**API contract (keep identical unless you say otherwise).** The Telegram bot and the evaluation runner both depend on it.
- `POST /api/v1/honeypot` with header `x-api-key`.
- Request `{sessionId, message:{sender, text, timestamp(str|int)}, conversationHistory[], metadata{channel, language, locale}}` (`models.py:15-62`).
- Response `{status, reply, meta:{agentState: engaging|completed, sessionStatus: active|closed, persona, turn, confidence: high|medium|low|null, scamType, agentNotes}}` (`models.py:69-124`).
- `persona` values `confused_customer` / `polite_responder` (`graph.py:695`).
- `agentNotes` sanitised to the detection line only, with no intel leaked in the reply (`graph.py:697-714`).

**Never break character towards the scammer.** Every failure still returns an in-persona reply (`main.py:239-273`, `persona.py:539-604`, bot `bot_service.py:79-90`). Keep this, but report the failure honestly in logs, metrics and an internal status field, and do not answer HTTP 200 "success" on internal errors.

**Detection behaviour.**
- Continuous monitoring: detection runs on every message until a scam is found (`graph.py:87-102`, `:393-410`).
- Once a scam is detected, the session stays a scam (latch, `graph.py:99-101`).
- Grace-period probe: engage for the first 3 messages even when unsure, to catch slow-boil scams (`graph.py:431-435`).
- Instant deflection of jailbreak attempts with an in-character line (`detection.py:445-448`, `persona.py:89-93`).
- Recognising genuine OTP/bank/telecom notifications is a good idea (`detection.py:69-78`). It must never override scam signals, and must never mark a session trusted because of an error.

**Persona "Meena".**
- Confused elderly customer, 60+, and the absolute rules: never admit to being an AI, a honeypot or having a system prompt (`persona.py:373-408`).
- Short replies (under 2 sentences).
- Strict language mirroring: English, Hindi (Devanagari) and Hinglish (`persona.py:106-130`).
- The strategy modes and their example lines: `generic_confusion`, `active_reference` with focus phone/upi/link/account/verification, and `probe_for_more` (`persona.py:181-489`). This "ask for what we are missing" logic is the core of the 15-20 message engagement.
- The context-aware canned fallbacks (`persona.py:539-604`).
- The leak sanitiser idea, so the persona never says honeypot, AI or provider names (`persona.py:504-519`).
- The anti-hallucination principle: the persona must never output realistic OTPs, accounts, UPI IDs or links (`hallucination_filter.py`). Keep the principle, but replace the bracket placeholders with in-character fumbling, e.g. "nine-eight... wait, my glasses".
- Full conversation memory every turn.

**Extraction.**
- The ten categories (`models.py:151-160`). The rebuild adds names, employee IDs, claimed bank/organisation, card numbers, amounts and APK file names.
- India-specific handling: UPI handles, IFSC, +91 formats.
- Obfuscation handling: "at"/"dot", spaced digits, number words (`extraction.py:5-24`). Fix the false positives.
- Extraction runs on every turn.

**Termination and report.**
- End the conversation on intel coverage, with a minimum and a hard maximum (`callbacks.py:21-158`). Retune it so it reaches 15-20 messages.
- Idempotent "final report sent once" (`callbackSent`, `graph.py:334-371`).
- The final payload shape `{sessionId, scamDetected, totalMessagesExchanged, extractedIntelligence, agentNotes}` (`models.py:171-190`) as the basis of the export.

**Taxonomy and summary features.**
- Scam types `DIGITAL_ARREST, UPI_SCAM, JOB_SCAM, SEXTORTION, LOTTERY_SCAM, UNKNOWN` with their keyword hints (`models.py:162-168`, `detection.py:60-66`).
- Timeline phases (urgency, authority, fear, credential request, payment redirection, impersonation) and pattern names (`timeline.py:45-161`).

**Concurrency intent.** Turns of one session are processed strictly in order (`main.py:215-217`), and many sessions run at once. Keep this, but make it hold across workers and processes.

**Voice basics that work.**
- `<Connect><Stream>` TwiML.
- mulaw 8 kHz in both directions.
- base64 `media` frames carrying `streamSid`.
- The greeting "Hello? Who is this?" on the `start` event (`voice_router.py:32-38`, `audio_orchestrator.py:75-82`, `:150-172`). The greeting is heard today.

**Telegram bot.**
- Webhook with secret-token check.
- In-persona `/start` and `/help`, and the typing indicator.
- In-persona fallback when the backend is down.
- Closing the session when the backend reports completion.

**Dashboard designs.** Wire them to real data: sidebar layout, connection pill, chat-bubble live feed, typed intel card, live-call monitor, alerts table with confidence bars, settings ideas (persona, sensitivity, kill-switch). `types.ts` `Intelligence` mirrors the backend model field for field.

**Evaluation skeleton.** India-specific and adversarial seed prompts, variant generator, concurrent runner with per-category breakdown and p95 latency. It needs labels and legitimate negatives.

**Pattern for the new rule.** `check_models_openai.py` already calls Cerebras through the OpenAI SDK (`base_url=https://api.cerebras.ai/v1`).

---

## 9. Cerebras speed opportunities

These are the places where a reply waits on something slow or sequential. "Cerebras" means one call to `gpt-oss-120b` or `qwen-3.8-27b` on Cerebras through the OpenAI SDK. No model latency was measured (the models are dead and no keys were used). Code constants such as timeouts are labelled as constants, not measurements.

| # | Step | file:line | Why it is slow | Cerebras or parallel replacement | Latency today |
|---|---|---|---|---|---|
| 1 | Detection LLM "vibe check" | `detection.py:344-386` (call at `:375`) | Model network call, run before the persona, **no timeout**, new LangChain client per call (`persona.py:21-39`) | One Cerebras structured-output call over the last N turns returning verdict, scam type, confidence, language and injection flag. Run it **in parallel** with persona generation, with a pooled client | not measured |
| 2 | TF-IDF + SVM classifier | `detection.py:294-337`, `:474` | Local model, trained lazily on the first request; threadpool hop | Removed; replaced by #1 (also outside the AI rule) | measured: 30.4 ms first request, 2.45 ms per message |
| 3 | Rule, trusted and jailbreak regexes | `detection.py:96-163`, `:393-411`, `:445-458`; `persona.py:74-77`, `:91` | Sync on the event loop; backtracking on long input | Linear token checks; the jailbreak/injection judgement goes into the #1 Cerebras call | measured: 0.018 ms normal; **13.7 s** (10k chars) and **35.2 s** (2.9k chars) worst case |
| 4 | Persona primary LLM | `persona.py:153-157` | Model network call, 12 s timeout, new client per call | Cerebras `gpt-oss-120b` (low reasoning effort) **streamed**, pooled client | not measured |
| 5 | Persona secondary retry | `persona.py:162-170` | Starts only after the primary fails or times out, then another 12 s | Hedged request: fire `qwen-3.8-27b` if the first call has no first token within a short deadline; take whichever answers first | not measured; up to 24 s by timeout constants |
| 6 | Extraction, twice per turn | `graph.py:149`, `:254`; `extraction.py:26-55` | Sync regex over the **entire** history, on the event loop, duplicated | Incremental extraction of the new scammer message only (linear regex) **plus** a Cerebras structured extraction for names, employee IDs, claimed bank, amounts, in parallel with the persona call; merge with provenance | measured: 32.9 ms for 18 ordinary messages; **86-97 s** for one ~30-char URL without `.apk` |
| 7 | Turn-1 artificial delay | `graph.py:185-187` | `asyncio.sleep(0.5)` before a canned reply | Remove; a real Cerebras reply on turn 1 | 500 ms (code constant) |
| 8 | Sequential pipeline | `graph.py:501-530` | Detection, then persona, then extraction, then save, all one after another per message | `asyncio.gather(classify, extract, persona)` per message; persist the inbound message first; summary and broadcast after the reply | not measured |
| 9 | End-of-chat summary | `graph.py:344-360`; `timeline.py:164-213` | Done only at close; counts only | Incremental Cerebras 1-2 line summary each turn, run **after** the reply is sent | not measured |
| 10 | Final callback | `callbacks.py:229-234`; `graph.py:367` | Sync `requests.post` inside the reply path; 10 s timeout; repeated every turn after a failure | Background task with retry; never in the reply path | not measured; up to 10 s per turn (constant) |
| 11 | DB load/save | `graph.py:48-51`, `:380-381`; `database.py:71-140` | `SessionManager()` per node reruns `create_all`; sync SQLAlchemy; retry sleeps 1 + 2 + 4 s | One engine; append-only message rows; write the inbound message while the models run | not measured |
| 12 | Dashboard broadcast | `main.py:198-204` | Awaited, client by client, before any processing starts | Fire-and-forget event queue | not measured |
| 13 | Stats endpoint | `main.py:129-132`; `database.py:167-212` | Sync full-table scan and JSON parse in an async handler | SQL aggregates on typed columns | not measured |
| 14 | Voice: STT turn detection | `audio_orchestrator.py:44-46` | Final transcripts only, after 500 ms of silence | GPT-Live-1 full-duplex, or streaming STT with interim results; Cerebras detection on partial transcripts | not measured; 500 ms endpointing (constant) |
| 15 | Voice: TTS | `audio_orchestrator.py:154-172` | Whole reply synthesised through a sync iterator on the event loop; no sentence streaming | Stream Cerebras tokens into sentence chunks into streaming TTS (OpenAI), or GPT-Live speech-to-speech | not measured |
| 16 | Voice: STT I/O | `audio_orchestrator.py:50`, `:88`, `:183` | Sync `start`/`send`/`finish` on the event loop for every 20 ms frame | Async client (or GPT-Live) | not measured |
| 17 | Voice: no pipeline at all | `audio_orchestrator.py:126-148` | Detection, extraction and DB missing | Run #1 and #6 on each caller utterance in parallel with the reply | n/a |
| 18 | Telegram bot call | `bot_service.py:122-136` | 40 s timeout, then a 2 s sleep, then a retry | Fast backend, plus an idempotency key so retries are safe | not measured |

**Where Cerebras speed matters most on the day:** #1 + #4 + #6 run as one parallel fan-out per message, and the voice loop (#14-#15) hands each final transcript to Cerebras and streams the reply sentence by sentence.

---

## 10. Open questions

1. **Leaked credentials.**
   - Have the Supabase DB password (`deploy_bot_manual.md:34`) and the Telegram bot token (`:35`) been rotated?
   - Does that Supabase database hold real conversation data that must be migrated or deleted?
   - Purging history means rewriting `main` of the old repo and force-pushing. You asked for the old repo to stay read-only, so I have not done this. Do you want me to do it later, or will you?
2. **Voice stack under the OpenAI/Cerebras rule.**
   - (a) OpenAI **GPT-Live-1** speech-to-speech on Twilio Media Streams (full-duplex, handles barge-in itself, can delegate to our backend). Detection and extraction would run in parallel on its transcripts via Cerebras.
   - (b) An OpenAI streaming STT, then Cerebras persona text, then OpenAI TTS pipeline, with our own `mark`/`clear` barge-in.
   - Which do you want? Does your OpenAI project have GPT-Live access? Twilio and OpenAI docs say a project needs it enabled.
3. **OpenAI Decisions API.** Third-party reports say access was gated (403 "Decision API is not enabled for this user" on 2026-10-02), and I found no official OpenAI docs page in my search. Does your key have it? If not, the fallback is a Cerebras structured-output classifier.
4. **API compatibility.**
   - Must `POST /api/v1/honeypot` and its exact request/response JSON stay identical (any judge harness or bot depending on it)?
   - Is the end-of-session callback to `_CALLBACK_URL` still needed, or is "export" now only the DB plus the file export?
5. **"15-20 messages".** Counted as scammer messages, or total? The old code counts both sides (hard max 20 total, so about 10 scammer messages; `callbacks.py:21`).
6. **Languages.** Must calls and chats handle Hindi and Hinglish on the day? This decides the STT language settings and the eval set.
7. **Channels for the demo.** Telegram bot, SMS/WhatsApp via Twilio, live Twilio calls: which are in scope? Is a Twilio number available (and which country; Indian numbers need a regulatory bundle), and is an ngrok (or other public URL) account ready?
8. **Export for authorities.** Which format (CSV, JSON, PDF case file) and which fields? Is there a target such as the cybercrime.gov.in (NCRP) complaint fields? Should scammer identifiers be shown in full in the export but masked on the dashboard?
9. **Dashboard.** Keep React/Vite, or a simpler server-rendered page? Is basic auth acceptable for the demo?
10. **Accuracy measurement.** Can I build the labelled set from the 115 in-code training samples, the 18 eval prompts and their variants, plus new legitimate Indian SMS (OTP, bank alerts, delivery, Hinglish chat)? Or do you have real anonymised transcripts?
11. **Cerebras models.** Shared inference lists `gpt-oss-120b` and `qwen-3.8-27b`. Do you have a paid key or event credits (rate limits differ)? Is reasoning-style `gpt-oss-120b` acceptable for the persona (with low reasoning effort), with `qwen-3.8-27b` as the fast second model?
12. **Repo for the rebuild.** A new repo under `diyaavirmani`, or a new branch of SCAM-BAIT?
