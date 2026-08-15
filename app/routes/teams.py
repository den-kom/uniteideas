"""Collaboration: request to join with a time pledge, owner approves."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Idea, JoinRequest, TeamMember, User, utc_now
from app.security import require_user

router = APIRouter()


@router.post("/ideas/{idea_id}/join")
def request_join(
    idea_id: str,
    message: str = Form(default=""),
    pledged_hours_per_week: int = Form(default=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    settings = get_settings()
    idea = db.get(Idea, idea_id)
    if idea is None or idea.status != "published":
        return RedirectResponse("/ideas?err=Idea+not+found", status_code=303)
    if idea.owner_id == user.id:
        return RedirectResponse(
            f"/ideas/{idea_id}?err=You+already+own+this+idea", status_code=303
        )

    hours = max(1, min(int(pledged_hours_per_week), settings.max_pledge_hours_per_week))

    existing_pledge = sum(
        m.pledged_hours_per_week
        for m in db.scalars(select(TeamMember).where(TeamMember.user_id == user.id)).all()
    )
    if existing_pledge + hours > settings.max_pledge_hours_per_week:
        return RedirectResponse(
            f"/ideas/{idea_id}?err=That+would+exceed+your+weekly+pledge+cap+of+"
            f"{settings.max_pledge_hours_per_week}h",
            status_code=303,
        )

    db.add(
        JoinRequest(
            idea_id=idea_id,
            user_id=user.id,
            message=message.strip()[:2000],
            pledged_hours_per_week=hours,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"/ideas/{idea_id}?err=You+have+already+asked+to+join", status_code=303
        )
    return RedirectResponse(
        f"/ideas/{idea_id}?msg=Request+sent+to+the+idea+owner", status_code=303
    )


def _decide(
    db: Session,
    join_id: str,
    owner: User,
    approve: bool,
) -> RedirectResponse:
    join = db.get(JoinRequest, join_id)
    if join is None:
        return RedirectResponse("/profile?err=Request+not+found", status_code=303)
    idea = db.get(Idea, join.idea_id)
    if idea is None or idea.owner_id != owner.id:
        return RedirectResponse("/profile?err=Not+your+idea", status_code=303)
    if join.status != "pending":
        return RedirectResponse(
            f"/ideas/{idea.id}?err=Already+decided", status_code=303
        )

    join.status = "approved" if approve else "declined"
    join.decided_at = utc_now()
    db.add(join)
    if approve:
        db.add(
            TeamMember(
                idea_id=idea.id,
                user_id=join.user_id,
                pledged_hours_per_week=join.pledged_hours_per_week,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    word = "approved" if approve else "declined"
    return RedirectResponse(f"/ideas/{idea.id}?msg=Request+{word}", status_code=303)


@router.post("/joins/{join_id}/approve")
def approve_join(
    join_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return _decide(db, join_id, user, approve=True)


@router.post("/joins/{join_id}/decline")
def decline_join(
    join_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return _decide(db, join_id, user, approve=False)
