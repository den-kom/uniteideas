"""Magic-link authentication: no passwords, one-time links by email."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import mailer
from app.config import get_settings
from app.db import get_db
from app.models import ROLE_ADMIN, ROLE_USER, User
from app.security import (
    SESSION_COOKIE,
    consume_login_token,
    create_login_token,
    current_user,
    issue_session,
)
from app.templating import render

router = APIRouter()


@router.get("/login")
def login_form(request: Request, user: User | None = Depends(current_user)):
    if user is not None:
        return RedirectResponse("/profile", status_code=303)
    return render(request, "login.html", {}, user=None)


@router.post("/login")
def login_request(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(default=""),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    clean_email = email.strip().lower()
    if "@" not in clean_email or len(clean_email) < 5:
        return RedirectResponse("/login?err=Enter+a+valid+email+address", status_code=303)

    token = create_login_token(db, clean_email)
    link = f"{settings.public_base_url}/auth/verify?token={quote(token)}"
    if display_name.strip():
        link += f"&display_name={quote(display_name.strip())}"

    mailer.send(
        clean_email,
        "Your UniteIdeas sign-in link",
        f"Click to sign in (valid {settings.magic_link_ttl_minutes} minutes):\n\n{link}\n",
    )
    return render(
        request,
        "login_sent.html",
        {
            "email": clean_email,
            "dev_link": link if settings.dev_show_magic_link else None,
        },
        user=None,
    )


@router.get("/auth/verify")
def verify(
    request: Request,
    token: str,
    display_name: str = "",
    db: Session = Depends(get_db),
):
    email = consume_login_token(db, token)
    if email is None:
        return RedirectResponse("/login?err=That+link+is+invalid+or+expired", status_code=303)

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        is_first = db.scalar(select(func.count(User.id))) == 0
        user = User(
            email=email,
            display_name=(display_name.strip() or email.split("@")[0])[:80],
            role=ROLE_ADMIN if is_first else ROLE_USER,
        )
        db.add(user)
        db.commit()

    target = "/" if user.onboarding_done else "/onboarding"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(user.id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/?msg=Signed+out", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
