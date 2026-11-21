"""Shared FastAPI dependencies. Resources live on app.state, created in the lifespan."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, Query, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db.session import session_scope
from app.models import CurriculumDocument, FacultyProgramAssignment, User
from app.services.auth import ratelimit
from app.services.auth.tokens import decode_access_token
from app.workers.queue import TaskQueue


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(request.app.state.session_factory):
        yield session


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def get_task_queue(request: Request) -> TaskQueue:
    queue: TaskQueue = request.app.state.task_queue
    return queue


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, le=100_000, description="Items to skip"),
) -> Pagination:
    return Pagination(limit, offset)


# ---- authentication and authorisation (docs/security.md) ---------------------------------


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


async def optional_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> User | None:
    """The authenticated user, or None when no token is sent. An invalid token is a 401."""
    token = _bearer(request)
    if token is None:
        return None
    user_id = decode_access_token(token, settings)
    # Reloaded on every request so deactivation and role changes take effect immediately.
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid access token")
    return user


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise UnauthorizedError()
    return user


def require_role(*roles: str) -> Callable[..., Awaitable[User]]:
    async def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise ForbiddenError()
        return user

    return dependency


require_admin = require_role("admin")
require_student = require_role("student")


async def _manages(session: AsyncSession, user: User, program_id: int) -> bool:
    if user.role == "admin":
        return True
    if user.role != "faculty":
        return False
    return (
        await session.scalar(
            select(FacultyProgramAssignment.user_id).where(
                FacultyProgramAssignment.user_id == user.id,
                FacultyProgramAssignment.program_id == program_id,
            )
        )
        is not None
    )


async def require_program_manager(
    program_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Admins, or faculty assigned to the program in the path."""
    if not await _manages(session, user, program_id):
        raise ForbiddenError()
    return user


async def require_document_manager(
    document_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Admins, or faculty assigned to the document's program. An unknown document id gives
    the same 403 as a forbidden one, so ids cannot be probed."""
    program_id = await session.scalar(
        select(CurriculumDocument.program_id).where(CurriculumDocument.id == document_id)
    )
    if program_id is None:
        if user.role == "admin":
            return user  # let the route answer 404
        raise ForbiddenError()
    if not await _manages(session, user, program_id):
        raise ForbiddenError()
    return user


def rate_limit(
    bucket: str, setting: str, *, per: str = "ip", fail_closed: bool = False
) -> Callable[..., Awaitable[None]]:
    """Count the request against a Redis window, per client IP or per user (IP when
    anonymous). The per-IP variant does not look up the user."""

    async def per_ip(
        request: Request,
        settings: Settings = Depends(get_app_settings),
        redis: Redis = Depends(get_redis),
    ) -> None:
        identifier = f"ip:{ratelimit.client_ip(request, settings)}"
        await ratelimit.hit(
            redis, bucket, identifier, getattr(settings, setting), fail_closed=fail_closed
        )

    async def per_user(
        request: Request,
        settings: Settings = Depends(get_app_settings),
        redis: Redis = Depends(get_redis),
        user: User | None = Depends(optional_user),
    ) -> None:
        identifier = (
            f"user:{user.id}"
            if user is not None
            else f"ip:{ratelimit.client_ip(request, settings)}"
        )
        await ratelimit.hit(
            redis, bucket, identifier, getattr(settings, setting), fail_closed=fail_closed
        )

    if per not in ("ip", "user"):
        raise ValueError(per)
    return per_ip if per == "ip" else per_user


public_rate_limit = rate_limit("public", "RATE_LIMIT_PUBLIC")
expensive_rate_limit = rate_limit("expensive", "RATE_LIMIT_EXPENSIVE", per="user")


def check_origin(request: Request, settings: Settings = Depends(get_app_settings)) -> None:
    """Cookie-authenticated endpoints (refresh, logout): reject browser requests from origins
    not on the CORS list. SameSite=Strict on the cookie is the primary CSRF defence."""
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.CORS_ORIGINS:
        raise ForbiddenError("Origin not allowed")
