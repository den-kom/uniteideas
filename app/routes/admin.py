"""Admin area: overview, accounts, audit log, timestamp queue. Moderators cannot enter."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app import audit, mailer, purge, timestamping
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
from app.config import base_url_for, get_settings
from app.permissions import require_permission
from app.security import create_login_token
from app.system_users import is_system_email
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


# ---- Create accounts -------------------------------------------------------------------------


@router.get("/users/new")
def new_user_form(request: Request, user: User = Depends(require_permission("users.manage"))):
    return render(request, "admin_user_new.html", {"roles": ASSIGNABLE_ROLES}, user=user)


@router.post("/users/new")
def new_user_create(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(default=""),
    role: str = Form(default=ROLE_USER),
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("users.manage")),
):
    clean = email.strip().lower()
    if "@" not in clean or len(clean) < 5:
        return RedirectResponse("/admin/users/new?err=Enter+a+valid+email+address", status_code=303)
    if is_system_email(clean):
        return RedirectResponse("/admin/users/new?err=That+address+is+reserved", status_code=303)
    if role not in ASSIGNABLE_ROLES:
        role = ROLE_USER
    if db.scalar(select(User).where(User.email == clean)) is not None:
        return RedirectResponse("/admin/users/new?err=An+account+with+that+email+already+exists", status_code=303)
    name = (display_name.strip() or clean.split("@")[0])[:80]
    member = User(email=clean, display_name=name, role=role)
    db.add(member)
    audit.record(db, admin, "user.create", "user", member.id, f"{clean} as {role}")
    db.commit()
    token = create_login_token(db, clean)
    link = f"{base_url_for(request)}/auth/verify?token={quote(token)}"
    mailer.send(
        clean,
        "Your UniteIdeas account is ready",
        f"An account has been created for you on UniteIdeas. Sign in with this one-time link "
        f"(valid {get_settings().magic_link_ttl_minutes} minutes):\n\n{link}\n\n"
        "After that you can set a password if you like, or ask for a new link any time.",
    )
    return render(
        request,
        "admin_user_created.html",
        {
            "member": member,
            "dev_link": link if get_settings().dev_show_magic_link else None,
        },
        user=admin,
    )


# ---- Bulk and single account actions ---------------------------------------------------------


def _bulk_targets(db: Session, ids: list[str], admin: User, action: str) -> tuple[list[User], int]:
    """Pick who the action may apply to. Robots, yourself and admins are never touched."""
    people = [u for u in db.scalars(select(User).where(User.id.in_(ids))).all()] if ids else []
    ok: list[User] = []
    skipped = len(set(ids)) - len(people)
    for person in people:
        if person.is_bot or person.id == admin.id:
            skipped += 1
        elif person.role == ROLE_ADMIN and action in {"suspend", "delete"}:
            skipped += 1
        else:
            ok.append(person)
    return ok, skipped


@router.post("/users/bulk")
def users_bulk(
    request: Request,
    action: str = Form(...),
    ids: list[str] = Form(default=[]),
    reason: str = Form(default=""),
    confirm: str = Form(default=""),
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("users.manage")),
):
    if action not in {"suspend", "reactivate", "delete"} or not ids:
        return RedirectResponse("/admin/users?err=Choose+at+least+one+member+and+an+action", status_code=303)
    targets, skipped = _bulk_targets(db, ids, admin, action)
    if not targets:
        return RedirectResponse(
            "/admin/users?err=None+of+those+accounts+can+be+changed+(admins,+robots+and+you+are+protected)",
            status_code=303,
        )
    note = f"+{skipped}+protected+account(s)+skipped" if skipped else ""
    if action == "suspend":
        if not reason.strip():
            return RedirectResponse("/admin/users?err=Give+a+reason+for+the+suspension", status_code=303)
        for person in targets:
            person.is_active = False
            audit.record(db, admin, "user.suspend", "user", person.id, reason.strip()[:300])
        db.commit()
        return RedirectResponse(f"/admin/users?msg={len(targets)}+account(s)+suspended{note}", status_code=303)
    if action == "reactivate":
        for person in targets:
            person.is_active = True
            audit.record(db, admin, "user.reactivate", "user", person.id, reason.strip()[:300])
        db.commit()
        return RedirectResponse(f"/admin/users?msg={len(targets)}+account(s)+reactivated{note}", status_code=303)

    # delete: show what will go, and only act once DELETE has been typed
    if confirm.strip() != "DELETE":
        counts = {
            person.id: db.scalar(select(func.count(Idea.id)).where(Idea.owner_id == person.id)) or 0
            for person in targets
        }
        return render(
            request,
            "admin_confirm.html",
            {
                "heading": f"Delete {len(targets)} account(s) permanently?",
                "explain": "Their ideas, votes, join requests, reports and uploaded files are deleted too. "
                "This cannot be undone. Suspend instead if you might change your mind.",
                "items": [
                    f"{p.display_name} <{p.email}> - {counts[p.id]} idea(s)" for p in targets
                ],
                "skipped": skipped,
                "action_url": "/admin/users/bulk",
                "fields": [("action", "delete")] + [("ids", p.id) for p in targets],
                "back_url": "/admin/users",
            },
            user=admin,
        )
    removed_ideas = 0
    for person in targets:
        label = f"{person.email} ({person.display_name})"
        removed_ideas += purge.delete_user(db, person.id)
        audit.record(db, admin, "user.delete", "user", person.id, label)
    db.commit()
    return RedirectResponse(
        f"/admin/users?msg={len(targets)}+account(s)+and+{removed_ideas}+idea(s)+deleted{note}", status_code=303
    )


# ---- Ideas: find and delete, one or many ----------------------------------------------------


@router.get("/ideas")
def ideas_page(
    request: Request,
    q: str = "",
    status: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users.manage")),
):
    stmt = select(Idea, User).join(User, User.id == Idea.owner_id)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Idea.title).like(like),
                func.lower(User.email).like(like),
                func.lower(User.display_name).like(like),
            )
        )
    if status in {"published", "pending", "removed"}:
        stmt = stmt.where(Idea.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = max(1, page)
    rows = db.execute(stmt.order_by(desc(Idea.created_at)).offset((page - 1) * PAGE).limit(PAGE)).all()
    return render(
        request,
        "admin_ideas.html",
        {"rows": rows, "q": q, "status_filter": status, "page": page, "pages": max(1, -(-total // PAGE)), "total": total},
        user=user,
    )


@router.post("/ideas/bulk")
def ideas_bulk(
    request: Request,
    ids: list[str] = Form(default=[]),
    confirm: str = Form(default=""),
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("users.manage")),
):
    ideas = db.scalars(select(Idea).where(Idea.id.in_(ids))).all() if ids else []
    if not ideas:
        return RedirectResponse("/admin/ideas?err=Choose+at+least+one+idea", status_code=303)
    if confirm.strip() != "DELETE":
        return render(
            request,
            "admin_confirm.html",
            {
                "heading": f"Delete {len(ideas)} idea(s) permanently?",
                "explain": "Votes, join requests, reports and uploaded files go with them. "
                "This cannot be undone. Use Moderation to remove an idea but keep a record.",
                "items": [f"{i.title} (posted {i.created_at.strftime('%d %b %Y')})" for i in ideas],
                "skipped": 0,
                "action_url": "/admin/ideas/bulk",
                "fields": [("ids", i.id) for i in ideas],
                "back_url": "/admin/ideas",
            },
            user=admin,
        )
    for idea in ideas:
        label = f"{idea.title[:120]} (owner {idea.owner_id})"
        purge.delete_idea(db, idea.id)
        audit.record(db, admin, "idea.delete", "idea", idea.id, label)
    db.commit()
    return RedirectResponse(f"/admin/ideas?msg={len(ideas)}+idea(s)+deleted", status_code=303)
