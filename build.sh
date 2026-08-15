#!/usr/bin/env bash
# Create/refresh the virtualenv and install dependencies.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required (https://docs.astral.sh/uv/). Install it first." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  uv venv .venv
fi

uv pip install --python .venv/bin/python -e .

mkdir -p data/uploads data/outbox
echo "build ok"
