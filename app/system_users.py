"""Service accounts. AgentBob is a member of the site that cannot sign in.

It acts through the agent API (token), and its actions are recorded under this account so
people can always see what the robot did.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ROLE_BOT, User

BOT_DOMAIN = "@system.invalid"
AGENTBOB_ID = "user-agentbob"
AGENTBOB_EMAIL = "agentbob" + BOT_DOMAIN


def is_system_email(email: str) -> bool:
    return email.strip().lower().endswith(BOT_DOMAIN)


def ensure_system_users(db: Session) -> None:
    if db.get(User, AGENTBOB_ID) is not None:
        return
    db.add(
        User(
            id=AGENTBOB_ID,
            email=AGENTBOB_EMAIL,
            display_name="AgentBob (AI)",
            role=ROLE_BOT,
            onboarding_done=True,
            profile_done=True,
            headline="The site's robot assistant",
            bio=(
                "AgentBob is UniteIdeas' automated assistant. It helps with housekeeping such as "
                "spotting duplicate ideas, suggesting teammates, flagging content for moderators "
                "and keeping the site running. People make the final decisions."
            ),
        )
    )
    db.commit()
