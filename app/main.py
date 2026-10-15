"""UniteIdeas.org — application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app import timestamping
from app.db import SessionLocal, init_db
from app.routes import admin, agent_api, auth, content, ideas, moderation, pages, profiles, teams
from app.seo import is_private_path
from app.templating import render

logging.basicConfig(level=logging.INFO)
ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.outbox_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    worker = asyncio.create_task(timestamping.worker_loop(SessionLocal))
    try:
        yield
    finally:
        worker.cancel()


app = FastAPI(title="UniteIdeas", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")

app.add_middleware(GZipMiddleware, minimum_size=600)


@app.middleware("http")
async def headers(request: Request, call_next):
    """Cache static files, and keep private areas out of search results at the HTTP level too."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    if is_private_path(path):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(content.router)
app.include_router(profiles.router)
app.include_router(ideas.router)
app.include_router(teams.router)
app.include_router(moderation.router)
app.include_router(admin.router)
app.include_router(agent_api.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    wants_html = "text/html" in (request.headers.get("accept") or "")
    if exc.status_code == 401 and wants_html:
        return RedirectResponse("/login?err=Please+sign+in+first", status_code=303)
    if exc.status_code in {403, 404} and wants_html:
        return render(
            request,
            "error.html",
            {"code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )
    from fastapi.responses import JSONResponse

    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "uniteideas", "version": "0.2.0"}
