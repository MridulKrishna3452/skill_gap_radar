"""Skills taxonomy, market demand and trends (v1: GET /skills and the trends page)."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import Pagination, get_app_settings, get_db, pagination
from app.api.v1.jobs import escape_like
from app.api.v1.schemas import (
    DemandResponse,
    MoversResponse,
    Page,
    RoleOut,
    SkillDetail,
    SkillOut,
    SkillTrendResponse,
)
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models import Role, RoleSkill, Skill, SkillAlias, SkillDemandMonthly
from app.services.analytics.demand import add_months, monthly_totals, resolve_window, window_demand
from app.services.analytics.trends import (
    EMERGING_MIN_SHARE,
    EMERGING_PREV_MAX,
    compute_movers,
    month_shares,
    series_for_skill,
)

router = APIRouter(tags=["skills"])


def _ref(s: Skill) -> dict[str, Any]:
    return {"id": s.id, "slug": s.slug, "name": s.name}


async def _role_id(session: AsyncSession, slug: str | None) -> int | None:
    if not slug:
        return None
    role_id = await session.scalar(select(Role.id).where(Role.slug == slug))
    if role_id is None:
        raise NotFoundError(f"Role '{slug}' not found")
    return role_id


async def _skills_by_id(session: AsyncSession, ids: set[int]) -> dict[int, Skill]:
    return {s.id: s for s in (await session.scalars(select(Skill).where(Skill.id.in_(ids)))).all()}


@router.get("/skills", response_model=Page[SkillOut], summary="Search the skills taxonomy")
async def list_skills(
    page: Pagination = Depends(pagination),
    q: str | None = Query(None, max_length=100, description="Matches name or any alias"),
    category: str | None = Query(None, max_length=60),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conds: list[ColumnElement[bool]] = []
    if q:
        pattern = f"%{escape_like(q.lower())}%"
        conds.append(
            or_(
                func.lower(Skill.name).like(pattern, escape="\\"),
                Skill.id.in_(
                    select(SkillAlias.skill_id).where(
                        SkillAlias.alias_normalized.like(pattern, escape="\\")
                    )
                ),
            )
        )
    if category:
        conds.append(Skill.category == category)
    total = await session.scalar(select(func.count()).select_from(Skill).where(*conds)) or 0
    rows = (
        await session.scalars(
            select(Skill).where(*conds).order_by(Skill.name).limit(page.limit).offset(page.offset)
        )
    ).all()
    parents = await _skills_by_id(session, {s.parent_id for s in rows if s.parent_id})
    items = [
        {
            **_ref(s),
            "category": s.category,
            "esco_uri": s.esco_uri,
            "parent": _ref(parents[s.parent_id]) if s.parent_id else None,
        }
        for s in rows
    ]
    return {"items": items, "total": total, "limit": page.limit, "offset": page.offset}


@router.get(
    "/skills/demand",
    response_model=DemandResponse,
    summary="Skill demand share in recent postings",
    description="Share of postings in the window (default: the last ANALYTICS_DEFAULT_WINDOW_"
    "MONTHS months with data) that mention each skill. Synthetic sources are excluded.",
)
async def skill_demand(
    page: Pagination = Depends(pagination),
    role: str | None = Query(None, description="Role slug; omit for all postings"),
    months: int | None = Query(None, ge=1, le=60),
    as_of: date | None = Query(None, description="Last month of the window (default: latest)"),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    months = months or settings.ANALYTICS_DEFAULT_WINDOW_MONTHS
    role_id = await _role_id(session, role)
    window = await resolve_window(session, months, as_of)
    total, demand = (0, []) if window is None else await window_demand(session, window, role_id)
    demand.sort(key=lambda d: (-d.postings_with_skill, d.skill_id))
    chunk = demand[page.offset : page.offset + page.limit]
    skills = await _skills_by_id(session, {d.skill_id for d in chunk})
    return {
        "window": {
            "start": window.start if window else None,
            "end_exclusive": window.end if window else None,
            "months": months,
        },
        "role": role,
        "total_postings": total,
        "low_sample": total < settings.ANALYTICS_MIN_POSTINGS,
        "items": [
            {
                "skill": _ref(skills[d.skill_id]),
                "postings_with_skill": d.postings_with_skill,
                "required_postings": d.required_postings,
                "share": round(d.postings_with_skill / total, 4),
                "required_share": round(d.required_postings / total, 4),
            }
            for d in chunk
        ],
        "total": len(demand),
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/skills/{slug}", response_model=SkillDetail, summary="Get one skill with aliases")
async def get_skill(slug: str, session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    skill = await session.scalar(
        select(Skill).where(Skill.slug == slug).options(selectinload(Skill.aliases))
    )
    if skill is None:
        raise NotFoundError(f"Skill '{slug}' not found")
    parent = await session.get(Skill, skill.parent_id) if skill.parent_id else None
    return {
        **_ref(skill),
        "category": skill.category,
        "esco_uri": skill.esco_uri,
        "parent": _ref(parent) if parent else None,
        "description": skill.description,
        "context_terms": skill.context_terms,
        "aliases": sorted(
            (
                {
                    "alias": a.alias,
                    "requires_context": a.requires_context,
                    "case_sensitive_form": a.case_sensitive_form,
                }
                for a in skill.aliases
            ),
            key=lambda a: str(a["alias"]),
        ),
    }


@router.get("/roles", response_model=list[RoleOut], summary="Job roles and their core skills")
async def list_roles(session: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    roles = (await session.scalars(select(Role).order_by(Role.name))).all()
    links = (await session.scalars(select(RoleSkill).order_by(RoleSkill.position))).all()
    skills = await _skills_by_id(session, {link.skill_id for link in links})
    return [
        {
            "id": r.id,
            "slug": r.slug,
            "name": r.name,
            "title_patterns": r.title_patterns,
            "core_skills": [_ref(skills[link.skill_id]) for link in links if link.role_id == r.id],
        }
        for r in roles
    ]


@router.get(
    "/trends/skills/{slug}",
    response_model=SkillTrendResponse,
    tags=["trends"],
    summary="Monthly demand share series for a skill",
)
async def skill_trend(
    slug: str,
    role: str | None = Query(None, description="Role slug; omit for all postings"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    skill = await session.scalar(select(Skill).where(Skill.slug == slug))
    if skill is None:
        raise NotFoundError(f"Skill '{slug}' not found")
    role_id = await _role_id(session, role)
    series = await series_for_skill(session, skill.id, role_id)
    return {
        "skill": _ref(skill),
        "role": role,
        "series": [
            {
                "month": p.month,
                "total_postings": p.total_postings,
                "postings_with_skill": p.postings_with_skill,
                "share": round(p.share, 4),
                "change_pp": None if p.change_pp is None else round(p.change_pp, 4),
                "change_rel": None if p.change_rel is None else round(p.change_rel, 4),
            }
            for p in series
        ],
    }


@router.get(
    "/trends/movers",
    response_model=MoversResponse,
    tags=["trends"],
    summary="Growing, declining and emerging skills, latest month vs the month before",
)
async def movers(
    role: str | None = Query(None, description="Role slug; omit for all postings"),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    role_id = await _role_id(session, role)
    cond = (
        SkillDemandMonthly.role_id.is_(None)
        if role_id is None
        else SkillDemandMonthly.role_id == role_id
    )
    current = await session.scalar(select(func.max(SkillDemandMonthly.month)).where(cond))
    thresholds = {
        "min_postings": float(settings.ANALYTICS_MIN_POSTINGS),
        "emerging_prev_max": EMERGING_PREV_MAX,
        "emerging_min_share": EMERGING_MIN_SHARE,
    }
    empty: dict[str, Any] = {
        "role": role,
        "current_month": current,
        "previous_month": add_months(current, -1) if current else None,
        "current_postings": 0,
        "previous_postings": 0,
        "low_sample": True,
        "thresholds": thresholds,
        "growing": [],
        "declining": [],
        "emerging": [],
    }
    if current is None:
        return empty
    previous = add_months(current, -1)
    totals = await monthly_totals(session, role_id)
    cur_n, prev_n = totals.get(current, 0), totals.get(previous, 0)
    empty.update(current_postings=cur_n, previous_postings=prev_n)
    if min(cur_n, prev_n) < settings.ANALYTICS_MIN_POSTINGS:
        return empty
    result = compute_movers(
        await month_shares(session, previous, role_id),
        await month_shares(session, current, role_id),
        limit,
    )
    skills = await _skills_by_id(session, {m.skill_id for ms in result.values() for m in ms})

    def out(m: Any) -> dict[str, Any]:
        return {
            "skill": _ref(skills[m.skill_id]),
            "share_prev": round(m.share_prev, 4),
            "share_curr": round(m.share_curr, 4),
            "change_pp": round(m.change_pp, 4),
            "change_rel": None if m.change_rel is None else round(m.change_rel, 4),
        }

    empty.update(low_sample=False, **{k: [out(m) for m in v] for k, v in result.items()})
    return empty
