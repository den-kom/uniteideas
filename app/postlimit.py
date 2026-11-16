"""How long a member waits between ideas. The wait grows with how many they posted recently.

Ideas posted in the last 24 hours -> wait since the latest one:
  0: none   1: 10 minutes   2: 30 minutes   3: 2 hours   4: 6 hours   5 or more: 24 hours
Accounts under three days old wait twice as long. Admins and robots are exempt.
Removed and held ideas still count, so spam does not get a fresh start.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ROLE_ADMIN, ROLE_BOT, Idea, User, utc_now

LADDER_SECONDS = [0, 10 * 60, 30 * 60, 2 * 3600, 6 * 3600, 24 * 3600]
NEW_ACCOUNT_DAYS = 3


def wait_seconds(db: Session, user: User) -> int:
    if user.role in (ROLE_ADMIN, ROLE_BOT):
        return 0
    now = utc_now()
    times = list(
        db.scalars(
            select(Idea.created_at)
            .where(Idea.owner_id == user.id, Idea.created_at > now - timedelta(hours=24))
            .order_by(Idea.created_at.desc())
        )
    )
    if not times:
        return 0
    times = [t.replace(tzinfo=now.tzinfo) for t in times]
    created = user.created_at.replace(tzinfo=now.tzinfo)
    base = LADDER_SECONDS[min(len(times), len(LADDER_SECONDS) - 1)]
    if now - created < timedelta(days=NEW_ACCOUNT_DAYS):
        base *= 2
    remaining = (times[0] + timedelta(seconds=base) - now).total_seconds()
    return max(0, int(remaining) + 1) if remaining > 0 else 0


def describe(seconds: int) -> str:
    if seconds < 90:
        return f"{max(seconds, 1)} seconds"
    if seconds < 3 * 3600:
        return f"{(seconds + 59) // 60} minutes"
    return f"{(seconds + 3599) // 3600} hours"
