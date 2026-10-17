#!/usr/bin/env python
"""Tests for the external timestamp queue and the database migration path.

Calendars are faked: nothing here touches the network.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="uniteideas-ts-"))
os.environ.update(
    {
        "DB_PATH": str(TMP / "ts.db"),
        "UPLOAD_DIR": str(TMP / "u"),
        "OUTBOX_DIR": str(TMP / "o"),
        "SECRET_KEY": "x",
        "TIMESTAMP_PROVIDER": "opentimestamps",
    }
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import opentimestamps.calendar  # noqa: E402,F401  (must come before core.timestamp)
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation  # noqa: E402
from opentimestamps.core.timestamp import Timestamp  # noqa: E402

from app import timestamping as ts  # noqa: E402
from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.models import Idea, IdeaProof, User, utc_now  # noqa: E402
from app.proof import sha256_text  # noqa: E402

PASSED = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if not cond:
        print(f"FAIL  {label} {detail}")
        raise SystemExit(1)
    PASSED += 1
    print(f"ok    {label}")


class FakeCalendar:
    """Behaves like an OpenTimestamps calendar: pending first, Bitcoin later."""

    confirmed = False
    down: set[str] = set()
    fetched: list[str] = []

    def __init__(self, url: str) -> None:
        self.url = url

    def submit(self, digest, timeout=None):
        if self.url in FakeCalendar.down:
            raise OSError("connection refused")
        stamp = Timestamp(digest)
        stamp.attestations.add(PendingAttestation(self.url))
        return stamp

    def get_timestamp(self, commitment, timeout=None):
        FakeCalendar.fetched.append(self.url)
        if not FakeCalendar.confirmed:
            raise KeyError("pending")
        stamp = Timestamp(commitment)
        stamp.attestations.add(BitcoinBlockHeaderAttestation(812345))
        return stamp


def new_proof(db, label: str) -> IdeaProof:
    user = db.query(User).first()
    if user is None:
        user = User(email="a@example.com", display_name="A")
        db.add(user)
        db.flush()
    idea = Idea(owner_id=user.id, title=label, summary="summary long enough", status="published")
    db.add(idea)
    db.flush()
    proof = IdeaProof(idea_id=idea.id, content_hash=sha256_text(label), author_email_hash="x")
    ts.queue_for_timestamp(proof)
    db.add(proof)
    db.commit()
    return proof


def main() -> None:
    init_db()
    db = SessionLocal()

    # --- submit / upgrade -------------------------------------------------
    FakeCalendar.down = {ts.calendar_urls()[0]}
    raw = ts.submit(sha256_text("one"), FakeCalendar)
    check("submit survives one calendar being down", raw.startswith(b"\x00OpenTimestamps"))
    check("two calendars were recorded", raw.count(b"calendar") >= 2, str(raw)[:120])
    FakeCalendar.down = set(ts.calendar_urls())
    try:
        ts.submit(sha256_text("one"), FakeCalendar)
        check("all calendars down is an error", False)
    except ts.TimestampError:
        check("all calendars down is an error", True)
    FakeCalendar.down = set()
    try:
        ts.submit("abcd", FakeCalendar)
        check("short fingerprint rejected", False)
    except ts.TimestampError:
        check("short fingerprint rejected", True)

    # --- the queue --------------------------------------------------------
    proof = new_proof(db, "idea-a")
    check("new proof is queued", proof.anchor_status == "pending_submit" and proof.is_pending)
    result = ts.process_due(db, FakeCalendar)
    db.refresh(proof)
    check("submitted to calendars", result.submitted == 1 and proof.anchor_status == "pending_confirm")
    check("pending proof file stored", len(proof.anchor_proof) > 40)
    check("provider recorded", proof.anchor_provider == "opentimestamps")

    again = ts.process_due(db, FakeCalendar)
    check("not retried before it is due", again.submitted == 0 and again.waiting == 0 and again.confirmed == 0)

    proof.anchor_next_try_at = utc_now() - timedelta(seconds=1)
    db.commit()
    waiting = ts.process_due(db, FakeCalendar)
    db.refresh(proof)
    check("still pending when Bitcoin has not confirmed", waiting.waiting == 1 and proof.anchor_status == "pending_confirm")

    FakeCalendar.confirmed = True
    proof.anchor_next_try_at = utc_now() - timedelta(seconds=1)
    db.commit()
    done = ts.process_due(db, FakeCalendar)
    db.refresh(proof)
    check("confirmed once Bitcoin attests it", done.confirmed == 1 and proof.anchor_status == "confirmed" and proof.is_confirmed)
    check("block recorded", proof.anchor_reference == "bitcoin block 812345", proof.anchor_reference)
    check("confirmation time recorded", proof.anchored_at is not None)
    stamp = ts._deserialize(ts.decode(proof.anchor_proof)).timestamp
    check("stored proof file reads back with the block", ts.bitcoin_height(stamp) == 812345)

    from app.verification import verify as verify_proof

    seen = verify_proof(db, proof)
    stamp_check = [c for c in seen.checks if c.label == "Public timestamp"][0]
    check("verification reports a confirmed timestamp", stamp_check.state == "pass" and "812345" in stamp_check.detail)
    check("verification names a published idea", seen.idea is not None)
    hidden = db.get(Idea, proof.idea_id)
    hidden.status = "pending_review"
    db.commit()
    check("verification does not name an unpublished idea", verify_proof(db, proof).idea is None)
    hidden.status = "published"
    db.commit()
    pend = new_proof(db, "idea-pending")
    pend_check = [c for c in verify_proof(db, pend).checks if c.label == "Public timestamp"][0]
    check("verification reports a pending timestamp as waiting", pend_check.state == "wait")
    pend.anchor_status = "failed"
    db.commit()
    check("a failed timestamp makes verification fail", verify_proof(db, pend).ok is False)

    # --- failures ---------------------------------------------------------
    FakeCalendar.down = set(ts.calendar_urls())
    bad = new_proof(db, "idea-b")
    for i in range(ts.MAX_SUBMIT_ATTEMPTS):
        bad.anchor_next_try_at = utc_now() - timedelta(seconds=1)
        db.commit()
        ts.process_due(db, FakeCalendar)
        db.refresh(bad)
        if i == 0:
            check(
                "a failed attempt is retried later, not dropped",
                bad.anchor_status == "pending_submit" and bad.anchor_attempts == 1 and bad.anchor_next_try_at > utc_now().replace(tzinfo=None),
            )
    check("gives up after repeated failures", bad.anchor_status == "failed", bad.anchor_status)
    check("error is kept for the admin", "no calendar" in bad.anchor_error)
    FakeCalendar.down = set()
    ts.requeue(db, bad)
    db.refresh(bad)
    check("an admin can requeue a failed proof", bad.anchor_status == "pending_submit" and bad.anchor_attempts == 0)
    ts.process_due(db, FakeCalendar)
    db.refresh(bad)
    check("requeued proof goes through", bad.anchor_status == "pending_confirm")

    # --- a calendar cannot make us fetch arbitrary URLs --------------------
    FakeCalendar.fetched = []
    FakeCalendar.confirmed = False
    evil = Timestamp(bytes.fromhex(sha256_text("evil")))
    evil.attestations.add(PendingAttestation("https://evil.example/cal"))
    from opentimestamps.core.op import OpSHA256
    from opentimestamps.core.timestamp import DetachedTimestampFile

    blob = ts._serialize(DetachedTimestampFile(OpSHA256(), evil))
    ts.upgrade(blob, FakeCalendar)
    check("attestation URLs outside the configured calendars are never fetched", FakeCalendar.fetched == [])

    # --- switched off -----------------------------------------------------
    os.environ["TIMESTAMP_PROVIDER"] = "none"
    off = IdeaProof(idea_id="x", content_hash="0" * 64, author_email_hash="x")
    ts.queue_for_timestamp(off)
    check("provider off means no queueing", off.anchor_status == "none")
    os.environ["TIMESTAMP_PROVIDER"] = "opentimestamps"
    db.close()

    # --- migrating a database that predates the queue ---------------------
    legacy = TMP / "legacy.db"
    with sqlite3.connect(legacy) as con:
        con.executescript(
            """
            CREATE TABLE users (id VARCHAR(40) PRIMARY KEY, email VARCHAR(320), display_name VARCHAR(80),
              role VARCHAR(20), is_active BOOLEAN, onboarding_done BOOLEAN, created_at DATETIME);
            CREATE TABLE idea_proofs (id VARCHAR(40) PRIMARY KEY, idea_id VARCHAR(40), algorithm VARCHAR(30),
              content_hash VARCHAR(64), canonical_version VARCHAR(40), author_email_hash VARCHAR(64),
              anchor_provider VARCHAR(30), anchor_reference VARCHAR(200), anchored_at DATETIME, created_at DATETIME);
            CREATE TABLE votes (id INTEGER PRIMARY KEY, idea_id VARCHAR(40), user_id VARCHAR(40), created_at DATETIME);
            INSERT INTO idea_proofs VALUES ('p1','i1','sha256','%s','v1','h','local','',NULL,'2026-01-01 00:00:00');
            INSERT INTO votes (idea_id, user_id, created_at) VALUES ('i1','u1','2026-01-01 00:00:00');
            """
            % sha256_text("old")
        )
    import subprocess

    code = (
        "import os,sys;sys.path.insert(0,'.');"
        f"os.environ['DB_PATH']=r'{legacy}';"
        "from app.db import init_db, engine;init_db();"
        "from sqlalchemy import inspect;"
        "cols={c['name'] for c in inspect(engine).get_columns('idea_proofs')};"
        "print(sorted(cols & {'anchor_status','anchor_proof','anchor_error'}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1])
    )
    check("old database gains the new columns", "anchor_status" in out.stdout and out.returncode == 0, out.stderr[-300:])
    with sqlite3.connect(legacy) as con:
        row = con.execute("select anchor_status from idea_proofs").fetchone()
        ver = con.execute("select version_num from alembic_version").fetchone()
        vote_value = con.execute("select value from votes where idea_id = 'i1'").fetchone()
    check("existing proofs are queued for a timestamp", row[0] == "pending_submit")
    check("existing votes become upvotes", vote_value[0] == 1, vote_value)
    check("database is marked up to date", ver[0] == "0006", str(ver))

    fresh = sqlite3.connect(os.environ["DB_PATH"])
    check("a new database is created at the latest version", fresh.execute("select version_num from alembic_version").fetchone()[0] == "0006")

    print(f"\n{PASSED} checks passed")


if __name__ == "__main__":
    main()
