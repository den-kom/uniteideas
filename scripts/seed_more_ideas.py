#!/usr/bin/env python
"""Add ten example ideas (5 digital, 5 physical) with a spread of votes, to see all bulb levels.

Usage:   .venv/bin/python scripts/seed_more_ideas.py            add them (safe to run twice)
         .venv/bin/python scripts/seed_more_ideas.py --remove   delete them and their demo voters again

Demo accounts use the address domain @demo.uniteideas.test so they are easy to spot and remove.
For test environments only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app import glow  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Attachment, Idea, IdeaProof, User, Vote, utc_now  # noqa: E402
from app.proof import compute_content_hash, sha256_text  # noqa: E402
from app.sealing import seal  # noqa: E402

DOMAIN = "@demo.uniteideas.test"
VOTERS = 60
AUTHORS = ["Ava Thompson", "Noah Patel", "Isla Nguyen", "Leo Fischer", "Zoe Martin"]

# title, summary, category, type, upvotes, downvotes
IDEAS = [
    ("Medication box that rings the family", "A pill organiser that sends a quiet message to a nominated relative when a dose is missed.", "health", "physical", 46, 2),
    ("Neighbourhood meal swap", "An app where neighbours cook one extra portion and trade meals, so nobody eats alone or wastes food.", "community", "digital", 38, 3),
    ("Snap-on tap aerator for renters", "A tool-free attachment that cuts tap water use by half and fits any standard kitchen mixer.", "sustainability", "physical", 29, 1),
    ("Bus arrival board for your hallway", "A small display that shows live departures for your stop so you leave at the right minute.", "transport", "physical", 21, 0),
    ("Plain-language bills", "Paste any utility or council bill and get a one-paragraph explanation and what to question.", "money", "digital", 15, 4),
    ("Left-handed kitchen knife set", "Properly mirrored blades and handles, not just a flipped right-handed knife.", "home", "physical", 10, 1),
    ("Sleep-friendly alarm light", "A bedside light that brightens slowly over thirty minutes and chooses the lightest sleep moment.", "health", "physical", 7, 2),
    ("Local repair directory", "A map of people who fix toasters, bikes and phones, with honest prices and wait times.", "sustainability", "digital", 4, 1),
    ("Quiet-hours scheduler for shared flats", "Housemates set study, sleep and party hours once and get gentle reminders instead of arguments.", "community", "digital", 2, 2),
    ("Foldable laundry rack that fits a door", "A drying rack that hangs over any door and folds to the thickness of a book.", "home", "physical", 1, 3),
]


def remove(db) -> None:
    users = db.scalars(select(User).where(User.email.like(f"%{DOMAIN}"))).all()
    ids = [u.id for u in users]
    idea_ids = [i.id for i in db.scalars(select(Idea).where(Idea.owner_id.in_(ids)))] if ids else []
    if idea_ids:
        db.execute(delete(Vote).where(Vote.idea_id.in_(idea_ids)))
        db.execute(delete(Attachment).where(Attachment.idea_id.in_(idea_ids)))
        db.execute(delete(IdeaProof).where(IdeaProof.idea_id.in_(idea_ids)))
        db.execute(delete(Idea).where(Idea.id.in_(idea_ids)))
    if ids:
        db.execute(delete(Vote).where(Vote.user_id.in_(ids)))
        db.execute(delete(User).where(User.id.in_(ids)))
    db.commit()
    glow.recalculate(db)
    print(f"Removed {len(idea_ids)} ideas and {len(ids)} demo accounts.")


def main() -> None:
    init_db()
    db = SessionLocal()
    if "--remove" in sys.argv:
        remove(db)
        return

    def person(name: str, email: str) -> User:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=name, onboarding_done=True, profile_done=True)
            db.add(user)
            db.flush()
        return user

    authors = [person(n, n.lower().replace(" ", ".") + DOMAIN) for n in AUTHORS]
    voters = [person(f"Demo voter {i:02d}", f"voter{i:02d}{DOMAIN}") for i in range(1, VOTERS + 1)]
    added = 0
    for n, (title, summary, category, kind, ups, downs) in enumerate(IDEAS):
        if db.scalar(select(Idea).where(Idea.title == title)):
            continue
        owner = authors[n % len(authors)]
        body = f"{summary}\n\nThe problem: people run into this every week and nothing good exists yet."
        digest, _ = compute_content_hash(
            title=title, summary=summary, category=category, idea_type=kind,
            public_body=body, sealed_detail="Private details.", attachment_hashes=[],
        )
        idea = Idea(
            owner_id=owner.id, title=title, summary=summary, category=category, idea_type=kind,
            public_body=body, sealed_blob=seal("Private details."), status="published",
            published_at=utc_now(), score=ups - downs,
        )
        db.add(idea)
        db.flush()
        db.add(IdeaProof(idea_id=idea.id, content_hash=digest, author_email_hash=sha256_text(owner.email)))
        # Rotate which voters are used so the same people do not always vote the same way.
        pool = voters[n * 3 % VOTERS:] + voters[: n * 3 % VOTERS]
        for v in pool[:ups]:
            db.add(Vote(idea_id=idea.id, user_id=v.id, value=1))
        for v in pool[ups : ups + downs]:
            db.add(Vote(idea_id=idea.id, user_id=v.id, value=-1))
        added += 1
    db.commit()
    glow.recalculate(db)
    print(f"Added {added} ideas ({len(IDEAS) - added} already there). Bulb levels recalculated.")


if __name__ == "__main__":
    main()
