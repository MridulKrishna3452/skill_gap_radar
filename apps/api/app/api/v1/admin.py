"""Administration: users and roles, faculty program assignments, the audit log. Admin only."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_db, pagination, require_admin
from app.api.v1.account_schemas import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    AuditOut,
    Role,
)
from app.api.v1.schemas import Page
from app.core.errors import ConflictError, InvalidInputError, NotFoundError
from app.models import AuditLog, FacultyProgramAssignment, Program, User
from app.services import audit
from app.services.auth import service
from app.services.auth.passwords import check_password_policy, hash_password

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


async def _out(session: AsyncSession, user: User) -> dict[str, Any]:
    program_ids = (
        await session.scalars(
            select(FacultyProgramAssignment.program_id)
            .where(FacultyProgramAssignment.user_id == user.id)
            .order_by(FacultyProgramAssignment.program_id)
        )
    ).all()
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "program_ids": list(program_ids),
    }


async def _user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    return user


@router.get("/users", response_model=Page[AdminUserOut], summary="List users")
async def list_users(
    page: Pagination = Depends(pagination),
    role: Role | None = Query(None),
    email: str | None = Query(None, max_length=320, description="Substring match"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conds = []
    if role:
        conds.append(User.role == role)
    if email:
        conds.append(User.email.contains(email.strip().lower(), autoescape=True))
    total = await session.scalar(select(func.count()).select_from(User).where(*conds)) or 0
    users = (
        await session.scalars(
            select(User)
            .where(*conds)
            .order_by(User.created_at)
            .limit(page.limit)
            .offset(page.offset)
        )
    ).all()
    return {
        "items": [await _out(session, u) for u in users],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.post(
    "/users",
    response_model=AdminUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user with any role (faculty and admin accounts are created here)",
)
async def create_user(
    body: AdminUserCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await service.create_user(session, body.email, body.password, role=body.role)
    audit.record(
        session,
        "user.create",
        actor=admin,
        target_type="user",
        target_id=user.id,
        details={"role": user.role},
    )
    return await _out(session, user)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserOut,
    summary="Change a user's role or active flag, or reset their password",
    description="Deactivating a user, changing their role or resetting their password signs "
    "them out everywhere. The last active admin cannot be demoted or deactivated.",
)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await _user(session, user_id)
    changes: dict[str, Any] = {}
    losing_admin = (
        user.role == "admin"
        and user.is_active
        and ((body.role is not None and body.role != "admin") or body.is_active is False)
    )
    if losing_admin and await service.active_admin_count(session) <= 1:
        raise ConflictError("The last active admin cannot be demoted or deactivated")
    if body.role is not None and body.role != user.role:
        changes["role"] = {"from": user.role, "to": body.role}
        user.role = body.role
        if body.role != "faculty":
            await session.execute(
                delete(FacultyProgramAssignment).where(FacultyProgramAssignment.user_id == user.id)
            )
    if body.is_active is not None and body.is_active != user.is_active:
        changes["is_active"] = body.is_active
        user.is_active = body.is_active
    if body.new_password is not None:
        check_password_policy(body.new_password, user.email)
        user.password_hash = hash_password(body.new_password)
        user.failed_login_count = 0
        user.locked_until = None
        changes["password_reset"] = True
    if not changes:
        raise InvalidInputError("Nothing to change")
    await service.revoke_all(session, user.id)
    audit.record(
        session,
        "user.update",
        actor=admin,
        target_type="user",
        target_id=user.id,
        details=changes,
    )
    await session.flush()
    return await _out(session, user)


@router.put(
    "/users/{user_id}/programs/{program_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Let a faculty member manage a program's curriculum",
)
async def assign_program(
    user_id: uuid.UUID,
    program_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    user = await _user(session, user_id)
    if user.role != "faculty":
        raise InvalidInputError("Only faculty accounts can be assigned to programs")
    if await session.get(Program, program_id) is None:
        raise NotFoundError(f"Program {program_id} not found")
    if await session.get(FacultyProgramAssignment, (user.id, program_id)) is None:
        session.add(FacultyProgramAssignment(user_id=user.id, program_id=program_id))
        audit.record(
            session,
            "faculty.assign",
            actor=admin,
            target_type="user",
            target_id=user.id,
            details={"program_id": program_id},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/users/{user_id}/programs/{program_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a faculty member's program assignment",
)
async def unassign_program(
    user_id: uuid.UUID,
    program_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    row = await session.get(FacultyProgramAssignment, (user_id, program_id))
    if row is None:
        raise NotFoundError("No such assignment")
    await session.delete(row)
    audit.record(
        session,
        "faculty.unassign",
        actor=admin,
        target_type="user",
        target_id=user_id,
        details={"program_id": program_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit-log", response_model=Page[AuditOut], summary="Audit log, newest first")
async def audit_log(
    page: Pagination = Depends(pagination),
    action: str | None = Query(None, max_length=60),
    actor_user_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conds = []
    if action:
        conds.append(AuditLog.action == action)
    if actor_user_id:
        conds.append(AuditLog.actor_user_id == actor_user_id)
    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*conds)) or 0
    rows = (
        await session.scalars(
            select(AuditLog)
            .where(*conds)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(page.limit)
            .offset(page.offset)
        )
    ).all()
    return {"items": rows, "total": total, "limit": page.limit, "offset": page.offset}
