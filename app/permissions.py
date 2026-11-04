"""What each role may do. Roles are coarse on purpose; permissions are the unit checked in code.

user        ordinary member
moderator   reviews held ideas and reports; cannot manage accounts. May not decide on their own ideas.
admin       everything a moderator can, plus accounts, the audit log and system tools. An admin is
            also an ordinary member with the same account; the admin tools live on /admin.
bot         AgentBob: no sign-in, acts only through the agent API. Moderation scope only: look at
            items, confirm or escalate them, flag ideas. Cannot reject, remove or manage anyone.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.models import ROLE_ADMIN, ROLE_MODERATOR, User
from app.security import require_user

MODERATE = {"ideas.review", "reports.resolve", "sealed.review"}
ADMIN = MODERATE | {"users.manage", "audit.view", "system.manage"}

PERMISSIONS: dict[str, set[str]] = {
    ROLE_MODERATOR: MODERATE,
    ROLE_ADMIN: ADMIN,
}


def can(user: User | None, permission: str) -> bool:
    return bool(user and user.is_active and permission in PERMISSIONS.get(user.role, set()))


def require_permission(permission: str):
    def dependency(user: User = Depends(require_user)) -> User:
        if not can(user, permission):
            raise HTTPException(status_code=403, detail="you do not have access to this")
        return user

    return dependency
