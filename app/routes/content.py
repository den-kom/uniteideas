"""Static content pages: legal, and (later) about and help pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.config import LEGAL_UPDATED, LEGAL_VERSION
from app.models import User
from app.security import current_user
from app.templating import render

router = APIRouter()

LEGAL = {"legal_version": LEGAL_VERSION, "legal_updated": LEGAL_UPDATED}


@router.get("/terms")
def terms(request: Request, user: User | None = Depends(current_user)):
    return render(request, "terms.html", LEGAL, user=user)


@router.get("/privacy")
def privacy(request: Request, user: User | None = Depends(current_user)):
    return render(request, "privacy.html", LEGAL, user=user)


@router.get("/community-rules")
def community_rules(request: Request, user: User | None = Depends(current_user)):
    return render(request, "community_rules.html", LEGAL, user=user)
