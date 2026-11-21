"""Registration, login, token refresh and logout.

The access token is returned in the body (keep it in memory, send it as a Bearer token). The
refresh token is only ever an httpOnly, Secure, SameSite=Strict cookie scoped to /auth.
"""

from typing import Any

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    check_origin,
    current_user,
    get_app_settings,
    get_db,
    get_redis,
    rate_limit,
)
from app.api.v1.account_schemas import Credentials, PasswordChangeIn, RegisterIn, TokenOut, UserOut
from app.core.config import Settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.models import User
from app.services.auth import ratelimit, service

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "sr_refresh"


def _cookie_path(settings: Settings) -> str:
    return f"{settings.API_PREFIX}/auth"


def _set_refresh_cookie(response: Response, session: service.Session, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_value,
        max_age=settings.REFRESH_TOKEN_DAYS * 86400,
        path=_cookie_path(settings),
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=_cookie_path(settings),
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def _token(session: service.Session) -> dict[str, Any]:
    return {"access_token": session.access.token, "expires_in": session.access.expires_in}


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a student account",
    description="Open registration creates student accounts only; faculty and admin accounts "
    "are created by an admin. Passwords need at least 12 characters.",
    dependencies=[Depends(rate_limit("register", "RATE_LIMIT_REGISTER", fail_closed=True))],
    responses={409: {"description": "Email already registered"}, 429: {"description": "Rate"}},
)
async def register(
    body: RegisterIn,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> User:
    if not settings.ALLOW_REGISTRATION:
        raise ForbiddenError("Registration is closed")
    return await service.create_user(session, body.email, body.password, role="student")


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Log in; returns an access token and sets the refresh cookie",
    description="Failures always return the same 401, whether the email is unknown, the "
    "password wrong or the account temporarily locked (after repeated failures).",
    dependencies=[Depends(rate_limit("login_ip", "RATE_LIMIT_LOGIN_IP", fail_closed=True))],
)
async def login(
    body: Credentials,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    redis: Any = Depends(get_redis),
) -> dict[str, Any]:
    ip = ratelimit.client_ip(request, settings)
    await ratelimit.hit(
        redis,
        "login",
        f"{ip}|{body.email.strip().lower()}",
        settings.RATE_LIMIT_LOGIN,
        fail_closed=True,
    )
    result = await service.login(session, body.email, body.password, settings)
    _set_refresh_cookie(response, result, settings)
    return _token(result)


@router.post(
    "/refresh",
    response_model=TokenOut,
    summary="Exchange the refresh cookie for a new access token (rotates the cookie)",
    description="Each refresh token works once. Presenting a used one again is treated as "
    "theft: every session from that login is revoked.",
    dependencies=[
        Depends(check_origin),
        Depends(rate_limit("refresh", "RATE_LIMIT_REFRESH", fail_closed=True)),
    ],
)
async def refresh(
    response: Response,
    sr_refresh: str | None = Cookie(default=None, include_in_schema=False),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    if not sr_refresh:
        raise UnauthorizedError("No refresh token")
    result = await service.refresh(session, sr_refresh, settings)
    _set_refresh_cookie(response, result, settings)
    return _token(result)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End this session (revokes the refresh cookie's login)",
    dependencies=[Depends(check_origin)],
)
async def logout(
    sr_refresh: str | None = Cookie(default=None, include_in_schema=False),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    await service.logout(session, sr_refresh)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End every session of the current user",
)
async def logout_all(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    await service.revoke_all(session, user.id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current user's password (signs out every session)",
)
async def change_password(
    body: PasswordChangeIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    await service.change_password(session, user, body.current_password, body.new_password)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response
