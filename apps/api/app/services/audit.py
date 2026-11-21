"""Audit log of privileged and security-relevant actions.

Entries carry ids, the action and non-personal details only: never passwords, tokens or email
addresses. Writing an entry adds it to the caller's transaction, so it is committed (or rolled
back) together with the action it records.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_ctx
from app.models import AuditLog, User

ACTIONS = frozenset(
    {
        "auth.lockout",
        "auth.password_change",
        "auth.refresh_reuse",
        "curriculum.upload",
        "faculty.assign",
        "faculty.unassign",
        "ingestion.trigger",
        "program.create",
        "university.create",
        "user.create",
        "user.delete",
        "user.update",
    }
)


def record(
    session: AsyncSession,
    action: str,
    *,
    actor: User | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    target_type: str | None = None,
    target_id: object = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    if action not in ACTIONS:
        raise ValueError(f"unknown audit action {action!r}")
    entry = AuditLog(
        actor_user_id=actor.id if actor else actor_id,
        actor_role=actor.role if actor else actor_role,
        action=action,
        target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        request_id=request_id_ctx.get(),
        details=details or {},
    )
    session.add(entry)
    return entry
