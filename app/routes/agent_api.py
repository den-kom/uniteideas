"""Scoped API for AgentBob.

Today this only answers a ping, so AgentBob can confirm its token works and who it acts as.
The old proof-of-concept build queue was removed with the old POC builder. New endpoints
(moderation triage, similarity suggestions, health) are added here when AgentBob gets those jobs.
Everything AgentBob does should be recorded under its own account (user-agentbob).
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
from app.models import ScreenItem, User
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
