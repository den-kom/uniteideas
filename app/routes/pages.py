"""Public pages: home, feed, one-pager, verification, profile, onboarding."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Idea,
    IdeaProof,
    JoinRequest,
    PROGRESS_STAGES,
    TeamMember,
    User,
    Vote,
)
from app.proof import sha256_text
from app.sealing import unseal
from app.security import current_user, require_user
from app.verification import Check, Verification, find_proof, verify
from app.templating import render

router = APIRouter()


def _published(stmt):
    return stmt.where(Idea.status == "published")


def _backed_ids(db: Session, user: User | None, ideas) -> set[str]:
    """Which of these ideas the signed-in user already backs."""
    if user is None or not ideas:
        return set()
    return set(
        db.scalars(
            select(Vote.idea_id).where(
                Vote.user_id == user.id, Vote.idea_id.in_([i.id for i in ideas])
            )
        ).all()
    )


@router.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    top = db.scalars(
        _published(select(Idea)).order_by(desc(Idea.score), desc(Idea.created_at)).limit(4)
    ).all()
    recent = db.scalars(
        _published(select(Idea)).order_by(desc(Idea.created_at)).limit(4)
    ).all()
    backed = _backed_ids(db, user, list(top) + list(recent))
    return render(
        request, "index.html", {"top": top, "recent": recent, "backed": backed}, user=user
    )


@router.get("/ideas")
def feed(
    request: Request,
    type: str = "all",
    category: str = "",
    sort: str = "top",
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    stmt = _published(select(Idea))
    if type in {"digital", "physical"}:
        stmt = stmt.where(Idea.idea_type == type)
    if category.strip():
        stmt = stmt.where(Idea.category == category.strip().lower())
    stmt = (
        stmt.order_by(desc(Idea.created_at))
        if sort == "new"
        else stmt.order_by(desc(Idea.score), desc(Idea.created_at))
    )
    ideas = db.scalars(stmt.limit(100)).all()
    categories = sorted(
        {c for c in db.scalars(_published(select(Idea.category))).all() if c}
    )
    return render(
        request,
        "feed.html",
        {
            "ideas": ideas,
            "filter_type": type,
            "filter_category": category,
            "sort": sort,
            "categories": categories,
            "backed": _backed_ids(db, user, ideas),
        },
        user=user,
    )


@router.get("/ideas/{idea_id}")
def idea_detail(
    request: Request,
    idea_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    idea = db.get(Idea, idea_id)
    if idea is None:
        return render(request, "not_found.html", {}, user=user, status_code=404)
    if idea.status != "published" and not (
        user and (user.is_staff or user.id == idea.owner_id)
    ):
        return render(request, "not_found.html", {}, user=user, status_code=404)

    is_owner = bool(user and user.id == idea.owner_id)
    member = None
    join_request = None
    if user:
        member = db.scalar(
            select(TeamMember).where(
                TeamMember.idea_id == idea.id, TeamMember.user_id == user.id
            )
        )
        join_request = db.scalar(
            select(JoinRequest).where(
                JoinRequest.idea_id == idea.id, JoinRequest.user_id == user.id
            )
        )

    can_see_sealed = idea.sealed_is_public or is_owner or bool(member) or bool(
        user and user.is_staff
    )
    sealed_text = unseal(idea.sealed_blob) if (can_see_sealed and idea.sealed_blob) else ""

    pending_joins = []
    if is_owner:
        pending_joins = db.scalars(
            select(JoinRequest).where(
                JoinRequest.idea_id == idea.id, JoinRequest.status == "pending"
            )
        ).all()

    has_voted = False
    if user:
        has_voted = (
            db.scalar(
                select(Vote).where(Vote.idea_id == idea.id, Vote.user_id == user.id)
            )
            is not None
        )

    members = db.scalars(select(TeamMember).where(TeamMember.idea_id == idea.id)).all()
    member_users = {
        m.user_id: db.get(User, m.user_id) for m in members
    }
    join_users = {j.user_id: db.get(User, j.user_id) for j in pending_joins}
    build = idea.latest_build
    show_demo = bool(build and build.preview_url and (build.is_public or is_owner))

    return render(
        request,
        "idea.html",
        {
            "idea": idea,
            "proof": idea.proof,
            "is_owner": is_owner,
            "is_member": bool(member),
            "sealed_text": sealed_text,
            "can_see_sealed": can_see_sealed,
            "join_request": join_request,
            "pending_joins": pending_joins,
            "join_users": join_users,
            "members": members,
            "member_users": member_users,
            "has_voted": has_voted,
            "stages": PROGRESS_STAGES,
            "build": build,
            "show_demo": show_demo,
        },
        user=user,
    )


@router.get("/verify")
def verify_form(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    """Look up an idea's proof by its link, id or fingerprint."""
    if not q.strip():
        return render(request, "verify.html", {"q": "", "verification": None}, user=user)
    proof = find_proof(db, q)
    if proof is None:
        return render(
            request,
            "verify.html",
            {"q": q, "verification": None, "not_found": True},
            user=user,
        )
    return render(
        request, "verify.html", {"q": q, "verification": verify(db, proof)}, user=user
    )


