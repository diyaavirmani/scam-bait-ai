# Contracts

These are fixed before the parallel tracks start. Code lives in `app/models.py` (types), `app/runtime.py` (dependencies) and the stub modules. If a track needs a change here, the integrator makes it.

## Process model

- One uvicorn worker (`uvicorn app.main:app --workers 1`). In-process state (persona memory, per-case locks, event bus) depends on it.
- `app.runtime.Runtime` holds `settings`, `store`, `bus`, `cerebras`, `openai`. Code calls `get_runtime()`. Tests install fakes with `set_runtime()`.
- All timestamps are `datetime.now(timezone.utc).isoformat()` (`app.models.utc_now`). The UI converts them to IST.
- Inbound text is cut to `MAX_TEXT_CHARS = 4000` before any regex or model call.

## Ownership (each track edits only its own folders)

| Track | Folders | Commits |
|---|---|---|
| Integrator | `app/main.py`, `app/config.py`, `app/models.py`, `app/runtime.py`, `app/store`, `app/report`, `docs/`, root files | 1-3, 13, 20, 21 |
| A core | `app/providers`, `app/detection`, `app/persona`, `app/extraction`, `app/orchestrator`, `config/ensemble.json`, `tests/test_a_*.py`, `tests/fixtures/decisions_sample.json` | 4-11 |
| B channels | `app/channels`, `tests/test_b_*.py` | 12 |
| C dashboard | `app/events`, `app/web`, `tests/test_c_*.py` | 17-19 |
| D voice | `app/voice`, `tests/test_d_*.py` | 14-16 |

Sub-agents never run git. Each writes `.milestones/NN.txt` (git-ignored) when milestone NN is complete: the first line is a summary, and the rest lists the files in it. The integrator then runs the tests, commits and pushes.

## Database (SQLite, WAL, `synchronous=NORMAL`, `busy_timeout=5000`, one aiosqlite connection)

```sql
cases(id TEXT PK, channel TEXT, external_id TEXT, status TEXT, scam_type TEXT, verdict TEXT,
      summary TEXT, created_at TEXT, updated_at TEXT)          -- status: watching|engaged|closed
messages(id INTEGER PK, case_id TEXT, role TEXT, text TEXT, ts TEXT)   -- role: scammer|persona
intel_items(id INTEGER PK, case_id TEXT, kind TEXT, value TEXT, message_id INTEGER, first_seen TEXT,
            norm TEXT,  -- normalised value for exact network matching (app/networks.py)
            UNIQUE(case_id, kind, value))
events(id INTEGER PK AUTOINCREMENT, ts TEXT, case_id TEXT, channel TEXT, type TEXT, data TEXT)
evidence(id INTEGER PK, case_id TEXT, kind TEXT, path TEXT, sha256 TEXT, created_at TEXT)  -- kind: csv|pdf|transcript|report
seen_keys(key TEXT PK, ts TEXT)   -- idempotency (Telegram update_id, Twilio CallSid+event)
```

`external_id` is `tg:<chat_id>`, `api:<sessionId>` or `call:<CallSid>`. Case ids are `c_` plus 12 hex characters.

## Store API (`app.store.Store`, all async)

`init, close, ping`; `get_or_create_case(channel, external_id) -> dict` (returns the open case, or creates one); `new_case(channel, external_id)`; `get_case(id)`; `update_case(id, **fields)` (sets `updated_at`); `list_cases(limit)`; `add_message(case_id, role, text) -> id`; `list_messages(case_id)`; `count_messages(case_id, role)`; `add_intel(case_id, kind, value, message_id) -> bool` (False on duplicate); `list_intel(case_id)`; `network_rows()` (intel shared by 2 or more cases); `add_event(Event) -> id`; `events_after(last_id, limit) -> [Event]`; `add_evidence(case_id, kind, path, sha256)`; `list_evidence(case_id)`; `mark_seen(key) -> bool` (False if already seen).

## Events (`app.models.Event`, SSE and the `events` table)

`{id, ts (UTC ISO), case_id, channel: "telegram"|"api"|"call", type, data}`. Emit with `await app.events.emit(Event(...))`. The bus stores the event first, then fans it out.

| type | data |
|---|---|
| `message.received` | `{role: "scammer", text, message_id, turn}` |
| `persona.reply` | `{text, message_id, turn, mode, degraded, language}` |
| `scam.detected` | `{stage: "fast"\|"final", p_cerebras, p_decisions, verdict: "scam"\|"not_scam"\|"unknown", scam_type, risk, decisions_available, decided_by, recheck: bool}` (emitted for every detection result, including not_scam) |
| `intel.extracted` | `{kind, value, message_id, source}` (only new, validated items) |
| `case.summary` | `{summary, status, final: bool, report: object\|null}` |
| `transcript.partial` | `{call_sid, speaker: "caller"\|"persona", delta}` (not stored) |
| `transcript.final` | `{call_sid, speaker, text, start_ms, end_ms}` |
| `call.status` | `{call_sid, status, from_masked, detail}` |
| `metrics.speed` | `{step, provider, model, ms, queued_ms, retries, tokens_per_s, prompt_tokens, completion_tokens, cached_tokens}` |
| `ratelimit.status` | `{model, rpm_used, rpm_limit, waiting}` (not stored) |
| `task.retrying` | `{step, model, retry_in_ms, reason}` |
| `network.updated` | `{network_id, case_ids, shared: [{field, value, case_count}]}` (emitted by the bus after an `intel.extracted` changes a scammer network) |

