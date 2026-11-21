"""Request and response models for authentication, the current user, and administration."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas import ORM, SkillRef

Role = Literal["student", "faculty", "admin"]
Password = Field(min_length=1, max_length=128, json_schema_extra={"format": "password"})


class Credentials(BaseModel):
    email: str = Field(max_length=320, examples=["student@example.edu"])
    password: str = Password


class RegisterIn(Credentials):
    pass


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - the OAuth token type, not a secret
    expires_in: int = Field(description="Access token lifetime in seconds")


class UserOut(ORM):
    id: uuid.UUID
    email: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class PasswordChangeIn(BaseModel):
    current_password: str = Password
    new_password: str = Password


class AccountDeleteIn(BaseModel):
    password: str = Password


# ---- profile and skills -------------------------------------------------------------------


class ProfileIn(BaseModel):
    """All fields optional; PUT replaces the profile, PATCH changes only the fields sent."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=120)
    university_id: int | None = None
    program_id: int | None = Field(
        default=None, description="Must belong to university_id when both are given"
    )
    graduation_year: int | None = Field(default=None, ge=2000, le=2100, examples=[2027])
    target_role: str | None = Field(
        default=None,
        max_length=60,
        description="Role slug (GET /roles)",
        examples=["data-engineer"],
    )
    location_preference: str | None = Field(default=None, max_length=255, examples=["Bangalore"])
    open_to_remote: bool | None = None


class RefOut(BaseModel):
    id: int
    name: str


class RoleRefOut(BaseModel):
    id: int
    slug: str
    name: str


class ProfileOut(BaseModel):
    display_name: str | None
    university: RefOut | None
    program: RefOut | None
    graduation_year: int | None
    target_role: RoleRefOut | None
    location_preference: str | None
    open_to_remote: bool
    updated_at: datetime | None


Proficiency = Field(
    ge=1, le=5, description="1 beginner, 2 elementary, 3 intermediate, 4 advanced, 5 expert"
)


class UserSkillIn(BaseModel):
    skill: str = Field(max_length=80, description="Skill slug (GET /skills)", examples=["python"])
    proficiency: int = Proficiency


class UserSkillUpdate(BaseModel):
    proficiency: int = Proficiency


class UserSkillOut(BaseModel):
    skill: SkillRef
    proficiency: int
    source: str
    updated_at: datetime


class MeOut(UserOut):
    profile: ProfileOut | None = None


# ---- administration ---------------------------------------------------------------------


class AdminUserCreate(Credentials):
    role: Role = "faculty"


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    is_active: bool | None = None
    new_password: str | None = Field(
        default=None, max_length=128, description="Reset the password; signs the user out"
    )


class AdminUserOut(UserOut):
    program_ids: list[int] = Field(default_factory=list, description="Programs a faculty manages")


class AuditOut(ORM):
    id: int
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_role: str | None
    action: str
    target_type: str | None
    target_id: str | None
    request_id: str | None
    details: dict[str, Any]
