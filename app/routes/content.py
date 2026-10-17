"""Static content pages: legal, and (later) about and help pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import seo
from app.config import LEGAL_UPDATED, LEGAL_VERSION
from app.db import get_db
from app.models import Idea, User
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


FAQ = [
    (
        "Is my idea safe if I post it here?",
        "You decide how much to show. The public one-pager is visible to everyone. The sealed detail is encrypted and only you, "
        "the team members you approve, and (if you choose to reveal it) everyone can read it. Nothing stops a reader copying what is public, "
        "which is why every submission gets a timestamped receipt showing when you shared it.",
    ),
    (
        "What is a proof receipt?",
        "When you submit an idea we compute a fingerprint of its content and record the time. You can download a receipt, and anyone can check "
        "it on the verify page without seeing your sealed text.",
    ),
    (
        "How does the public timestamp work?",
        "The fingerprint, and only the fingerprint, is sent to public timestamp servers that write it into the Bitcoin blockchain. "
        "Confirmation usually takes a few hours. After that anyone can check it without trusting UniteIdeas.",
    ),
    (
        "Does a receipt replace a patent?",
        "No. A receipt is evidence that specific content existed by a certain time. It is not a patent, copyright registration or any other legal right. "
        "If a patent matters to you, get professional advice before you publish anything.",
    ),
    (
        "What does sealed detail mean?",
        "It is a private section of your idea, such as dimensions, materials, algorithms or business model. It is encrypted when stored. "
        "Only its fingerprint is part of your public proof, so you can show later that this exact text existed on the day you submitted.",
    ),
    (
        "Who can see my sealed detail?",
        "You and the team members you approve. Moderators can open it only to review a report or a first submission, and each view is recorded in a log they cannot edit.",
    ),
    (
        "How do teams work?",
        "People ask to join an idea and say how many hours a week they can give. The idea's owner approves who joins. "
        "Members should agree between themselves who owns what they build.",
    ),
    (
        "How does voting work?",
        "Signed-in members can upvote or downvote an idea. The net score decides what rises to the top.",
    ),
    (
        "What do the robots do?",
        "AgentBob is the site's robot assistant. It helps with housekeeping such as flagging content for moderators, suggesting similar ideas or possible teammates, "
        "and keeping the site running. People make the final decisions.",
    ),
    (
        "What are Unite Ideas and Unite Talent?",
        "Two features we are building. Unite Ideas spots ideas that overlap and suggests combining or branching them. "
        "Unite Talent suggests teammates whose skills fit an idea. Both are coming soon.",
    ),
    (
        "Does it cost anything?",
        "Joining, sharing ideas, voting and verifying are free today.",
    ),
    (
        "How do I report a problem or close my account?",
        "Use the report button on an idea, or write to us using the contact page. To close your account and delete your details, write to us from the email you signed up with.",
    ),
]


@router.get("/how-it-works")
def how_it_works(request: Request, user: User | None = Depends(current_user)):
    return render(request, "how_it_works.html", {}, user=user)


@router.get("/about")
def about(request: Request, user: User | None = Depends(current_user)):
    return render(request, "about.html", {}, user=user)


@router.get("/faq")
def faq(request: Request, user: User | None = Depends(current_user)):
    return render(
        request,
        "faq.html",
        {"faq": FAQ, "faq_jsonld": seo.faq_schema(FAQ)},
        user=user,
    )


@router.get("/contact")
def contact(request: Request, user: User | None = Depends(current_user)):
    return render(request, "contact.html", {}, user=user)


@router.get("/categories")
def categories(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user),
):
    rows = db.execute(
        select(Idea.category, func.count(Idea.id))
        .where(Idea.status == "published")
        .group_by(Idea.category)
        .order_by(func.count(Idea.id).desc(), Idea.category)
    ).all()
    return render(
        request,
        "categories.html",
        {"rows": [(c, n) for c, n in rows if c]},
        user=user,
    )


@router.get("/robots.txt", include_in_schema=False)
def robots() -> PlainTextResponse:
    return PlainTextResponse(seo.robots_txt())


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap(db: Session = Depends(get_db)) -> Response:
    return Response(seo.sitemap_xml(db), media_type="application/xml")


@router.get("/unite-ideas")
def unite_ideas(request: Request, user: User | None = Depends(current_user)):
    return render(request, "unite_ideas.html", {}, user=user)


@router.get("/unite-talent")
def unite_talent(request: Request, user: User | None = Depends(current_user)):
    return render(request, "unite_talent.html", {}, user=user)
