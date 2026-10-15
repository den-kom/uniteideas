"""Record staff actions. Call inside the same transaction as the change, then commit."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record(
    db: Session,
    actor: User | None,
    action: str,
    target_type: str = "",
    target_id: str = "",
    detail: str = "",
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_name=actor.display_name if actor else "system",
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail[:500],
        )
    )
