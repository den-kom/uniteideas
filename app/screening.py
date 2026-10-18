"""Screening: check text before it goes live.

Ideas and custom skills are queued as ScreenItems. A built-in word check gives a first verdict:
clean text is approved, text that touches a blocked topic is escalated to a moderator. When
SCREENING_MODE=agent, clean text waits for AgentBob (through /api/agent/screen) instead, and
AgentBob either approves it or escalates it. Nobody but a person can reject escalated items.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.models import (
    STATUS_PENDING,
    STATUS_PUBLISHED,
    STATUS_REMOVED,
    Idea,
    ScreenItem,
    User,
    UserSkill,
    utc_now,
)

# Topics that are not allowed on UniteIdeas. A match never rejects on its own: it sends the item
# to a person, because words are used innocently too ("kill switch", "drug discovery").
BLOCKED_TOPICS: dict[str, list[str]] = {
    "weapons": ["weapon", "firearm", "gun smuggling", "bomb", "explosive", "ammunition", "assault rifle", "silencer"],
    "adult content": ["porn", "xxx", "nude", "escort service", "erotic", "onlyfans"],
    "illegal drugs": ["cocaine", "heroin", "methamphetamine", "drug dealing", "buy drugs", "fentanyl"],
    "fraud": ["money laundering", "counterfeit", "carding", "phishing kit", "fake id", "stolen credit", "ponzi"],
    "hacking for harm": ["ransomware", "ddos for hire", "keylogger", "steal passwords", "botnet"],
    "hate or violence": ["genocide", "kill all", "white power", "lynch", "terrorist"],
    "child safety": ["child abuse", "underage sex", "csam"],
}

_PATTERNS = {
    topic: re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(w) for w in words) + r")", re.I)
    for topic, words in BLOCKED_TOPICS.items()
}


def check_text(text: str) -> tuple[str, str]:
    """Return ("approved", "") for clean text or ("escalated", reason) when a blocked topic shows up."""
    hits = [topic for topic, pattern in _PATTERNS.items() if pattern.search(text or "")]
    if hits:
        return "escalated", "Mentions a restricted topic: " + ", ".join(hits)
    return "approved", ""


def _decide(db: Session, item: ScreenItem, status: str, reason: str, by: str) -> None:
    item.status = status
    item.reason = reason[:2000]
    item.decided_by = by
    item.decided_at = utc_now()
    db.add(item)


def queue_idea(db: Session, idea: Idea, extra_text: str = "", trusted: bool = False) -> ScreenItem:
    """Queue a new idea. `extra_text` (sealed detail) is checked by the word check only, never sent to AgentBob."""
    text = "\n\n".join(part for part in (idea.title, idea.summary, idea.public_body) if part)
    item = ScreenItem(kind="idea", ref=idea.id, user_id=idea.owner_id, text=text[:20000])
    db.add(item)
    verdict, reason = check_text(text + "\n" + extra_text)
    if verdict == "escalated":
        _decide(db, item, "escalated", reason, "rules")
    elif get_settings().screening_mode == "rules":
        _decide(db, item, "approved", "", "rules")
    # else: stays pending for AgentBob
    idea.status = STATUS_PENDING
    if item.status == "approved" and trusted:
        idea.status = STATUS_PUBLISHED
        idea.published_at = utc_now()
    db.add(idea)
    return item


def queue_skill(db: Session, user: User, text: str) -> ScreenItem:
    skill = f"custom:{text}"
    item = ScreenItem(kind="skill", ref=f"{user.id}|{skill}"[:80], user_id=user.id, text=text)
    db.add(item)
    verdict, reason = check_text(text)
    row = next((s for s in user.skills if s.skill == skill), None)
    if verdict == "escalated":
        _decide(db, item, "escalated", reason, "rules")
    elif get_settings().screening_mode == "rules":
        _decide(db, item, "approved", "", "rules")
    if row is not None:
        row.status = "approved" if item.status == "approved" else "pending"
    return item


def apply(db: Session, item: ScreenItem, status: str, reason: str, actor: User, by_agent: bool) -> bool:
    """Record a decision on a pending or escalated item. Returns False when the decision is not allowed.

    AgentBob may approve or escalate. Only a person may reject, and only a person may approve
    something already escalated.
    """
    if status not in {"approved", "escalated", "rejected"}:
        return False
    if by_agent and (status == "rejected" or item.status == "escalated"):
        return False
    if item.status in {"approved", "rejected"}:
        return False
    _decide(db, item, status, reason, actor.id)

    if item.kind == "idea":
        idea = db.get(Idea, item.ref)
        if idea is not None and idea.status == STATUS_PENDING:
            if status == "approved":
                # A person approving it has reviewed it; AgentBob's approval only passes the word check
                # and an account's first idea still goes to a moderator.
                trusted = not by_agent or _has_published(db, idea)
                if trusted:
                    idea.status = STATUS_PUBLISHED
                    idea.published_at = utc_now()
                    idea.updated_at = utc_now()
            elif status == "rejected":
                idea.status = STATUS_REMOVED
                idea.review_note = reason[:2000] or "Not allowed on UniteIdeas."
                idea.updated_at = utc_now()
            db.add(idea)
    elif item.kind == "skill":
        user_id, _, skill = item.ref.partition("|")
        row = db.scalar(select(UserSkill).where(UserSkill.user_id == user_id, UserSkill.skill == skill))
        if row is not None:
            if status == "approved":
                row.status = "approved"
            elif status == "rejected":
                db.delete(row)
            else:
                row.status = "pending"
            if status != "rejected":
                db.add(row)
    audit.record(db, actor, f"screen.{status}", item.kind, item.ref, reason[:200])
    return True


def _has_published(db: Session, idea: Idea) -> bool:
    from sqlalchemy import func

    return bool(
        db.scalar(
            select(func.count(Idea.id)).where(
                Idea.owner_id == idea.owner_id, Idea.status == STATUS_PUBLISHED, Idea.id != idea.id
            )
        )
    )
