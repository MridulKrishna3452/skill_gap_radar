"""Student profiles, the user skills inventory, and account deletion."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, InvalidInputError, NotFoundError
from app.models import Program, Role, Skill, StudentProfile, University, User, UserSkill
from app.services import audit
from app.services.normalize import normalize_location

MAX_SKILLS = 200


async def profile_out(session: AsyncSession, user: User) -> dict[str, Any] | None:
    p = await session.get(StudentProfile, user.id)
    if p is None:
        return None
    uni = await session.get(University, p.university_id) if p.university_id else None
    prog = await session.get(Program, p.program_id) if p.program_id else None
    role = await session.get(Role, p.target_role_id) if p.target_role_id else None
    return {
        "display_name": p.display_name,
        "university": {"id": uni.id, "name": uni.name} if uni else None,
        "program": {"id": prog.id, "name": prog.name} if prog else None,
        "graduation_year": p.graduation_year,
        "target_role": {"id": role.id, "slug": role.slug, "name": role.name} if role else None,
        "location_preference": p.location_preference,
        "open_to_remote": p.open_to_remote,
        "updated_at": p.updated_at,
    }


async def save_profile(
    session: AsyncSession, user: User, values: dict[str, Any], *, replace: bool
) -> None:
    """Create or update the profile. `values` holds only fields the client sent (PATCH) or
    every field (PUT; missing ones reset to empty)."""
    p = await session.get(StudentProfile, user.id)
    if p is None:
        p = StudentProfile(user_id=user.id, open_to_remote=False)
        session.add(p)
    current: dict[str, Any] = {
        "display_name": p.display_name,
        "university_id": p.university_id,
        "program_id": p.program_id,
        "graduation_year": p.graduation_year,
        "target_role_id": p.target_role_id,
        "location_preference": p.location_preference,
        "open_to_remote": p.open_to_remote,
    }
    if replace:
        current = {k: None for k in current} | {"open_to_remote": False}
    for key, value in values.items():
        if key == "target_role":
            if value is None:
                current["target_role_id"] = None
            else:
                role_id = await session.scalar(select(Role.id).where(Role.slug == value))
                if role_id is None:
                    raise InvalidInputError(f"Unknown role '{value}' (see GET /roles)")
                current["target_role_id"] = role_id
        elif key == "location_preference":
            current[key] = normalize_location(value) if value else None
        elif key == "display_name":
            current[key] = value.strip() or None if value else None
        elif key == "open_to_remote":
            current[key] = bool(value)
        else:
            current[key] = value
    if current["university_id"] is not None and (
        await session.get(University, current["university_id"]) is None
    ):
        raise InvalidInputError(f"University {current['university_id']} not found")
    if current["program_id"] is not None:
        program = await session.get(Program, current["program_id"])
        if program is None:
            raise InvalidInputError(f"Program {current['program_id']} not found")
        if current["university_id"] is None:
            current["university_id"] = program.university_id
        elif program.university_id != current["university_id"]:
            raise InvalidInputError("The program does not belong to the selected university")
    for key, value in current.items():
        setattr(p, key, value)
    await session.flush()


async def _skill(session: AsyncSession, slug: str) -> Skill:
    skill = await session.scalar(select(Skill).where(Skill.slug == slug))
    if skill is None:
        raise InvalidInputError(f"Unknown skill '{slug}' (see GET /skills)")
    return skill


async def list_skills(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(UserSkill, Skill)
            .join(Skill, Skill.id == UserSkill.skill_id)
            .where(UserSkill.user_id == user.id)
            .order_by(UserSkill.proficiency.desc(), Skill.name)
        )
    ).all()
    return [_skill_out(us, s) for us, s in rows]


def _skill_out(us: UserSkill, s: Skill) -> dict[str, Any]:
    return {
        "skill": {"id": s.id, "slug": s.slug, "name": s.name},
        "proficiency": us.proficiency,
        "source": us.source,
        "updated_at": us.updated_at,
    }


async def add_skill(
    session: AsyncSession, user: User, slug: str, proficiency: int
) -> dict[str, Any]:
    skill = await _skill(session, slug)
    count = len(
        (await session.scalars(select(UserSkill.id).where(UserSkill.user_id == user.id))).all()
    )
    if count >= MAX_SKILLS:
        raise InvalidInputError(f"At most {MAX_SKILLS} skills per user")
    row = UserSkill(user_id=user.id, skill_id=skill.id, proficiency=proficiency)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"'{slug}' is already in your skills; use PATCH to change it") from exc
    await session.refresh(row)
    return _skill_out(row, skill)


async def _owned(session: AsyncSession, user: User, slug: str) -> tuple[UserSkill, Skill]:
    skill = await _skill(session, slug)
    row = await session.scalar(
        select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.skill_id == skill.id)
    )
    if row is None:
        raise NotFoundError(f"'{slug}' is not in your skills")
    return row, skill


async def update_skill(
    session: AsyncSession, user: User, slug: str, proficiency: int
) -> dict[str, Any]:
    row, skill = await _owned(session, user, slug)
    row.proficiency = proficiency
    await session.flush()
    await session.refresh(row)
    return _skill_out(row, skill)


async def remove_skill(session: AsyncSession, user: User, slug: str) -> None:
    row, _ = await _owned(session, user, slug)
    await session.delete(row)


async def delete_account(session: AsyncSession, user: User) -> None:
    """Remove the user and, through ON DELETE CASCADE, their refresh tokens, profile, skills
    and faculty assignments. Audit entries they made keep the action but lose the actor."""
    audit.record(
        session,
        "user.delete",
        actor_id=None,  # the actor row is being deleted
        actor_role=user.role,
        target_type="user",
        target_id=user.id,
        details={"self_service": True},
    )
    await session.execute(delete(User).where(User.id == user.id))
