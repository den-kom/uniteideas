"""Sessions, magic-link tokens, and role checks."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import LoginToken, User, utc_now

SESSION_COOKIE = "ui_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="uniteideas-session")


def issue_session(user_id: str) -> str:
    return _serializer().dumps({"uid": user_id})


def read_session(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        data = _serializer().loads(raw, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_login_token(db: Session, email: str) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        LoginToken(
            email=email.strip().lower(),
            token_hash=hash_token(token),
            expires_at=utc_now() + timedelta(minutes=get_settings().magic_link_ttl_minutes),
        )
    )
    db.commit()
    return token


def consume_login_token(db: Session, token: str) -> str | None:
    """Return the email for a valid unused token, marking it used."""
    row = db.scalar(select(LoginToken).where(LoginToken.token_hash == hash_token(token)))
    if row is None or row.used_at is not None:
        return None
    if row.expires_at.replace(tzinfo=utc_now().tzinfo) < utc_now():
        return None
    row.used_at = utc_now()
    db.commit()
    return row.email


def current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    uid = read_session(request.cookies.get(SESSION_COOKIE))
    if not uid:
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        return None
    return user


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="login required")
    return user


def require_staff(user: User = Depends(require_user)) -> User:
    if not user.is_staff:
        raise HTTPException(status_code=403, detail="moderator access required")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin access required")
    return user
