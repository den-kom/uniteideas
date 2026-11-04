"""Scoped API for AgentBob.

AgentBob is the site's moderation assistant. Its whole reach is: ping, take items to look at, confirm
or escalate them, and flag an idea for a moderator. It cannot reject, remove, approve something a
rule or person already held, read sealed text, or manage accounts. Everything it does is recorded
under its own account (user-agentbob).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app import screening
from app import audit
from app.models import Idea, Report, ScreenItem, User
from app.system_users import AGENTBOB_ID

router = APIRouter(prefix="/api/agent")


def require_agent(authorization: str | None = Header(default=None)) -> User:
    """Bearer-token check. Returns nothing sensitive; the token is compared in constant time."""
    settings = get_settings()
    if not settings.agent_api_configured:
        raise HTTPException(status_code=503, detail="AGENT_API_TOKEN not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, settings.agent_api_token or ""):
        raise HTTPException(status_code=403, detail="invalid token")
    return None  # type: ignore[return-value]


@router.get("/ping")
def ping(db: Session = Depends(get_db), _: None = Depends(require_agent)) -> dict:
    bot = db.get(User, AGENTBOB_ID)
    return {
        "ok": True,
        "agent": bot.display_name if bot else None,
        "user_id": bot.id if bot else None,
    }


@router.get("/screen/next")
def screen_next(db: Session = Depends(get_db), _: None = Depends(require_agent)) -> dict:
    """The oldest item nobody has checked yet. Returns {"item": null} when the queue is empty.

    Ideas are sent as title, summary and public text only. Sealed text is never sent.
    """
    item = db.scalar(
        select(ScreenItem).where(ScreenItem.status == "pending").order_by(ScreenItem.created_at).limit(1)
    )
    if item is None:
        return {"item": None}
    return {"item": {"id": item.id, "kind": item.kind, "text": item.text, "created_at": item.created_at.isoformat()}}


class Decision(BaseModel):
    verdict: str  # "approved" or "escalated"
    reason: str = ""


@router.post("/screen/{item_id}/decide")
def screen_decide(
    item_id: str,
    body: Decision,
    db: Session = Depends(get_db),
    _: None = Depends(require_agent),
) -> dict:
    """AgentBob approves clean items and escalates anything it is unsure about. It cannot reject."""
    item = db.get(ScreenItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="no such item")
    bot = db.get(User, AGENTBOB_ID)
    if bot is None or not screening.apply(db, item, body.verdict, body.reason, bot, by_agent=True):
        raise HTTPException(status_code=409, detail="decision not allowed")
    db.commit()
    return {"ok": True, "status": item.status}


class Flag(BaseModel):
    idea_id: str
    reason: str


@router.post("/flag")
def flag_idea(
    body: Flag,
    db: Session = Depends(get_db),
    _: None = Depends(require_agent),
) -> dict:
    """AgentBob reports an idea to the moderators, like a member's report. A person decides."""
    bot = db.get(User, AGENTBOB_ID)
    idea = db.get(Idea, body.idea_id)
    reason = body.reason.strip()[:2000]
    if bot is None or idea is None or not reason:
        raise HTTPException(status_code=404, detail="no such idea, or no reason given")
    already = db.scalar(
        select(Report.id).where(Report.idea_id == idea.id, Report.reporter_id == bot.id, Report.status == "open")
    )
    if already:
        return {"ok": True, "report_id": already, "duplicate": True}
    report = Report(idea_id=idea.id, reporter_id=bot.id, reason=reason)
    db.add(report)
    audit.record(db, bot, "agent.flag", "idea", idea.id, reason[:200])
    db.commit()
    return {"ok": True, "report_id": report.id, "duplicate": False}
