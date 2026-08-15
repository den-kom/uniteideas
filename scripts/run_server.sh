#!/usr/bin/env bash
# Run the UniteIdeas web server.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8100}"

exec .venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
