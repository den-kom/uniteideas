#!/usr/bin/env python
"""Create (or repair) two test accounts for trying the signed-in parts of the site.

  denis      regular member    denis@uniteideas.test
  admDenis   administrator     admdenis@uniteideas.test

Run it from the project folder on the server. It is safe to run again: existing accounts are
updated, not duplicated. There are no passwords. Sign in with the email address, and while
DEV_SHOW_MAGIC_LINK=true in .env the sign-in link appears on screen (no mail server needed).

  .venv/bin/python scripts/create_test_users.py
  .venv/bin/python scripts/create_test_users.py --user denis=me@example.com --admin admDenis=me+admin@example.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import LEGAL_VERSION  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import ROLE_ADMIN, ROLE_USER, User, utc_now  # noqa: E402


def upsert(db, name: str, email: str, role: str, headline: str) -> str:
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    created = user is None
    if created:
        user = User(email=email, display_name=name)
        db.add(user)
    user.display_name = name
    user.role = role
    user.is_active = True
    user.onboarding_done = True
    user.profile_done = True
    user.headline = user.headline or headline
    user.terms_version = LEGAL_VERSION
    user.terms_accepted_at = user.terms_accepted_at or utc_now()
    db.commit()
    return ("created" if created else "updated") + f" {name} <{email}> as {role}"


def parse(pair: str) -> tuple[str, str]:
    name, _, email = pair.partition("=")
    if not name or "@" not in email:
        raise SystemExit(f"expected NAME=EMAIL, got {pair!r}")
    return name, email


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default="denis=denis@uniteideas.test", help="regular member as NAME=EMAIL")
    ap.add_argument("--admin", default="admDenis=admdenis@uniteideas.test", help="administrator as NAME=EMAIL")
    args = ap.parse_args()

    init_db()
    with SessionLocal() as db:
        print(upsert(db, *parse(args.user), ROLE_USER, "Regular test account"))
        print(upsert(db, *parse(args.admin), ROLE_ADMIN, "Administrator test account"))
    print("Sign in at /login with either email. The sign-in link appears on screen while DEV_SHOW_MAGIC_LINK=true.")


if __name__ == "__main__":
    main()
