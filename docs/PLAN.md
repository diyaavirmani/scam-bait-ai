# Build plan (1 Nov 2026, IST)

Spec: `docs/REBUILD_REPORT.md`. Audit: `docs/AUDIT.md`. Contracts: `docs/CONTRACTS.md`. User test: `docs/DEMO_SCRIPT.md`.

| Time | Who | Commits |
|---|---|---|
| 12:45-12:55 | Integrator | 1 scaffold, 2 contracts + stubs, 3 SQLite |
| 12:55-13:45 | Track A, core (`app/providers`, `app/detection`, `app/persona`, `app/extraction`, `app/orchestrator`) | 4-11 |
| 12:55-13:30 | Track B, channels (`app/channels`) | 12 |
| after 11 | Integrator | 13 case report |
| 12:55-13:50 | Track D, voice (`app/voice`) | 14-16 |
| 12:55-13:50 | Track C, dashboard (`app/events`, `app/web`) | 17-19 |
| 13:50-14:25 | Integrator | 20 tests + eval run, 21 docs |

Rules: one uvicorn worker; SQLite WAL with one writer; persona pinned to `PERSONA_MODEL`; a 429 is retried on the same model; no em dashes or emojis anywhere; every push runs `scripts/prepush_check.sh`.
