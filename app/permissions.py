"""What each role may do. Roles are coarse on purpose; permissions are the unit checked in code.

user        ordinary member
moderator   reviews first submissions and reports; cannot manage accounts
admin       everything a moderator can, plus accounts, the audit log and system tools
bot         service accounts (AgentBob); no sign-in, acts only through the agent API
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
