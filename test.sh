#!/usr/bin/env bash
# Smoke tests: exercises the full milestone-1 flow against a throwaway database.
set -euo pipefail
cd "$(dirname "$0")"

exec .venv/bin/python scripts/smoke_test.py
