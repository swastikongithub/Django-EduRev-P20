import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _json_safe(value: Any) -> Any:
    return value if value is None or isinstance(value, bool | int | float | str) else str(value)


def record(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    **details: Any,
) -> None:
    """Add an audit entry to the current transaction (it is saved when the caller commits)."""
    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={key: _json_safe(value) for key, value in details.items()},
        )
    )
