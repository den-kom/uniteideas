"""Permanently delete ideas and accounts, with everything that hangs off them."""

from __future__ import annotations

import shutil

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Attachment,
    Idea,
    IdeaProof,
    JoinRequest,
    PocBuild,
    Report,
    ScreenItem,
    TeamMember,
    User,
    UserSkill,
    Vote,
)


def delete_idea(db: Session, idea_id: str) -> None:
    for model in (Attachment, IdeaProof, Vote, JoinRequest, TeamMember, Report, PocBuild):
        db.execute(delete(model).where(model.idea_id == idea_id))
    db.execute(delete(ScreenItem).where(ScreenItem.kind == "idea", ScreenItem.ref == idea_id))
    db.execute(delete(Idea).where(Idea.id == idea_id))
    shutil.rmtree(get_settings().upload_dir / idea_id, ignore_errors=True)


def delete_user(db: Session, user_id: str) -> int:
    """Delete an account, its ideas and everything it did. Returns how many ideas went with it."""
    idea_ids = list(db.scalars(select(Idea.id).where(Idea.owner_id == user_id)))
    for idea_id in idea_ids:
        delete_idea(db, idea_id)
    for model in (Vote, JoinRequest, TeamMember, ScreenItem, UserSkill):
        db.execute(delete(model).where(model.user_id == user_id))
    db.execute(delete(Report).where(Report.reporter_id == user_id))
    db.execute(delete(User).where(User.id == user_id))
    return len(idea_ids)
