"""External timestamps for idea fingerprints, and the queue that obtains them.

What is timestamped is only the idea's SHA-256 fingerprint (32 bytes), never its text.
The fingerprint is sent to public OpenTimestamps calendar servers, which batch many
fingerprints into one and write that batch into a Bitcoin transaction. Anyone can later
check the resulting `.ots` file against the Bitcoin chain without trusting UniteIdeas.

Lifecycle of IdeaProof.anchor_status
    none             no external timestamp wanted (provider switched off)
    pending_submit   waiting to be sent to the calendars
    pending_confirm  calendars hold it; waiting for the Bitcoin block (hours)
    confirmed        a Bitcoin block attests it; `anchor_reference` says which
    failed           gave up after repeated errors; an admin can requeue it

The receipt UniteIdeas issues at submission time is instant and does not depend on any of
this. The external timestamp is the part we do not control, which is why it is the part
that proves anything. A future UniteIdeas log can be added as another provider that is
anchored the same way.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import IdeaProof, utc_now

logger = logging.getLogger("uniteideas.timestamping")

PROVIDER = "opentimestamps"
DEFAULT_CALENDARS = (
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
)
CALENDAR_TIMEOUT = 15
CONFIRM_RETRY = timedelta(minutes=30)
GIVE_UP_AFTER = timedelta(days=5)
MAX_SUBMIT_ATTEMPTS = 8
BATCH = 10


def enabled() -> bool:
    return os.getenv("TIMESTAMP_PROVIDER", PROVIDER).strip().lower() == PROVIDER


def calendar_urls() -> list[str]:
    raw = os.getenv("OTS_CALENDARS", "").strip()
    urls = [u.strip().rstrip("/") for u in raw.split(",") if u.strip()] or list(DEFAULT_CALENDARS)
    return urls


def poll_seconds() -> int:
    return max(5, int(os.getenv("TIMESTAMP_POLL_SECONDS", "30")))


class TimestampError(Exception):
    pass


def _ots() -> dict[str, Any]:
    """Import the library lazily. It must import `calendar` before `core.timestamp`."""
    try:
        from opentimestamps.calendar import RemoteCalendar  # noqa: I001
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
        from opentimestamps.core.op import OpSHA256
        from opentimestamps.core.serialize import (
            StreamDeserializationContext,
            StreamSerializationContext,
        )
        from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise TimestampError(f"opentimestamps library is not installed ({exc})") from exc
    return locals()


CalendarFactory = Callable[[str], Any]


def _default_calendar(url: str) -> Any:
    return _ots()["RemoteCalendar"](url, user_agent="uniteideas-timestamper")


def _serialize(detached: Any) -> bytes:
    lib = _ots()
    buf = io.BytesIO()
    detached.serialize(lib["StreamSerializationContext"](buf))
    return buf.getvalue()


def _deserialize(raw: bytes) -> Any:
    lib = _ots()
    return lib["DetachedTimestampFile"].deserialize(
        lib["StreamDeserializationContext"](io.BytesIO(raw))
    )


def _nodes(stamp: Any):
    yield stamp
    for child in stamp.ops.values():
        yield from _nodes(child)


def bitcoin_height(stamp: Any) -> int | None:
    """Lowest Bitcoin block height attesting this timestamp, if any."""
    lib = _ots()
    heights = [
        att.height
        for _, att in stamp.all_attestations()
        if isinstance(att, lib["BitcoinBlockHeaderAttestation"])
    ]
    return min(heights) if heights else None


def submit(content_hash: str, calendar_factory: CalendarFactory | None = None) -> bytes:
    """Send a fingerprint to the calendars. Returns a pending `.ots` file."""
    lib = _ots()
    factory = calendar_factory or _default_calendar
    digest = bytes.fromhex(content_hash)
    if len(digest) != 32:
        raise TimestampError("fingerprint must be a SHA-256 hash")
    root = lib["Timestamp"](digest)
    errors: list[str] = []
    accepted = 0
    for url in calendar_urls():
        try:
            root.merge(factory(url).submit(digest, timeout=CALENDAR_TIMEOUT))
            accepted += 1
        except Exception as exc:  # noqa: BLE001 — any one calendar may be down
            errors.append(f"{urlparse(url).hostname}: {str(exc)[:80]}")
    if not accepted:
        raise TimestampError("no calendar accepted the fingerprint (" + "; ".join(errors) + ")")
    detached = lib["DetachedTimestampFile"](lib["OpSHA256"](), root)
    return _serialize(detached)


def _allowed_calendar(uri: str) -> bool:
    """Pending attestations name a URL. Only follow ones we already trust (no SSRF)."""
    host = urlparse(uri).hostname
    return bool(host) and any(host == urlparse(u).hostname for u in calendar_urls())


def upgrade(raw: bytes, calendar_factory: CalendarFactory | None = None) -> tuple[bytes, int | None]:
    """Ask the calendars whether a pending proof now reaches Bitcoin.

    Returns (possibly updated `.ots` bytes, Bitcoin block height or None).
    """
    lib = _ots()
    factory = calendar_factory or _default_calendar
    detached = _deserialize(raw)
    stamp = detached.timestamp
    for node in list(_nodes(stamp)):
        for att in list(node.attestations):
            if not isinstance(att, lib["PendingAttestation"]) or not _allowed_calendar(att.uri):
                continue
            try:
                node.merge(factory(att.uri).get_timestamp(node.msg, timeout=CALENDAR_TIMEOUT))
            except Exception as exc:  # noqa: BLE001 — not confirmed yet is the normal case
                logger.debug("calendar %s not ready: %s", att.uri, exc)
    return _serialize(detached), bitcoin_height(stamp)


def encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def queue_for_timestamp(proof: IdeaProof) -> None:
    """Mark a new proof as wanting an external timestamp (or not, if switched off)."""
    if enabled():
        proof.anchor_provider = PROVIDER
        proof.anchor_status = "pending_submit"
        proof.anchor_next_try_at = utc_now()
    else:
        proof.anchor_status = "none"


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(2**attempts, 120))


@dataclass
class RunResult:
    submitted: int = 0
    confirmed: int = 0
    failed: int = 0
    waiting: int = 0


def process_due(db: Session, calendar_factory: CalendarFactory | None = None) -> RunResult:
    """Do whatever work is due. Safe to call repeatedly; each call is bounded."""
    result = RunResult()
    now = utc_now()
    due = db.scalars(
        select(IdeaProof)
        .where(
            IdeaProof.anchor_status.in_(("pending_submit", "pending_confirm")),
            or_(IdeaProof.anchor_next_try_at.is_(None), IdeaProof.anchor_next_try_at <= now),
        )
        .order_by(IdeaProof.created_at)
        .limit(BATCH)
    ).all()
    for proof in due:
        try:
            if proof.anchor_status == "pending_submit":
                raw = submit(proof.content_hash, calendar_factory)
                proof.anchor_proof = encode(raw)
                proof.anchor_status = "pending_confirm"
                proof.anchor_error = ""
                proof.anchor_next_try_at = now + CONFIRM_RETRY
                result.submitted += 1
            else:
                raw, height = upgrade(decode(proof.anchor_proof), calendar_factory)
                proof.anchor_proof = encode(raw)
                if height is not None:
                    proof.anchor_status = "confirmed"
                    proof.anchored_at = now
                    proof.anchor_reference = f"bitcoin block {height}"
                    proof.anchor_next_try_at = None
                    result.confirmed += 1
                elif now - proof.created_at.replace(tzinfo=now.tzinfo) > GIVE_UP_AFTER:
                    proof.anchor_status = "failed"
                    proof.anchor_error = "no Bitcoin confirmation after several days"
                    result.failed += 1
                else:
                    proof.anchor_next_try_at = now + CONFIRM_RETRY
                    result.waiting += 1
        except Exception as exc:  # noqa: BLE001 — one bad proof must not stop the queue
            proof.anchor_attempts = (proof.anchor_attempts or 0) + 1
            proof.anchor_error = str(exc)[:300]
            if proof.anchor_attempts >= MAX_SUBMIT_ATTEMPTS:
                proof.anchor_status = "failed"
                result.failed += 1
            else:
                proof.anchor_next_try_at = now + _backoff(proof.anchor_attempts)
            logger.warning("timestamp %s: %s", proof.idea_id, exc)
        db.add(proof)
    db.commit()
    return result


def requeue(db: Session, proof: IdeaProof) -> None:
    """Admin action: try a failed or stuck proof again from the start."""
    if not enabled():
        return
    proof.anchor_status = "pending_confirm" if proof.anchor_proof else "pending_submit"
    proof.anchor_attempts = 0
    proof.anchor_error = ""
    proof.anchor_next_try_at = utc_now()
    db.add(proof)
    db.commit()


async def worker_loop(session_factory: Callable[[], Session]) -> None:
    """Background task started with the app. Runs the blocking work in a thread."""

    def tick() -> RunResult:
        db = session_factory()
        try:
            return process_due(db)
        finally:
            db.close()

    while True:
        try:
            if enabled():
                await asyncio.to_thread(tick)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("timestamp worker tick failed")
        await asyncio.sleep(poll_seconds())
