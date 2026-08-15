"""UniteIdeas.org — application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.routes import agent_api, auth, ideas, moderation, pages, teams
from app.templating import render

logging.basicConfig(level=logging.INFO)
ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.outbox_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="UniteIdeas", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(ideas.router)
app.include_router(teams.router)
app.include_router(moderation.router)
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
