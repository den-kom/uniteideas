"""Submitting ideas, proofs, voting, sealed reveal, and POC requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import ALLOWED_UPLOAD_TYPES, MAX_UPLOAD_BYTES, get_settings
from app.db import get_db
from app.models import (
    Attachment,
    BUILD_DEMO_READY,
    BUILD_QUEUED,
    Idea,
    IdeaProof,
    PocBuild,
    STATUS_PENDING,
    STATUS_PUBLISHED,
    TeamMember,
    User,
    Vote,
    short_id,
    utc_now,
)
from app.proof import build_receipt, compute_content_hash, sha256_bytes, sha256_text
from app.sealing import seal, unseal
from app.security import current_user, require_user
from app.templating import render

router = APIRouter()

SUGGESTED_CATEGORIES = [
    "home",
    "health",
    "pets",
    "productivity",
    "developer tools",
    "education",
    "sustainability",
    "accessibility",
]


@router.get("/submit")
def submit_form(request: Request, user: User = Depends(require_user)):
    return render(
        request,
        "submit.html",
        {"categories": SUGGESTED_CATEGORIES},
        user=user,
    )


@router.post("/submit")
async def submit_idea(
    request: Request,
    title: str = Form(...),
    summary: str = Form(...),
    category: str = Form(default="general"),
    idea_type: str = Form(default="digital"),
    public_body: str = Form(default=""),
    sealed_detail: str = Form(default=""),
    attachment: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    settings = get_settings()
    title = title.strip()
    summary = summary.strip()
    if len(title) < 3:
        return RedirectResponse("/submit?err=Title+is+too+short", status_code=303)
    if len(summary) < 10:
        return RedirectResponse(
            "/submit?err=Write+a+one-line+summary+of+at+least+10+characters",
            status_code=303,
        )
    if idea_type not in {"digital", "physical"}:
        idea_type = "digital"

    idea_id = short_id("idea")
    stored_files: list[tuple[str, str, str, int, str]] = []

    if attachment is not None and attachment.filename:
        raw = await attachment.read()
        if len(raw) > MAX_UPLOAD_BYTES:
            return RedirectResponse("/submit?err=Attachment+is+larger+than+10MB", status_code=303)
        suffix = ALLOWED_UPLOAD_TYPES.get(attachment.content_type or "")
        if suffix is None:
            return RedirectResponse(
                "/submit?err=Attachment+must+be+PDF,+PNG+or+JPEG", status_code=303
            )
        target_dir = settings.upload_dir / idea_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(
            c for c in (attachment.filename or "upload") if c.isalnum() or c in "-_. "
        )[:120]
        path = target_dir / (safe_name or f"upload{suffix}")
        path.write_bytes(raw)
        stored_files.append(
            (
                safe_name or f"upload{suffix}",
                str(path),
                attachment.content_type or "application/octet-stream",
                len(raw),
                sha256_bytes(raw),
            )
        )

    content_hash, canonical = compute_content_hash(
        title=title,
        summary=summary,
        category=category,
        idea_type=idea_type,
        public_body=public_body,
        sealed_detail=sealed_detail,
        attachment_hashes=[f[4] for f in stored_files],
    )

    # First-ever submission from an account is held for review; after that the
    # account is trusted and posts go live immediately.
    published_before = (
        db.scalar(
            select(func.count(Idea.id)).where(
                Idea.owner_id == user.id, Idea.status == STATUS_PUBLISHED
            )
        )
        or 0
    )
    status = STATUS_PUBLISHED if published_before else STATUS_PENDING

    idea = Idea(
        id=idea_id,
        owner_id=user.id,
        title=title,
        summary=summary,
        category=(category.strip().lower() or "general")[:80],
        idea_type=idea_type,
        public_body=public_body.strip(),
        sealed_blob=seal(sealed_detail),
        status=status,
        published_at=utc_now() if status == STATUS_PUBLISHED else None,
    )
    db.add(idea)
    db.add(
        IdeaProof(
            idea_id=idea_id,
            content_hash=content_hash,
            author_email_hash=sha256_text(user.email.lower()),
        )
    )
    for name, path_str, ctype, size, digest in stored_files:
        db.add(
            Attachment(
                idea_id=idea_id,
                filename=name,
                stored_path=path_str,
                content_type=ctype,
                size_bytes=size,
                sha256=digest,
            )
        )
    db.commit()
    note = (
        "Idea+submitted+and+timestamped"
        if status == STATUS_PUBLISHED
        else "Idea+submitted+and+timestamped.+Your+first+post+is+awaiting+a+moderator+review"
    )
    return RedirectResponse(f"/ideas/{idea_id}?msg={note}", status_code=303)


@router.post("/ideas/{idea_id}/vote")
def vote(
    idea_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    idea = db.get(Idea, idea_id)
    if idea is None or idea.status != "published":
        return RedirectResponse("/ideas?err=Idea+not+found", status_code=303)
    db.add(Vote(idea_id=idea_id, user_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"/ideas/{idea_id}?err=You+have+already+backed+this+idea", status_code=303
        )
    idea.score = (idea.score or 0) + 1
    idea.updated_at = utc_now()
    db.add(idea)
    db.commit()
    return RedirectResponse(f"/ideas/{idea_id}?msg=Thanks+for+backing+this+idea", status_code=303)


@router.post("/ideas/{idea_id}/reveal")
def reveal_sealed(
    idea_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    idea = db.get(Idea, idea_id)
    if idea is None or idea.owner_id != user.id:
        return RedirectResponse("/profile?err=Not+your+idea", status_code=303)
    if not idea.sealed_blob:
        return RedirectResponse(f"/ideas/{idea_id}?err=Nothing+sealed+to+reveal", status_code=303)
    idea.sealed_revealed_at = utc_now()
    db.add(idea)
    db.commit()
    return RedirectResponse(
        f"/ideas/{idea_id}?msg=Sealed+detail+is+now+public", status_code=303
    )


@router.get("/ideas/{idea_id}/proof-bundle.json")
def proof_bundle(idea_id: str, db: Session = Depends(get_db)):
    idea = db.get(Idea, idea_id)
    if idea is None or idea.proof is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    settings = get_settings()
    owner = db.get(User, idea.owner_id)
    sealed_plain = unseal(idea.sealed_blob) if idea.sealed_blob else ""
    _, canonical = compute_content_hash(
        title=idea.title,
        summary=idea.summary,
        category=idea.category,
        idea_type=idea.idea_type,
        public_body=idea.public_body,
        sealed_detail=sealed_plain,
        attachment_hashes=[a.sha256 for a in idea.attachments],
    )
    receipt = build_receipt(
        idea_id=idea.id,
        content_hash=idea.proof.content_hash,
        author_display=owner.display_name if owner else "unknown",
        author_email_hash=idea.proof.author_email_hash,
        created_at=idea.proof.created_at,
        anchor_provider=idea.proof.anchor_provider,
        anchor_reference=idea.proof.anchor_reference,
        verify_url=f"{settings.public_base_url}/verify",
    )
    return JSONResponse(
        {"receipt": receipt, "canonical_payload": canonical},
        headers={
            "Content-Disposition": f'attachment; filename="{idea.id}-proof-bundle.json"'
        },
    )


@router.post("/ideas/{idea_id}/request-poc")
def request_poc(
    idea_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    idea = db.get(Idea, idea_id)
    if idea is None or idea.owner_id != user.id:
        return RedirectResponse("/profile?err=Not+your+idea", status_code=303)
    active = [
        b
        for b in idea.builds
        if b.status not in {BUILD_DEMO_READY, "failed", "escalated"}
    ]
    if active:
        return RedirectResponse(
            f"/ideas/{idea_id}?err=A+POC+job+is+already+in+the+queue", status_code=303
        )
    db.add(PocBuild(idea_id=idea_id, status=BUILD_QUEUED))
    db.commit()
    return RedirectResponse(
        f"/ideas/{idea_id}?msg=POC+queued+for+the+Agent+System", status_code=303
    )


@router.post("/ideas/{idea_id}/demo-visibility")
def demo_visibility(
    idea_id: str,
    make_public: str = Form(default="1"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    idea = db.get(Idea, idea_id)
    if idea is None or idea.owner_id != user.id:
        return RedirectResponse("/profile?err=Not+your+idea", status_code=303)
    build = idea.latest_build
    if build is None:
        return RedirectResponse(f"/ideas/{idea_id}?err=No+demo+yet", status_code=303)
    build.is_public = make_public == "1"
    build.updated_at = utc_now()
    db.add(build)
    db.commit()
    state = "public" if build.is_public else "private"
    return RedirectResponse(f"/ideas/{idea_id}?msg=Demo+is+now+{state}", status_code=303)


@router.get("/files/{attachment_id}")
def download_attachment(
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    att = db.get(Attachment, attachment_id)
    if att is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    idea = db.get(Idea, att.idea_id)
    if idea is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    allowed = att.is_public or idea.sealed_is_public
    if not allowed and user is not None:
        allowed = (
            user.id == idea.owner_id
            or user.is_staff
            or db.scalar(
                select(TeamMember).where(
                    TeamMember.idea_id == idea.id, TeamMember.user_id == user.id
                )
            )
            is not None
        )
    if not allowed:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return FileResponse(att.stored_path, media_type=att.content_type, filename=att.filename)
