#!/usr/bin/env python
"""Check that this machine can reach the OpenTimestamps calendar servers.

Sends a random fingerprint (not an idea) to each calendar and reports the result.
Run on the server that hosts UniteIdeas:  .venv/bin/python scripts/check_timestamp.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import timestamping as ts  # noqa: E402


def main() -> int:
    digest = os.urandom(32).hex()
    ok = 0
    for url in ts.calendar_urls():
        try:
            raw = ts._default_calendar(url).submit(bytes.fromhex(digest), timeout=ts.CALENDAR_TIMEOUT)
            print(f"ok    {url}  ({len(list(raw.all_attestations()))} attestation)")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {url}  {exc}")
    print(f"\n{ok} of {len(ts.calendar_urls())} calendars accepted the test fingerprint")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
