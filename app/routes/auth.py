"""Magic-link authentication: no passwords, one-time links by email."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, mailer, ratelimit
from app.passwords import hash_password, problem_with, verify_password
from app.config import LEGAL_VERSION, base_url_for, get_settings
from app.db import get_db
from app.models import ROLE_ADMIN, ROLE_BOT, ROLE_USER, User, utc_now
from app.system_users import is_system_email
from app.security import (
    SESSION_COOKIE,
    require_user,
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

    if is_system_email(clean_email):
        return RedirectResponse("/login?err=That+address+cannot+sign+in", status_code=303)

    ip = ratelimit.client_ip(request)
    wait = max(
        ratelimit.retry_after(db, "login_ip", ip),
        ratelimit.retry_after(db, "login_email", clean_email),
    )
    if wait:
        return RedirectResponse(
            f"/login?err=Too+many+sign-in+requests.+Try+again+in+{quote(ratelimit.human_wait(wait))}",
            status_code=303,
        )
    ratelimit.record(db, "login_ip", ip)
    ratelimit.record(db, "login_email", clean_email)
    ratelimit.sweep(db)
    db.commit()

    token = create_login_token(db, clean_email)
    link = f"{base_url_for(request)}/auth/verify?token={quote(token)}"
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
    ip = ratelimit.client_ip(request)
    wait = ratelimit.retry_after(db, "verify_ip", ip)
    if wait:
        return RedirectResponse(
            f"/login?err=Too+many+attempts.+Try+again+in+{quote(ratelimit.human_wait(wait))}",
            status_code=303,
        )
    email = consume_login_token(db, token)
    if email is None:
        ratelimit.record(db, "verify_ip", ip)
        db.commit()
        return RedirectResponse("/login?err=That+link+is+invalid+or+expired", status_code=303)

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        is_first = (
            db.scalar(select(func.count(User.id)).where(User.role != ROLE_BOT)) == 0
        )
        user = User(
            email=email,
            display_name=(display_name.strip() or email.split("@")[0])[:80],
            role=ROLE_ADMIN if is_first else ROLE_USER,
            terms_version=LEGAL_VERSION,
            terms_accepted_at=utc_now(),
        )
        db.add(user)
        db.commit()

    if not user.is_active:
        return RedirectResponse("/login?err=This+account+is+suspended", status_code=303)
    if not user.terms_version:  # account made by an admin: terms are accepted at first sign-in
        user.terms_version = LEGAL_VERSION
        user.terms_accepted_at = utc_now()
        db.commit()
    return _start_session(user)


def _start_session(user: User) -> RedirectResponse:
    if not user.profile_done:
        target = "/profile/edit?welcome=1"
    else:
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


@router.post("/login/password")
def login_password(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    clean_email = email.strip().lower()
    ip = ratelimit.client_ip(request)
    wait = max(
        ratelimit.retry_after(db, "password_fail", clean_email),
        ratelimit.retry_after(db, "password_fail_ip", ip),
    )
    if wait:
        return RedirectResponse(
            f"/login?err=Too+many+wrong+passwords.+Try+again+in+{quote(ratelimit.human_wait(wait))}",
            status_code=303,
        )
    user = db.scalar(select(User).where(User.email == clean_email))
    stored = user.password_hash if user and not is_system_email(clean_email) else None
    ok = verify_password(password, stored)
    if not ok or user is None:
        ratelimit.record(db, "password_fail", clean_email)
        ratelimit.record(db, "password_fail_ip", ip)
        db.commit()
        return RedirectResponse(
            "/login?err=Email+or+password+is+not+right.+You+can+always+use+the+emailed+link+instead",
            status_code=303,
        )
    if not user.is_active:
        return RedirectResponse("/login?err=This+account+is+suspended", status_code=303)
    ratelimit.clear(db, "password_fail", clean_email)
    if not user.terms_version:
        user.terms_version = LEGAL_VERSION
        user.terms_accepted_at = utc_now()
    db.commit()
    return _start_session(user)


@router.get("/profile/password")
def password_form(request: Request, user: User = Depends(require_user)):
    return render(request, "password.html", {"has_password": bool(user.password_hash)}, user=user)


@router.post("/profile/password")
def password_save(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_password: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if user.password_hash:
        wait = ratelimit.retry_after(db, "password_fail", user.email)
        if wait:
            return RedirectResponse(
                f"/profile/password?err=Too+many+wrong+attempts.+Try+again+in+{quote(ratelimit.human_wait(wait))}",
                status_code=303,
            )
        if not verify_password(current_password, user.password_hash):
            ratelimit.record(db, "password_fail", user.email)
            db.commit()
            return RedirectResponse("/profile/password?err=Your+current+password+is+not+right", status_code=303)
    if new_password != confirm_password:
        return RedirectResponse("/profile/password?err=The+two+passwords+do+not+match", status_code=303)
    problem = problem_with(new_password)
    if problem:
        return RedirectResponse(f"/profile/password?err={quote(problem)}", status_code=303)
    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/profile/password?msg=Password+saved.+You+can+still+use+emailed+links", status_code=303)


@router.post("/profile/password/remove")
def password_remove(
    current_password: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if user.password_hash and not verify_password(current_password, user.password_hash):
        return RedirectResponse("/profile/password?err=Your+current+password+is+not+right", status_code=303)
    user.password_hash = None
    db.commit()
    return RedirectResponse("/profile/password?msg=Password+removed.+Sign+in+with+emailed+links", status_code=303)


@router.post("/logout")
def logout():
    response = RedirectResponse("/?msg=Signed+out", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