@router.post("/verify")
async def verify_bundle(
    request: Request,
    bundle: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    """Advanced: check a proof bundle that someone downloaded earlier."""
    if bundle is None or not bundle.filename:
        return RedirectResponse("/verify?err=Choose+a+proof+bundle+to+check", status_code=303)
    raw = await bundle.read()
    try:
        parsed = json.loads(raw.decode("utf-8"))
        receipt = parsed["receipt"]
        canonical = parsed["canonical_payload"]
        claimed = receipt["content_hash"]
        idea_id = receipt.get("idea_id", "")
    except (json.JSONDecodeError, KeyError, UnicodeDecodeError, TypeError):
        return render(
            request,
            "verify.html",
            {
                "q": "",
                "verification": Verification(
                    ok=False,
                    checks=[Check("Bundle is readable", "fail", "This is not a valid proof bundle.")],
                ),
            },
            user=user,
        )

    recomputed = sha256_text(canonical)
    checks = [
        Check(
            "Content matches its fingerprint",
            "pass" if recomputed == claimed else "fail",
            f"recomputed {recomputed[:16]}… and the bundle claims {claimed[:16]}…",
        )
    ]
    stored = db.scalar(select(IdeaProof).where(IdeaProof.idea_id == idea_id))
    if stored is not None and stored.content_hash == claimed:
        result = verify(db, stored)
        result.checks = checks + result.checks
        result.ok = result.ok and checks[0].state == "pass"
        return render(request, "verify.html", {"q": "", "verification": result}, user=user)
    checks.append(Check("Registered on UniteIdeas", "fail", "No matching record on this site."))
    return render(
        request,
        "verify.html",
        {"q": "", "verification": Verification(ok=False, checks=checks)},
        user=user,
    )


@router.get("/profile")
def profile(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    my_ideas = db.scalars(
        select(Idea).where(Idea.owner_id == user.id).order_by(desc(Idea.created_at))
    ).all()
    my_joins = db.scalars(
        select(JoinRequest).where(JoinRequest.user_id == user.id)
    ).all()
    my_memberships = db.scalars(
        select(TeamMember).where(TeamMember.user_id == user.id)
    ).all()
    join_ideas = {j.idea_id: db.get(Idea, j.idea_id) for j in my_joins}
    member_ideas = {m.idea_id: db.get(Idea, m.idea_id) for m in my_memberships}
    pledged = sum(m.pledged_hours_per_day for m in my_memberships)
    return render(
        request,
        "profile.html",
        {
            "my_ideas": my_ideas,
            "my_joins": my_joins,
            "my_memberships": my_memberships,
            "join_ideas": join_ideas,
            "member_ideas": member_ideas,
            "pledged_total": pledged,
        },
        user=user,
    )


@router.get("/onboarding")
def onboarding(request: Request, user: User = Depends(require_user)):
    return render(request, "onboarding.html", {}, user=user)


@router.post("/onboarding/complete")
def onboarding_complete(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    user.onboarding_done = True
    db.add(user)
    db.commit()
    return RedirectResponse("/?msg=Welcome+aboard", status_code=303)
