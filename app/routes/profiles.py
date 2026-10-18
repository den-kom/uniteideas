"""Profiles: the sign-up questionnaire, editing, and the public member page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Idea, User, UserSkill
from app.routes.pages import _my_votes
from app.security import current_user, require_user
from app import screening
from app.skills import (
    GOALS,
    SKILL_GROUPS,
    SKILL_LABELS,
    catalogue_json,
    clean_custom_skills,
    clean_goals,
    clean_skills,
)
from app.templating import render

router = APIRouter()


@router.get("/profile/edit")
def edit_form(request: Request, welcome: int = 0, user: User = Depends(require_user)):
    return render(
        request,
        "profile_edit.html",
        {
            "welcome": bool(welcome) and not user.profile_done,
            "skill_groups": SKILL_GROUPS,
            "goals": GOALS,
            "catalogue": catalogue_json(),
            "selected_skills": [
                {"slug": s.skill, "label": s.text if s.is_custom else SKILL_LABELS.get(s.skill, s.skill),
                 "custom": s.is_custom, "status": s.status}
                for s in user.skills
            ],
            "my_skills": set(user.skill_slugs),
            "my_goals": set(user.goal_slugs),
        },
        user=user,
    )


@router.post("/profile/edit")
async def edit_save(
    request: Request,
    display_name: str = Form(...),
    headline: str = Form(default=""),
    bio: str = Form(default=""),
    location: str = Form(default=""),
    hours_per_week: int = Form(default=0),
    profile_public: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    form = await request.form()
    name = display_name.strip()[:80]
    if len(name) < 2:
        return RedirectResponse("/profile/edit?err=Please+enter+a+name+others+can+see", status_code=303)

    from app.config import get_settings

    cap = get_settings().max_pledge_hours_per_week
    first_time = not user.profile_done
    user.display_name = name
    user.headline = headline.strip()[:120]
    user.bio = bio.strip()[:1200]
    user.location = location.strip()[:80]
    user.hours_per_week = max(0, min(cap, hours_per_week))
    user.goals = ",".join(clean_goals(form.getlist("goals")))
    user.profile_public = bool(profile_public)
    user.profile_done = True

    chosen = clean_skills(form.getlist("skills"))
    custom = [f"custom:{t}" for t in clean_custom_skills(form.getlist("custom_skills"))]
    wanted = set(chosen) | set(custom)
    existing = {s.skill: s for s in user.skills}
    for slug, row in existing.items():
        if slug not in wanted:
            db.delete(row)
    for slug in chosen:
        if slug not in existing:
            db.add(UserSkill(user_id=user.id, skill=slug))
    for slug in custom:
        if slug not in existing:
            row = UserSkill(user_id=user.id, skill=slug, status="pending")
            db.add(row)
            user.skills.append(row)
            screening.queue_skill(db, user, slug.removeprefix("custom:"))
    db.add(user)
    db.commit()
    if first_time and not user.onboarding_done:
        return RedirectResponse("/onboarding?msg=Profile+saved", status_code=303)
    return RedirectResponse("/profile?msg=Profile+saved", status_code=303)


@router.get("/u/{user_id}")
def public_profile(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(current_user),
):
    member = db.get(User, user_id)
    visible = member is not None and member.is_active and (
        member.profile_public or (viewer and (viewer.id == member.id or viewer.is_staff))
    )
    if not visible:
        return render(request, "not_found.html", {}, user=viewer, status_code=404)
    ideas = db.scalars(
        select(Idea)
        .where(Idea.owner_id == member.id, Idea.status == "published")
        .order_by(desc(Idea.score), desc(Idea.created_at))
        .limit(20)
    ).all()
    return render(
        request,
        "public_profile.html",
        {
            "member": member,
            "ideas": ideas,
            "my_votes": _my_votes(db, viewer, ideas),
            "skill_labels": SKILL_LABELS,
            "goals": GOALS,
            "is_self": bool(viewer and viewer.id == member.id),
        },
        user=viewer,
    )
