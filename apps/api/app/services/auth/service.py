"""Accounts and sessions: registration, login with lockout, refresh rotation, logout.

Failures that must persist even though the request fails (a failed-login count, a lockout,
revoking a family after token reuse) are committed before the error is raised, because the
request's session rolls back on any error.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, InvalidInputError, UnauthorizedError
from app.models import RefreshToken, User
from app.services import audit
from app.services.auth.passwords import (
    check_password_policy,
    hash_password,
    needs_rehash,
    normalize_email,
    verify_password,
)
from app.services.auth.tokens import (
    AccessToken,
    create_access_token,
    hash_refresh_value,
    new_refresh_value,
)

logger = logging.getLogger(__name__)
# One message for every login failure (unknown email, wrong password, locked, inactive), so
# the response does not reveal whether an account exists.
LOGIN_FAILED = "Invalid email or password, or the account is temporarily locked"


@dataclass(frozen=True)
class Session:
    user: User
    access: AccessToken
    refresh_value: str
    refresh_expires_at: datetime


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def create_user(
    session: AsyncSession, email: str, password: str, role: str = "student"
) -> User:
    email = normalize_email(email)
    check_password_policy(password, email)
    user = User(email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("An account with this email already exists") from exc
    return user


async def _issue(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    family_id: uuid.UUID | None = None,
    family_started_at: datetime | None = None,
    now: datetime,
) -> tuple[RefreshToken, Session]:
    value = new_refresh_value()
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_refresh_value(value),
        issued_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        family_started_at=family_started_at or now,
    )
    session.add(row)
    await session.flush()
    access = create_access_token(user.id, user.role, settings, now=now)
    return row, Session(user, access, value, row.expires_at)


async def login(
    session: AsyncSession,
    email: str,
    password: str,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> Session:
    now = now or _now()
    try:
        email = normalize_email(email)
    except InvalidInputError:
        verify_password(None, password)
        raise UnauthorizedError(LOGIN_FAILED) from None
    user = await session.scalar(select(User).where(User.email == email).with_for_update())
    locked = user is not None and user.locked_until is not None and user.locked_until > now
    ok = verify_password(user.password_hash if user else None, password)
    if user is None or not user.is_active or locked or not ok:
        if user is not None and not locked and not ok:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.LOGIN_MAX_FAILURES:
                user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
                user.failed_login_count = 0
                audit.record(
                    session,
                    "auth.lockout",
                    actor_id=None,
                    target_type="user",
                    target_id=user.id,
                    details={"minutes": settings.LOCKOUT_MINUTES},
                )
                logger.info("Account %s locked after repeated failed logins", user.id)
            await session.commit()
        raise UnauthorizedError(LOGIN_FAILED)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    _, result = await _issue(session, user, settings, now=now)
    return result


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> int:
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def revoke_all(session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None) -> int:
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now or _now())
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def refresh(
    session: AsyncSession, value: str, settings: Settings, *, now: datetime | None = None
) -> Session:
    """Rotate a refresh token. Reusing an already-rotated token revokes its whole family."""
    now = now or _now()
    row = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_value(value))
        .with_for_update()
    )
    if row is None:
        raise UnauthorizedError("Invalid refresh token")
    if row.used_at is not None or row.revoked_at is not None:
        if row.used_at is not None:
            revoked = await _revoke_family(session, row.family_id, now)
            audit.record(
                session,
                "auth.refresh_reuse",
                actor_id=row.user_id,
                target_type="refresh_family",
                target_id=row.family_id,
                details={"tokens_revoked": revoked},
            )
            logger.warning("Refresh token reuse detected; family %s revoked", row.family_id)
            await session.commit()
        raise UnauthorizedError("Invalid refresh token")
    family_limit = row.family_started_at + timedelta(days=settings.REFRESH_FAMILY_MAX_DAYS)
    if row.expires_at <= now or family_limit <= now:
        raise UnauthorizedError("Refresh token expired")
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid refresh token")
    row.used_at = now
    new_row, result = await _issue(
        session,
        user,
        settings,
        family_id=row.family_id,
        family_started_at=row.family_started_at,
        now=now,
    )
    row.replaced_by_id = new_row.id
    return result


async def logout(session: AsyncSession, value: str | None, now: datetime | None = None) -> None:
    """Revoke the family of the presented refresh token. Unknown tokens are ignored."""
    if not value:
        return
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_value(value))
    )
    if row is not None:
        await _revoke_family(session, row.family_id, now or _now())


async def change_password(
    session: AsyncSession, user: User, current: str, new: str, now: datetime | None = None
) -> None:
    if not verify_password(user.password_hash, current):
        raise ForbiddenError("Current password is incorrect")
    check_password_policy(new, user.email)
    user.password_hash = hash_password(new)
    await revoke_all(session, user.id, now)
    audit.record(session, "auth.password_change", actor=user, target_type="user", target_id=user.id)


async def active_admin_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
        )
        or 0
    )