## Providers

- `CerebrasClient.chat_json(step, model, messages, schema, schema_name, priority, max_completion_tokens, reasoning_effort, case_id=None, cache_key=None, seed=None) -> (dict, CallMetrics)`. It uses the openai SDK with `base_url=https://api.cerebras.ai/v1` and `max_retries=0`, and `response_format={"type":"json_schema","json_schema":{"name":..., "strict": true, "schema":...}}`. Schemas use `additionalProperties: false`, with no `pattern`, `format` or `minItems`, and never `tools` together with `response_format`. `prompt_cache_key` goes in `extra_body`. Speed comes from `time_info` and `usage`. Each call emits `metrics.speed`. On a 429 it waits (Retry-After or a few seconds), emits `task.retrying`, and retries the same model. A 429 that names an hourly or daily bucket raises `ProviderError("rate_limit_quota")`. 5xx or timeouts after retries raise `ProviderError("outage")`.
- Priorities: `PRIORITY_PERSONA=0`, `PRIORITY_LIVE=1` (flag, call batch), `PRIORITY_BACKGROUND=2` (report, re-check).
- `OpenAIClient.decisions(input, questions, cache_key) -> dict` (POST `/v1/decisions`, model `DECISIONS_MODEL`); `moderate(text) -> {flagged, categories}` (`omni-moderation-latest`); `responses_json(...)` (case report only, after a hard Cerebras outage).

## Detection, persona, extraction, orchestrator

- `prefilter(text) -> {score, hits}`: word-boundary, linear-time rules, never a whitelist.
- `cerebras_flag(window, case_id) -> Verdict` and `decisions_verdict(window, case_id) -> Verdict` run in `asyncio.gather` on opening messages. `window` is the last few `{role, text}` turns.
- `combine(cerebras, decisions, regex_score, cfg) -> FinalVerdict` uses the E2 rule with `config/ensemble.json` `{lo, hi, decisions_threshold}`. Any error gives `unknown`, never `not_scam`.
- `persona_turn(case_id, history, key_facts, language, mode, missing_intel) -> PersonaTurn{reply, intel[], summary, still_scam, confidence}` uses `PERSONA_MODEL` only, with `reasoning_effort: "low"` and `prompt_cache_key = case_id`.
- `reply_guard(text) -> (text, flags)`. `detect_language(text)` uses the Unicode script.
- `extract(text) -> [IntelCandidate]` and `validate([...]) -> [IntelCandidate]`. Extraction runs on scammer text only, one message at a time.
- `orchestrator.handle_message(case_id, channel, text) -> Reply{case_id, text, degraded, closed, coalesced, turn, verdict, scam_type}`.
- `orchestrator.handle_call_transcript(case_id, role, text, final) -> str | None` handles calls (`role` is `caller` or `persona`): Decisions per caller utterance and qwen batches every `CALL_BATCH_SECONDS`. It returns a nudge for `session.instructions.append`, or None. `orchestrator.end_call(case_id)` runs the final batch, closes the case and schedules the report (idempotent). The voice track emits the `transcript.*` and `call.status` events itself.
- `detection.ensemble.detect_opening(window, case_id, on_fast=None) -> FinalVerdict` runs the prefilter, then `asyncio.gather(cerebras_flag, decisions_verdict)`, and calls `on_fast` (stage fast) as soon as the Cerebras flag returns. `detection.ensemble.recheck(window, case_id) -> FinalVerdict` is the background Decisions re-check.
- A case closes at 20 scammer messages, or at 15 or more when the scammer says goodbye, or when `still_scam` is false and Decisions agrees. Closing schedules `report.write_case_report(case_id)` in the background.

## Routes

| Route | Track |
|---|---|
| `POST /api/v1/honeypot` (old contract, `x-api-key`, sessionId `^[A-Za-z0-9_-]{1,64}$`, `message.sender` must be `scammer`) | B |
| `POST /telegram/webhook` (`X-Telegram-Bot-Api-Secret-Token`, `update_id` idempotency, typing indicator) | B |
| `POST /voice/incoming`, `POST /voice/status`, `POST /voice/stream-status`, `WS /voice/stream` | D |
| `GET /api/v1/events/stream` (SSE, `Last-Event-ID` replay), `GET /api/v1/cases`, `GET /api/v1/cases/{id}`, `GET /api/v1/cases/{id}/export.csv`, `.pdf` | C |
| `GET /`, `/chats`, `/calls`, `/intel`, `/networks`, `/cases`, `/export`, `/system` (React SPA from `app/web/dist`, open, no login) and `GET /assets/{name}` | C |
| `GET /api/networks` (scammer networks, open) | C (integrator add-on) |
| `GET /health` (DB ping, model self-test result, Decisions availability) | Integrator |

Each track exposes `router` (a FastAPI `APIRouter`) from its package. `app/main.py` includes them.

## Style

No em dash (U+2014) and no emoji anywhere: code, comments, UI copy, docs, commit messages, persona replies. `tests/test_style.py` and `scripts/prepush_check.sh` enforce it.
