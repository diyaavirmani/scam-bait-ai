# Deploy on Render

Current deployment (1 Nov 2026): backend `https://scam-bait-ai-api.onrender.com`, dashboard `https://scam-bait-ai-dashboard.onrender.com` (redirects to the backend's `/chats`). Render builds GitHub `main` of `diyaavirmani/scam-bait-ai`.

## Service settings (backend web service)

- [ ] Repository `diyaavirmani/scam-bait-ai`, branch `main`, root directory blank, runtime Python 3. Render's GitHub app needs access to the private repo.
- [ ] Build command: `pip install -r requirements.txt`. The dashboard build is committed in `app/web/dist`, so Node is not needed on Render.
- [ ] Start command (one worker only):
  ```
  uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
  ```
- [ ] Health check path: `/health`.

## Environment variables

| Name | Required | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | required | Decisions, GPT-Live voice, moderation, report fallback |
| `CEREBRAS_API_KEY` | required | Persona (`gpt-oss-120b`), scam flag and call batches (`qwen-3.8-27b`), case report |
| `PUBLIC_BASE_URL` | for Telegram and calls | `https://scam-bait-ai-api.onrender.com` (no trailing slash). Twilio signatures, TwiML stream URLs and the Telegram webhook URL are built from it |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` | for Telegram | Bot token and webhook secret. On startup the app registers the webhook at `PUBLIC_BASE_URL/telegram/webhook` with this secret |
| `TELEGRAM_AUTO_WEBHOOK` | optional (default `1`) | `0` skips the startup webhook registration. Set it to `0` on any local or second instance, or that instance takes the bot away from Render |
| `TWILIO_AUTH_TOKEN` | for calls | Verifies `X-Twilio-Signature` |
| `TWILIO_ACCOUNT_SID`, `TWILIO_PHONE_NUMBER` | optional | Read but not used by any route |
| `API_KEY` | optional | If set, `POST /api/v1/honeypot` requires it in `x-api-key`; if empty, that route is open |
| `DEMO_MODE` | optional (default `0`) | `1` blocks eval runs |
| `CEREBRAS_RPM_OSS`, `CEREBRAS_RPM_QWEN` | optional (default `5`) | Requests per minute per Cerebras model; match your Cerebras limits |
| `PERSONA_MODEL`, `FLAG_MODEL`, `DECISIONS_MODEL`, `LIVE_MODEL`, `CALL_BATCH_SECONDS` | optional | Defaults in `.env.example` |
| `DB_PATH`, `EXPORT_DIR`, `PDF_FONT_PATH` | optional | SQLite file, evidence pack folder, Unicode PDF font |
| `PYTHON_VERSION` | Render setting | `3.12.14`, the version the app is tested with |

The dashboard has no login (commit `3584840`): anyone with the URL can read cases.

## Storage

- On the Free plan the filesystem is lost on every spin-down (after 15 idle minutes), restart and redeploy (Render docs). So are the SQLite database, case reports and evidence packs.
- To keep them, use a paid instance with a disk mounted at `/opt/render/project/src/out`, and set `DB_PATH=/opt/render/project/src/out/scambait.db` and `EXPORT_DIR=/opt/render/project/src/out/exports`.

## Webhooks

- **Telegram:** automatic on startup (see `TELEGRAM_AUTO_WEBHOOK`). Check it:
  ```bash
  set -a; source .env; set +a
  curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
  ```
- **Twilio number (set 1 Nov 2026):**
  - Voice webhook: POST `https://scam-bait-ai-api.onrender.com/voice/incoming`.
  - Call status callback: POST `https://scam-bait-ai-api.onrender.com/voice/status`.
  - The stream status callback comes from the app's TwiML.
  - `TWILIO_AUTH_TOKEN` on Render must be the account's auth token, or every call is refused with 403.

## After each deploy

- [ ] Check health; expect HTTP 200 and `"status":"ok"`:
  ```bash
  curl -s -w "\nHTTP %{http_code}\n" https://scam-bait-ai-api.onrender.com/health
  ```
- [ ] Open `https://scam-bait-ai-api.onrender.com/chats`, send one Telegram message to the bot and watch it appear.
- [ ] On the Free plan, open the backend link a minute before a demo so the service is awake.
