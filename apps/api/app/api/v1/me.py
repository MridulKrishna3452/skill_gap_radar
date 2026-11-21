"""The current user: account, student profile and skills inventory, account deletion."""

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_app_settings, get_db, require_student
from app.api.v1.account_schemas import (
    AccountDeleteIn,
    MeOut,
    ProfileIn,
    ProfileOut,
    UserSkillIn,
    UserSkillOut,
    UserSkillUpdate,
)
from app.api.v1.auth import clear_refresh_cookie
from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.models import User
from app.services import profiles
from app.services.auth import service
from app.services.auth.passwords import verify_password

router = APIRouter(prefix="/me", tags=["me"])


def _user_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


@router.get("", response_model=MeOut, summary="The current user and their profile")
async def get_me(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return _user_dict(user) | {"profile": await profiles.profile_out(session, user)}


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the current account and its personal data",
    description="Requires the current password. Removes the account, sessions, profile and "
    "skills. Audit entries keep the action but no longer name the account. The last active "
    "admin cannot delete their own account.",
)
async def delete_me(
    body: AccountDeleteIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    if not verify_password(user.password_hash, body.password):
        raise ForbiddenError("Password is incorrect")
    if user.role == "admin" and await service.active_admin_count(session) <= 1:
        raise ConflictError("The last active admin cannot be deleted")
    await profiles.delete_account(session, user)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response


@router.get(
    "/profile",
    response_model=ProfileOut,
    summary="The current student's profile",
    responses={404: {"description": "No profile yet"}},
)
async def get_profile(
    user: User = Depends(require_student), session: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    out = await profiles.profile_out(session, user)
    if out is None:
        raise NotFoundError("No profile yet; create one with PUT /me/profile")
    return out


@router.put("/profile", response_model=ProfileOut, summary="Create or replace the profile")
async def put_profile(
    body: ProfileIn,
    user: User = Depends(require_student),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any] | None:
    await profiles.save_profile(session, user, body.model_dump(), replace=True)
    return await profiles.profile_out(session, user)


@router.patch("/profile", response_model=ProfileOut, summary="Change some profile fields")
async def patch_profile(
    body: ProfileIn,
    user: User = Depends(require_student),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any] | None:
    await profiles.save_profile(session, user, body.model_dump(exclude_unset=True), replace=False)
    return await profiles.profile_out(session, user)


@router.get("/skills", response_model=list[UserSkillOut], summary="The current user's skills")
async def get_skills(
    user: User = Depends(require_student), session: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    return await profiles.list_skills(session, user)


@router.post(
    "/skills",
    response_model=UserSkillOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a skill with a self-assessed proficiency",
    responses={409: {"description": "Skill already added"}},
)
async def add_skill(
    body: UserSkillIn,
    user: User = Depends(require_student),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await profiles.add_skill(session, user, body.skill, body.proficiency)


@router.patch("/skills/{slug}", response_model=UserSkillOut, summary="Change a skill's proficiency")
async def update_skill(
    slug: str,
    body: UserSkillUpdate,
    user: User = Depends(require_student),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await profiles.update_skill(session, user, slug, body.proficiency)


@router.delete("/skills/{slug}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a skill")
async def remove_skill(
    slug: str,
    user: User = Depends(require_student),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await profiles.remove_skill(session, user, slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
