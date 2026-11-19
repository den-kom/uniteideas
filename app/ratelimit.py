"""Simple database-backed rate limiting, so it survives restarts and works across workers.

Every attempt is stored as a RateEvent. A limit says "no more than N events for this key in
the last W seconds". Use `check` before doing the work and `record` when an attempt happens.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import RateEvent, utc_now

# bucket -> (max events, window in seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "login_ip": (10, 15 * 60),  # sign-in link requests per address
    "login_email": (5, 15 * 60),  # sign-in link requests for one email
    "verify_ip": (20, 15 * 60),  # bad or repeated link/password attempts per address
    "password_fail": (6, 15 * 60),  # wrong passwords per email
    "invite_ip": (5, 60 * 60),  # "ask for an invite" submissions per address
    "password_fail_ip": (20, 15 * 60),  # wrong passwords per address
}


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def record(db: Session, bucket: str, key: str) -> None:
    db.add(RateEvent(bucket=bucket, key=key.lower()[:320]))
    db.flush()


def retry_after(db: Session, bucket: str, key: str) -> int:
    """Seconds until another attempt is allowed; 0 means go ahead."""
    limit, window = LIMITS[bucket]
    cutoff = utc_now() - timedelta(seconds=window)
    rows = list(
        db.scalars(
            select(RateEvent.created_at)
            .where(RateEvent.bucket == bucket, RateEvent.key == key.lower()[:320], RateEvent.created_at > cutoff)
            .order_by(RateEvent.created_at.desc())
            .limit(limit)
        )
    )
    if len(rows) < limit:
        return 0
    oldest_counted = rows[-1].replace(tzinfo=utc_now().tzinfo)
    wait = (oldest_counted + timedelta(seconds=window) - utc_now()).total_seconds()
    return max(1, int(wait) + 1)


def clear(db: Session, bucket: str, key: str) -> None:
    db.execute(delete(RateEvent).where(RateEvent.bucket == bucket, RateEvent.key == key.lower()[:320]))


def sweep(db: Session) -> None:
    """Drop events older than the longest window."""
    longest = max(w for _, w in LIMITS.values())
    db.execute(delete(RateEvent).where(RateEvent.created_at < utc_now() - timedelta(seconds=longest * 2)))


def human_wait(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} seconds"
    return f"{(seconds + 59) // 60} minutes"
