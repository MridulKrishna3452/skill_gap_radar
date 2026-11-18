"""Role recommendations: which skills to learn for a target role, in priority order.

Candidates are the role's editorial core skills (v1 role_requirements, where defined) plus the
skills most demanded in recent postings for that role. Each candidate gets:

- demand_share: share of the role's postings in the window that mention it (from data);
- coverage: the program's coverage of it, when a program is given;
- priority from demand_share, replacing v1's fixed frequency cut-offs (>15 / >5 mentions):
      high   >= PRIORITY_HIGH
      medium >= PRIORITY_MEDIUM
      low    otherwise
  and "insufficient_data" when the role has fewer than min_postings postings in the window;
- learning content: v1's curated roadmap text, labelled editorial, where it exists. v1's
  generic placeholder roadmap ("Fundamentals", ...) for other skills is not reproduced.

A skill is recommended when the program covers it below COVERED_THRESHOLD, or always when no
program is given.
"""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import LearningContent, Program, Role, RoleSkill, Skill
from app.services.analytics.demand import resolve_window, window_demand
from app.services.analytics.gap import program_coverage_map

PRIORITY_HIGH = 0.30
PRIORITY_MEDIUM = 0.10
COVERED_THRESHOLD = 0.7
MARKET_CANDIDATES = 10
MARKET_MIN_SHARE = 0.10
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2, "insufficient_data": 3}


def priority_for(share: float, total_postings: int, min_postings: int) -> str:
    if total_postings < min_postings:
        return "insufficient_data"
    if share >= PRIORITY_HIGH:
        return "high"
    if share >= PRIORITY_MEDIUM:
        return "medium"
    return "low"


def coverage_status(coverage: float) -> str:
    if coverage >= COVERED_THRESHOLD:
        return "covered"
    return "partial" if coverage > 0 else "missing"


async def recommend(
    session: AsyncSession,
    *,
    role_slug: str,
    program_id: int | None,
    months: int,
    as_of: date | None,
    min_postings: int,
) -> dict[str, Any]:
    role = await session.scalar(select(Role).where(Role.slug == role_slug))
    if role is None:
        raise NotFoundError(f"Role '{role_slug}' not found")
    program = None
    coverage: dict[int, float] = {}
    if program_id is not None:
        program = await session.get(Program, program_id)
        if program is None:
            raise NotFoundError(f"Program {program_id} not found")
        coverage, _ = await program_coverage_map(session, program_id)

    window = await resolve_window(session, months, as_of)
    total, demand = (0, []) if window is None else await window_demand(session, window, role.id)
    share = {d.skill_id: d.postings_with_skill / total for d in demand} if total else {}

    core = [
        rs.skill_id
        for rs in (
            await session.scalars(
                select(RoleSkill).where(RoleSkill.role_id == role.id).order_by(RoleSkill.position)
            )
        ).all()
    ]
    market = [
        sid
        for sid, s in sorted(share.items(), key=lambda kv: (-kv[1], kv[0]))
        if s >= MARKET_MIN_SHARE
    ][:MARKET_CANDIDATES]
    if total < min_postings:
        market = []  # too few postings to call anything "most demanded"
    candidates = list(dict.fromkeys([*core, *market]))

    skills = {
        s.id: s
        for s in (await session.scalars(select(Skill).where(Skill.id.in_(candidates)))).all()
    }
    content = {
        c.skill_id: c
        for c in (
            await session.scalars(
                select(LearningContent).where(LearningContent.skill_id.in_(candidates))
            )
        ).all()
    }

    items: list[dict[str, Any]] = []
    for sid in candidates:
        cov = coverage.get(sid, 0.0)
        if program is not None and cov >= COVERED_THRESHOLD:
            continue
        lc = content.get(sid)
        s = share.get(sid, 0.0)
        items.append(
            {
                "skill": {"id": sid, "slug": skills[sid].slug, "name": skills[sid].name},
                "reason": [
                    r
                    for r, ok in (
                        ("role_core_skill", sid in core),
                        ("market_demand", sid in market),
                    )
                    if ok
                ],
                "priority": priority_for(s, total, min_postings),
                "demand_share": round(s, 4),
                "coverage": round(cov, 4) if program is not None else None,
                "coverage_status": coverage_status(cov) if program is not None else None,
                "learning": (
                    {
                        "difficulty": lc.difficulty,
                        "estimated_weeks": lc.estimated_weeks,
                        "steps": lc.steps,
                        "content_source": lc.content_source,
                    }
                    if lc
                    else None
                ),
            }
        )
    items.sort(
        key=lambda i: (_PRIORITY_RANK[i["priority"]], -i["demand_share"], i["skill"]["slug"])
    )
    return {
        "role": {"slug": role.slug, "name": role.name},
        "program": {"id": program.id, "name": program.name} if program else None,
        "window": {
            "start": window.start.isoformat() if window else None,
            "end_exclusive": window.end.isoformat() if window else None,
            "months": months,
        },
        "role_postings": total,
        "low_sample": total < min_postings,
        "thresholds": {
            "priority_high": PRIORITY_HIGH,
            "priority_medium": PRIORITY_MEDIUM,
            "covered": COVERED_THRESHOLD,
            "min_postings": min_postings,
        },
        "items": items,
    }
