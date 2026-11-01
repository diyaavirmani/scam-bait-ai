#!/usr/bin/env bash
# One-command local run: creates the venv on first use, then starts one uvicorn worker on 127.0.0.1:8000.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements.txt
fi
[ -f .env ] || { echo "Create .env from .env.example first (never commit it)."; exit 1; }
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" --workers 1
