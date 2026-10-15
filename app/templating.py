"""Shared Jinja setup and a render helper that injects common context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.models import User
from app.seo import absolute, is_private_path, jsonld, organization

ROOT = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))
templates.env.globals["jsonld"] = jsonld
templates.env.globals["site_jsonld"] = organization


def render(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    *,
    user: User | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    ctx: dict[str, Any] = {
        "user": user,
        "msg": request.query_params.get("msg"),
        "err": request.query_params.get("err"),
        "settings": get_settings(),
        # Search engines: where this page lives, and whether it may be listed.
        "canonical_url": absolute(request.url.path),
        "noindex": status_code >= 400 or is_private_path(request.url.path),
        "og_image": absolute("/static/og-image.png"),
    }
    ctx.update(context or {})
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
