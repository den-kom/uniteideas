"""Search-engine helpers: which pages are private, structured data, the sitemap."""

from __future__ import annotations

import json
from datetime import datetime
from xml.sax.saxutils import escape

from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Idea, User

# Pages that should never appear in search results.
PRIVATE_PREFIXES = (
    "/login",
    "/auth",
    "/logout",
    "/submit",
    "/profile",
    "/onboarding",
    "/admin",
    "/moderation",
    "/api",
    "/files",
    "/joins",
    "/reports",
)

STATIC_PAGES = (
    ("/", "daily", "1.0"),
    ("/ideas", "daily", "0.9"),
    ("/how-it-works", "monthly", "0.8"),
    ("/categories", "weekly", "0.6"),
    ("/link-ideas", "monthly", "0.5"),
    ("/connect-teams", "monthly", "0.5"),
    ("/verify", "monthly", "0.6"),
    ("/about", "monthly", "0.5"),
    ("/faq", "monthly", "0.6"),
    ("/contact", "yearly", "0.3"),
    ("/terms", "yearly", "0.3"),
    ("/privacy", "yearly", "0.3"),
    ("/community-rules", "yearly", "0.3"),
)


def is_private_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PRIVATE_PREFIXES)


def absolute(path: str) -> str:
    return get_settings().public_base_url.rstrip("/") + path


def jsonld(data: dict | list) -> Markup:
    """A JSON-LD script tag. Escapes `</` so content can never close the tag early."""
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return Markup(f'<script type="application/ld+json">{body}</script>')


def organization() -> dict:
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": absolute("/#org"),
                "name": "UniteIdeas",
                "url": absolute("/"),
                "logo": absolute("/static/logo.png"),
            },
            {
                "@type": "WebSite",
                "@id": absolute("/#site"),
                "name": "UniteIdeas",
                "url": absolute("/"),
                "publisher": {"@id": absolute("/#org")},
            },
        ],
    }


def idea_schema(idea: Idea, author: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "CreativeWork",
        "name": idea.title,
        "description": idea.summary,
        "url": absolute(f"/ideas/{idea.id}"),
        "author": {"@type": "Person", "name": author},
        "datePublished": (idea.published_at or idea.created_at).date().isoformat(),
        "dateModified": idea.updated_at.date().isoformat(),
        "genre": idea.category,
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": "https://schema.org/LikeAction",
            "userInteractionCount": idea.score,
        },
    }


def faq_schema(items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in items
        ],
    }


def _url(loc: str, lastmod: datetime | None = None, freq: str = "weekly", priority: str = "0.5") -> str:
    parts = [f"<loc>{escape(absolute(loc))}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{lastmod.date().isoformat()}</lastmod>")
    parts.append(f"<changefreq>{freq}</changefreq><priority>{priority}</priority>")
    return "<url>" + "".join(parts) + "</url>"


def sitemap_xml(db: Session, limit: int = 5000) -> str:
    urls = [_url(path, None, freq, prio) for path, freq, prio in STATIC_PAGES]
    categories = sorted({c for c in db.scalars(select(Idea.category).where(Idea.status == "published")) if c})
    for c in categories:
        urls.append(_url(f"/ideas?category={c.replace(' ', '%20')}", None, "weekly", "0.5"))
    ideas = db.scalars(
        select(Idea).where(Idea.status == "published").order_by(Idea.updated_at.desc()).limit(limit)
    ).all()
    for idea in ideas:
        urls.append(_url(f"/ideas/{idea.id}", idea.updated_at, "weekly", "0.7"))
    # Members appear only if they chose a public profile and have published something.
    authors = db.scalars(
        select(User)
        .where(User.profile_public.is_(True), User.is_active.is_(True), User.id.in_({i.owner_id for i in ideas}))
        .limit(limit)
    ).all()
    for member in authors:
        urls.append(_url(f"/u/{member.id}", None, "monthly", "0.4"))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(urls) + "</urlset>"
    )


def robots_txt() -> str:
    lines = ["User-agent: *"]
    lines += [f"Disallow: {p}" for p in PRIVATE_PREFIXES if p not in ("/logout",)]
    lines += ["Allow: /", "", f"Sitemap: {absolute('/sitemap.xml')}", ""]
    return "\n".join(lines)
