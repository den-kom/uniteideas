"""Scoped API for the Agent System. UniteIdeas owns the queue; agents pull work."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import (
    BUILD_QUEUED,
    BUILD_STATUSES,
    Idea,
    PocBuild,
    User,
    utc_now,
)
from app.sealing import unseal

router = APIRouter(prefix="/api/agent")


def require_agent(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.agent_api_configured:
        raise HTTPException(status_code=503, detail="AGENT_API_TOKEN not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    if authorization.removeprefix("Bearer ").strip() != settings.agent_api_token:
        raise HTTPException(status_code=403, detail="invalid token")


class BuildUpdate(BaseModel):
    status: str
    notes: str = ""
    preview_url: str = ""
    claim: bool = Field(default=False, description="Mark this job as claimed")


@router.get("/queue")
def queue(
    limit: int = 5,
    db: Session = Depends(get_db),
    _: None = Depends(require_agent),
) -> dict:
    builds = db.scalars(
        select(PocBuild)
        .where(PocBuild.status == BUILD_QUEUED)
        .order_by(PocBuild.created_at)
        .limit(max(1, min(limit, 20)))
    ).all()
    jobs = []
    for build in builds:
        idea = db.get(Idea, build.idea_id)
        if idea is None:
            continue
        owner = db.get(User, idea.owner_id)
        jobs.append(
            {
                "build_id": build.id,
                "idea_id": idea.id,
                "title": idea.title,
                "summary": idea.summary,
                "category": idea.category,
                "idea_type": idea.idea_type,
                "public_body": idea.public_body,
                "sealed_detail": unseal(idea.sealed_blob) if idea.sealed_blob else "",
                "owner_display": owner.display_name if owner else "unknown",
                "attachments": [
                    {
                        "id": a.id,
                        "filename": a.filename,
                        "content_type": a.content_type,
                        "sha256": a.sha256,
                        "path": a.stored_path,
                    }
                    for a in idea.attachments
                ],
                "created_at": build.created_at.isoformat(),
            }
        )
    return {"count": len(jobs), "jobs": jobs}


@router.post("/builds/{build_id}")
def update_build(
    build_id: str,
    body: BuildUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_agent),
) -> dict:
    build = db.get(PocBuild, build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="build not found")
    if body.status not in BUILD_STATUSES:
        raise HTTPException(
            status_code=422, detail=f"status must be one of {list(BUILD_STATUSES)}"
        )
    build.status = body.status
    if body.notes:
        build.notes = body.notes[:8000]
    if body.preview_url:
        build.preview_url = body.preview_url[:300]
    if body.claim and build.claimed_at is None:
        build.claimed_at = utc_now()
    build.updated_at = utc_now()
    db.add(build)
    db.commit()
    return {
        "build_id": build.id,
        "idea_id": build.idea_id,
        "status": build.status,
        "preview_url": build.preview_url,
        "is_public": build.is_public,
    }
