#!/usr/bin/env python
"""Fill a development database with a few example ideas so pages have something to show.

Usage: DB_PATH=data/demo.db python scripts/seed_demo.py
Never run this against the live database.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Idea, IdeaProof, User, Vote, utc_now  # noqa: E402
from app.proof import compute_content_hash, sha256_text  # noqa: E402
from app.sealing import seal  # noqa: E402

PEOPLE = ["Maya Chen", "Tom Okafor", "Priya Nair", "Lukas Meyer", "Sam Rivera"]
IDEAS = [
    ("Clip-on guard for pets' tails and chair wheels", "A snap-on ring that stops tails and paws getting caught in office chair castors.", "pets", "physical"),
    ("Shared tool library for apartment blocks", "A simple app that lets neighbours lend and borrow drills, ladders and saws.", "home", "digital"),
    ("Medication reminder that talks to the whole family", "Gentle reminders that also tell a nominated family member if a dose is missed.", "health", "digital"),
    ("Reusable lunch pods with a built-in cooler plate", "Stackable pods that keep food cold for six hours without ice packs.", "sustainability", "physical"),
    ("Study buddy matcher for night-shift students", "Matches students who study at odd hours so nobody has to study alone at 2am.", "education", "digital"),
    ("Screen-reader friendly recipe cards", "Recipes written so a screen reader reads ingredients and steps in a sensible order.", "accessibility", "digital"),
    ("One-tap meeting notes into tasks", "Turns a messy meeting transcript into three clear next steps.", "productivity", "digital"),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    users = []
    for name in PEOPLE:
        email = name.lower().replace(" ", ".") + "@example.com"
        user = db.query(User).filter_by(email=email).first()
        if user is None:
            user = User(email=email, display_name=name, onboarding_done=True)
            db.add(user)
            db.flush()
        users.append(user)
    for i, (title, summary, category, kind) in enumerate(IDEAS):
        if db.query(Idea).filter_by(title=title).first():
            continue
        owner = users[i % len(users)]
        body = f"{summary}\n\nThe problem: people run into this every week and nothing good exists yet."
        digest, _ = compute_content_hash(
            title=title, summary=summary, category=category, idea_type=kind,
            public_body=body, sealed_detail="Private details.", attachment_hashes=[],
        )
        idea = Idea(
            owner_id=owner.id, title=title, summary=summary, category=category,
            idea_type=kind, public_body=body, sealed_blob=seal("Private details."),
            status="published", published_at=utc_now(), score=0,
        )
        db.add(idea)
        db.flush()
        db.add(IdeaProof(idea_id=idea.id, content_hash=digest,
                         author_email_hash=sha256_text(owner.email)))
        for voter in users[: (len(IDEAS) - i) % 5 + 1]:
            if voter.id != owner.id:
                db.add(Vote(idea_id=idea.id, user_id=voter.id))
                idea.score += 1
    db.commit()
    print("Seeded demo data.")


if __name__ == "__main__":
    main()
