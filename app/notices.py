"""Email moderators and admins when something needs a person to look.

To avoid flooding inboxes, one email per kind of event is sent per cooldown period
(STAFF_NOTICE_COOLDOWN_MINUTES, default 30). The email says what happened and links to the queue,
which always shows the full, current list. Call before the caller's commit; nothing here commits.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import mailer
from app.config import get_settings
from app.models import (
    ROLE_ADMIN,
    ROLE_MODERATOR,
    STATUS_PENDING,
    Idea,
    RateEvent,
    Report,
    User,
    utc_now,
)

KINDS = {
    "held": "An idea is waiting for review",
    "report": "An idea has been reported",
    "skill": "A custom skill is waiting for review",
    "interest": "Someone asked to join UniteIdeas",
}


def notify_staff(db: Session, kind: str, detail: str) -> int:
    """Send a throttled notice. Returns how many emails were written (0 when throttled or off)."""
    settings = get_settings()
    if not settings.staff_notices or kind not in KINDS:
        return 0
    cutoff = utc_now() - timedelta(minutes=settings.staff_notice_cooldown_minutes)
    recent = db.scalar(
        select(func.count(RateEvent.id)).where(
            RateEvent.bucket == "staff_notice", RateEvent.key == kind, RateEvent.created_at > cutoff
        )
    )
    if recent:
        return 0
    db.add(RateEvent(bucket="staff_notice", key=kind))
    db.flush()
    waiting = db.scalar(select(func.count(Idea.id)).where(Idea.status == STATUS_PENDING)) or 0
    open_reports = db.scalar(select(func.count(Report.id)).where(Report.status == "open")) or 0
    staff = db.scalars(
        select(User).where(User.role.in_((ROLE_MODERATOR, ROLE_ADMIN)), User.is_active.is_(True))
    ).all()
    queue = "/admin/requests" if kind == "interest" else "/moderation"
    body = (
        f"{KINDS[kind]}.\n\n{detail[:300]}\n\n"
        f"Right now: {waiting} idea(s) held, {open_reports} open report(s).\n"
        f"Review queue: {settings.public_base_url.rstrip('/')}{queue}\n\n"
        f"You get at most one email of this kind every {settings.staff_notice_cooldown_minutes} minutes."
    )
    for person in staff:
        mailer.send(person.email, f"[UniteIdeas] {KINDS[kind]}", body)
    return len(staff)
