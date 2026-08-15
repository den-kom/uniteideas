"""Reporting, moderator queue, and admin role management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_USER,
    STATUS_PENDING,
    STATUS_PUBLISHED,
    STATUS_REMOVED,
    Idea,
    Report,
    User,
    utc_now,
)
from app.security import require_admin, require_staff, require_user
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
    user: User = Depends(require_staff),
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
    return render(
        request,
        "moderation.html",
        {
            "pending_ideas": pending_ideas,
            "pending_owners": pending_owners,
            "open_reports": open_reports,
            "closed_reports": closed_reports,
            "ideas": ideas,
            "reporters": reporters,
        },
        user=user,
    )


@router.post("/moderation/ideas/{idea_id}/approve")
def approve_idea(
    idea_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
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
    db.commit()
    return RedirectResponse("/moderation?msg=Idea+approved+and+published", status_code=303)


@router.post("/moderation/ideas/{idea_id}/reject")
def reject_idea(
    idea_id: str,
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    idea = db.get(Idea, idea_id)
    if idea is None:
        return RedirectResponse("/moderation?err=Idea+not+found", status_code=303)
    idea.status = STATUS_REMOVED
    idea.review_note = note.strip()[:2000]
    idea.updated_at = utc_now()
    db.add(idea)
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
    db.commit()
    return RedirectResponse("/moderation?msg=Report+resolved", status_code=303)


@router.post("/reports/{report_id}/dismiss")
def dismiss(
    report_id: str,
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    return _resolve(db, report_id, user, remove_idea=False, note=note)


@router.post("/reports/{report_id}/remove-idea")
def remove_idea(
    report_id: str,
    note: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    return _resolve(db, report_id, user, remove_idea=True, note=note)


@router.get("/admin/users")
def admin_users(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return render(
        request,
        "admin_users.html",
        {"users": users, "roles": [ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN]},
        user=user,
    )


@router.post("/admin/users/{user_id}/role")
def set_role(
    user_id: str,
    role: str = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if role not in {ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN}:
        return RedirectResponse("/admin/users?err=Unknown+role", status_code=303)
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/admin/users?err=User+not+found", status_code=303)
    if target.id == admin.id and role != ROLE_ADMIN:
        return RedirectResponse(
            "/admin/users?err=You+cannot+remove+your+own+admin+role", status_code=303
        )
    target.role = role
    db.add(target)
    db.commit()
    return RedirectResponse("/admin/users?msg=Role+updated", status_code=303)
