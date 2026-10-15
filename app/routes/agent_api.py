"""Scoped API for AgentBob.

Today this only answers a ping, so AgentBob can confirm its token works and who it acts as.
The old proof-of-concept build queue was removed with the old POC builder. New endpoints
(moderation triage, similarity suggestions, health) are added here when AgentBob gets those jobs.
Everything AgentBob does should be recorded under its own account (user-agentbob).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User
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
