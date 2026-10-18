"""Reporting and the moderator queue. Account management lives in admin.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    STATUS_PENDING,
    STATUS_PUBLISHED,
    STATUS_REMOVED,
    Idea,
    Report,
    ScreenItem,
    User,
    utc_now,
)
from app import audit, screening
from app.permissions import require_permission
from app.sealing import unseal
from app.security import require_user
from app.templating import render

router = APIRouter()


@router.post("/ideas/{idea_id}/report")
def report_idea(
    idea_id: str,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    idea = db.get(Idea, idea_id)
    if idea is None:
        return RedirectResponse("/ideas?err=Idea+not+found", status_code=303)
    if not reason.strip():
        return RedirectResponse(f"/ideas/{idea_id}?err=Describe+the+problem", status_code=303)
    db.add(
        Report(idea_id=idea_id, reporter_id=user.id, reason=reason.strip()[:2000])
    )
    db.commit()
    return RedirectResponse(
        f"/ideas/{idea_id}?msg=Reported+to+moderators", status_code=303
    )


@router.get("/moderation")
def queue(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ideas.review")),
):
    pending_ideas = db.scalars(
        select(Idea).where(Idea.status == STATUS_PENDING).order_by(Idea.created_at)
    ).all()
    pending_owners = {i.owner_id: db.get(User, i.owner_id) for i in pending_ideas}
    open_reports = db.scalars(
        select(Report).where(Report.status == "open").order_by(desc(Report.created_at))
    ).all()
    closed_reports = db.scalars(
        select(Report).where(Report.status != "open").order_by(desc(Report.created_at)).limit(20)
    ).all()
    ideas = {
        r.idea_id: db.get(Idea, r.idea_id) for r in [*open_reports, *closed_reports]
    }
    reporters = {
        r.reporter_id: db.get(User, r.reporter_id)
        for r in [*open_reports, *closed_reports]
    }
    held = db.scalars(
        select(ScreenItem)
        .where(ScreenItem.status == "escalated")
        .order_by(ScreenItem.created_at)
    ).all()
    held_ideas = {i.ref: db.get(Idea, i.ref) for i in held if i.kind == "idea"}
    held_users = {i.user_id: db.get(User, i.user_id) for i in held}
    waiting_for_agent = (
        db.scalar(select(func.count(ScreenItem.id)).where(ScreenItem.status == "pending")) or 0
    )
    return render(
        request,
        "moderation.html",
        {
            "held": held,
            "held_ideas": held_ideas,
            "held_users": held_users,
            "waiting_for_agent": waiting_for_agent,
            "pending_ideas": pending_ideas,
            "pending_owners": pending_owners,
            "open_reports": open_reports,
            "closed_reports": closed_reports,
            "ideas": ideas,
            "reporters": reporters,
        },
        user=user,
    )


def _close_screen(db: Session, idea_id: str, status: str, note: str, staff: User) -> None:
    """A moderator reviewing an idea also settles its screening item."""
    for item in db.scalars(
        select(ScreenItem).where(
            ScreenItem.kind == "idea",
            ScreenItem.ref == idea_id,
            ScreenItem.status.in_(("pending", "escalated")),
        )
    ):
        item.status = status
        item.reason = note[:2000]
        item.decided_by = staff.id
        item.decided_at = utc_now()
        db.add(item)


@router.post("/moderation/screening/{item_id}/{decision}")
def decide_screen(
    item_id: str,
    decision: str,
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ideas.review")),
):
    item = db.get(ScreenItem, item_id)
    status = {"approve": "approved", "reject": "rejected"}.get(decision)
    if item is None or status is None:
        return RedirectResponse("/moderation?err=Item+not+found", status_code=303)
    if not screening.apply(db, item, status, note, user, by_agent=False):
        return RedirectResponse("/moderation?err=Already+decided", status_code=303)
    db.commit()
    return RedirectResponse("/moderation?msg=Decision+saved", status_code=303)


@router.post("/moderation/ideas/{idea_id}/approve")
def approve_idea(
    idea_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ideas.review")),
):
    idea = db.get(Idea, idea_id)
    if idea is None:
        return RedirectResponse("/moderation?err=Idea+not+found", status_code=303)
    if idea.status != STATUS_PENDING:
        return RedirectResponse("/moderation?err=Already+reviewed", status_code=303)
    idea.status = STATUS_PUBLISHED
    idea.published_at = utc_now()
    idea.updated_at = utc_now()
    db.add(idea)
    _close_screen(db, idea.id, "approved", "", user)
    audit.record(db, user, "idea.approve", "idea", idea.id, idea.title)
    db.commit()
    return RedirectResponse("/moderation?msg=Idea+approved+and+published", status_code=303)


@router.post("/moderation/ideas/{idea_id}/reject")
def reject_idea(
    idea_id: str,
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ideas.review")),
):
    idea = db.get(Idea, idea_id)
    if idea is None:
        return RedirectResponse("/moderation?err=Idea+not+found", status_code=303)
    idea.status = STATUS_REMOVED
    idea.review_note = note.strip()[:2000]
    idea.updated_at = utc_now()
    db.add(idea)
    _close_screen(db, idea.id, "rejected", note.strip(), user)
    audit.record(db, user, "idea.reject", "idea", idea.id, note.strip()[:200])
    db.commit()
    return RedirectResponse("/moderation?msg=Idea+rejected", status_code=303)


def _resolve(
    db: Session,
    report_id: str,
    staff: User,
    *,
    remove_idea: bool,
    note: str,
) -> RedirectResponse:
    report = db.get(Report, report_id)
    if report is None:
        return RedirectResponse("/moderation?err=Report+not+found", status_code=303)
    report.status = "actioned" if remove_idea else "dismissed"
    report.resolution_note = note.strip()[:2000]
    report.resolved_by = staff.id
    report.resolved_at = utc_now()
    db.add(report)
    if remove_idea:
        idea = db.get(Idea, report.idea_id)
        if idea is not None:
            idea.status = STATUS_REMOVED
            idea.updated_at = utc_now()
            db.add(idea)
    audit.record(
        db,
        staff,
        "report.remove_idea" if remove_idea else "report.dismiss",
        "report",
        report.id,
        f"idea {report.idea_id}: {note.strip()[:200]}",
    )
    db.commit()
    return RedirectResponse("/moderation?msg=Report+resolved", status_code=303)


@router.post("/reports/{report_id}/dismiss")
def dismiss(
    report_id: str,
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ideas.review")),
):
    return _resolve(db, report_id, user, remove_idea=False, note=note)


@router.post("/reports/{report_id}/remove-idea")
def remove_idea(
    report_id: str,
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ideas.review")),
):
    return _resolve(db, report_id, user, remove_idea=True, note=note)


@router.get("/moderation/ideas/{idea_id}/sealed")
def review_sealed(
    request: Request,
    idea_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("sealed.review")),
):
    """Staff can read an idea's sealed text when they have to judge it. Every view is logged."""
    idea = db.get(Idea, idea_id)
    if idea is None:
        return RedirectResponse("/moderation?err=Idea+not+found", status_code=303)
    audit.record(db, user, "sealed.viewed", "idea", idea.id, idea.title)
    db.commit()
    text = unseal(idea.sealed_blob) if idea.sealed_blob else ""
    return render(
        request, "sealed_review.html", {"idea": idea, "sealed_text": text}, user=user
    )
