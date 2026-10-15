"""Admin area: overview, accounts, audit log, timestamp queue. Moderators cannot enter."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app import audit, timestamping
from app.db import get_db
from app.models import (
    ROLE_ADMIN,
    ROLE_BOT,
    ROLE_MODERATOR,
    ROLE_USER,
    STATUS_PENDING,
    AuditLog,
    Idea,
    IdeaProof,
    Report,
    User,
)
from app.permissions import require_permission
from app.templating import render

router = APIRouter(prefix="/admin")

PAGE = 50
ASSIGNABLE_ROLES = [ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN]


def _admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(User.role == ROLE_ADMIN, User.is_active.is_(True))
    ) or 0


@router.get("")
def overview(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users.manage")),
):
    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    stats = {
        "members": count(select(func.count(User.id)).where(User.role != ROLE_BOT)),
        "ideas": count(select(func.count(Idea.id)).where(Idea.status == "published")),
        "waiting": count(select(func.count(Idea.id)).where(Idea.status == STATUS_PENDING)),
        "reports": count(select(func.count(Report.id)).where(Report.status == "open")),
        "ts_pending": count(
            select(func.count(IdeaProof.id)).where(
                IdeaProof.anchor_status.in_(("pending_submit", "pending_confirm"))
            )
        ),
        "ts_failed": count(select(func.count(IdeaProof.id)).where(IdeaProof.anchor_status == "failed")),
    }
    recent = db.scalars(select(AuditLog).order_by(desc(AuditLog.id)).limit(8)).all()
    return render(request, "admin_home.html", {"stats": stats, "recent": recent}, user=user)


@router.get("/users")
def users_page(
    request: Request,
    q: str = "",
    role: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users.manage")),
):
    stmt = select(User)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like), func.lower(User.display_name).like(like)))
    if role in {ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN, ROLE_BOT}:
        stmt = stmt.where(User.role == role)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = max(1, page)
    users = db.scalars(
        stmt.order_by(User.created_at).offset((page - 1) * PAGE).limit(PAGE)
    ).all()
    return render(
        request,
        "admin_users.html",
        {
            "users": users,
            "roles": ASSIGNABLE_ROLES,
            "q": q,
            "role_filter": role,
            "page": page,
            "pages": max(1, -(-total // PAGE)),
            "total": total,
        },
        user=user,
    )


@router.post("/users/{user_id}/role")
def set_role(
    user_id: str,
    role: str = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("users.manage")),
):
    if role not in ASSIGNABLE_ROLES:
        return RedirectResponse("/admin/users?err=Unknown+role", status_code=303)
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/admin/users?err=User+not+found", status_code=303)
    if target.is_bot:
        return RedirectResponse("/admin/users?err=Robot+accounts+cannot+be+changed+here", status_code=303)
    if target.id == admin.id and role != ROLE_ADMIN:
        return RedirectResponse(
            "/admin/users?err=You+cannot+remove+your+own+admin+role", status_code=303
        )
    if target.role == ROLE_ADMIN and role != ROLE_ADMIN and _admin_count(db) <= 1:
        return RedirectResponse("/admin/users?err=There+must+always+be+one+admin", status_code=303)
    if target.role != role:
        audit.record(db, admin, "user.role_change", "user", target.id, f"{target.role} to {role}")
        target.role = role
        db.add(target)
        db.commit()
    return RedirectResponse("/admin/users?msg=Role+updated", status_code=303)


@router.post("/users/{user_id}/status")
def set_status(
    user_id: str,
    action: str = Form(...),
    reason: str = Form(default=""),
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("users.manage")),
):
    """Suspend or reactivate an account. A suspended member is signed out and cannot sign back in."""
    target = db.get(User, user_id)
    if target is None or action not in {"suspend", "reactivate"}:
        return RedirectResponse("/admin/users?err=Nothing+to+do", status_code=303)
    if target.is_bot:
        return RedirectResponse("/admin/users?err=Robot+accounts+cannot+be+changed+here", status_code=303)
    if action == "suspend":
        if target.id == admin.id:
            return RedirectResponse("/admin/users?err=You+cannot+suspend+yourself", status_code=303)
        if not reason.strip():
            return RedirectResponse("/admin/users?err=Give+a+reason+for+the+suspension", status_code=303)
        if target.role == ROLE_ADMIN and _admin_count(db) <= 1:
            return RedirectResponse("/admin/users?err=There+must+always+be+one+admin", status_code=303)
        target.is_active = False
        audit.record(db, admin, "user.suspend", "user", target.id, reason.strip()[:300])
    else:
        target.is_active = True
        audit.record(db, admin, "user.reactivate", "user", target.id, reason.strip()[:300])
    db.add(target)
    db.commit()
    return RedirectResponse("/admin/users?msg=Account+updated", status_code=303)


@router.get("/audit")
def audit_page(
    request: Request,
    action: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit.view")),
):
    stmt = select(AuditLog)
    if action.strip():
        stmt = stmt.where(AuditLog.action == action.strip())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = max(1, page)
    rows = db.scalars(
        stmt.order_by(desc(AuditLog.id)).offset((page - 1) * PAGE).limit(PAGE)
    ).all()
    actions = sorted(db.scalars(select(AuditLog.action).distinct()).all())
    return render(
        request,
        "admin_audit.html",
        {
            "rows": rows,
            "actions": actions,
            "action": action,
            "page": page,
            "pages": max(1, -(-total // PAGE)),
        },
        user=user,
    )


@router.get("/timestamps")
def timestamps_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("system.manage")),
):
    problems = db.scalars(
        select(IdeaProof)
        .where(
            or_(
                IdeaProof.anchor_status == "failed",
                (IdeaProof.anchor_status.in_(("pending_submit", "pending_confirm")))
                & (IdeaProof.anchor_attempts > 0),
            )
        )
        .order_by(desc(IdeaProof.created_at))
        .limit(100)
    ).all()
    counts = dict(
        db.execute(select(IdeaProof.anchor_status, func.count()).group_by(IdeaProof.anchor_status)).all()
    )
    return render(
        request,
        "admin_timestamps.html",
        {"problems": problems, "counts": counts, "enabled": timestamping.enabled()},
        user=user,
    )


@router.post("/timestamps/{idea_id}/requeue")
def requeue_timestamp(
    idea_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("system.manage")),
):
    proof = db.scalar(select(IdeaProof).where(IdeaProof.idea_id == idea_id))
    if proof is None:
        return RedirectResponse("/admin/timestamps?err=Not+found", status_code=303)
    timestamping.requeue(db, proof)
    audit.record(db, admin, "timestamp.requeue", "idea", idea_id)
    db.commit()
    return RedirectResponse("/admin/timestamps?msg=Queued+again", status_code=303)
