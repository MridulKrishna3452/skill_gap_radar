"""Program-vs-market skill gap, per program and (optionally) per role.

For every skill demanded in the window (d > 0):

    d_s   = postings mentioning s / postings in window            (demand share, 0-1)
    c_s   = program coverage of s (max unit grade, 0-1)            (see curriculum/coverage.py)
    gap_s = d_s * (1 - c_s)

Summary numbers:

    weighted_coverage = sum(d_s * c_s) / sum(d_s)     demand-weighted coverage over ALL
                                                      demanded skills
    top_n_coverage    = mean(c_s) over the N skills with the highest d_s
    gap_index         = 1 - weighted_coverage

v1 bug fixed here: v1 sorted skills by gap and then measured coverage over the top 20 of
that list, i.e. over the skills it had just selected for being uncovered, which understates
coverage. The top-N used here is chosen by demand, independent of coverage.
"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import (
    Course,
    CourseUnit,
    GapReport,
    Program,
    Role,
    Skill,
    UnitSkill,
)
from app.services.analytics.demand import SkillDemand, resolve_window, window_demand

DEFAULT_TOP_N = 20


@dataclass(frozen=True)
class GapRow:
    skill_id: int
    demand_share: float
    required_share: float
    postings_with_skill: int
    coverage: float
    gap: float


@dataclass(frozen=True)
class GapSummary:
    total_postings: int
    skills_in_demand: int
    weighted_coverage: float | None
    top_n: int
    top_n_coverage: float | None
    top_n_covered_count: int
    gap_index: float | None


def compute_gap(
    total_postings: int,
    demand: Sequence[SkillDemand],
    coverage: Mapping[int, float],
    top_n: int = DEFAULT_TOP_N,
) -> tuple[GapSummary, list[GapRow]]:
    rows: list[GapRow] = []
    if total_postings > 0:
        for d in demand:
            if d.postings_with_skill <= 0:
                continue
            share = d.postings_with_skill / total_postings
            c = coverage.get(d.skill_id, 0.0)
            rows.append(
                GapRow(
                    skill_id=d.skill_id,
                    demand_share=share,
                    required_share=d.required_postings / total_postings,
                    postings_with_skill=d.postings_with_skill,
                    coverage=c,
                    gap=share * (1 - c),
                )
            )
    rows.sort(key=lambda r: (-r.gap, -r.demand_share, r.skill_id))

    total_d = sum(r.demand_share for r in rows)
    weighted = sum(r.demand_share * r.coverage for r in rows) / total_d if total_d else None
    by_demand = sorted(rows, key=lambda r: (-r.demand_share, r.skill_id))[:top_n]
    top_cov = sum(r.coverage for r in by_demand) / len(by_demand) if by_demand else None
    summary = GapSummary(
        total_postings=total_postings,
        skills_in_demand=len(rows),
        weighted_coverage=weighted,
        top_n=len(by_demand),
        top_n_coverage=top_cov,
        top_n_covered_count=sum(1 for r in by_demand if r.coverage > 0),
        gap_index=None if weighted is None else 1 - weighted,
    )
    return summary, rows


async def program_coverage_map(
    session: AsyncSession, program_id: int
) -> tuple[dict[int, float], dict[int, list[dict[str, Any]]]]:
    """skill_id -> program coverage, and skill_id -> the best covering units (up to 3)."""
    rows = (
        await session.execute(
            select(
                UnitSkill.skill_id,
                UnitSkill.coverage,
                CourseUnit.id,
                CourseUnit.title,
                Course.title,
            )
            .join(CourseUnit, CourseUnit.id == UnitSkill.unit_id)
            .join(Course, Course.id == CourseUnit.course_id)
            .where(Course.program_id == program_id)
            .order_by(UnitSkill.coverage.desc(), CourseUnit.id)
        )
    ).all()
    coverage: dict[int, float] = {}
    units: dict[int, list[dict[str, Any]]] = {}
    for skill_id, cov, unit_id, unit_title, course_title in rows:
        coverage[skill_id] = max(coverage.get(skill_id, 0.0), cov)
        lst = units.setdefault(skill_id, [])
        if len(lst) < 3:
            lst.append(
                {"unit_id": unit_id, "unit": unit_title, "course": course_title, "coverage": cov}
            )
    return coverage, units


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(x, nd)


async def gap_report(
    session: AsyncSession,
    *,
    program_id: int,
    role_slug: str | None,
    months: int,
    as_of: date | None,
    top_n: int,
    min_postings: int,
) -> GapReport:
    program = await session.get(Program, program_id)
    if program is None:
        raise NotFoundError(f"Program {program_id} not found")
    role = None
    if role_slug:
        role = await session.scalar(select(Role).where(Role.slug == role_slug))
        if role is None:
            raise NotFoundError(f"Role '{role_slug}' not found")

    coverage, units = await program_coverage_map(session, program_id)
    window = await resolve_window(session, months, as_of)
    demand: list[SkillDemand]
    if window is None:
        total, demand = 0, []
    else:
        total, demand = await window_demand(session, window, role.id if role else None)
    summary, rows = compute_gap(total, demand, coverage, top_n)

    skills = {
        s.id: s
        for s in (
            await session.scalars(select(Skill).where(Skill.id.in_([r.skill_id for r in rows])))
        ).all()
    }
    payload: dict[str, Any] = {
        "program": {"id": program.id, "name": program.name},
        "role": {"slug": role.slug, "name": role.name} if role else None,
        "window": {
            "start": window.start.isoformat() if window else None,
            "end_exclusive": window.end.isoformat() if window else None,
            "months": months,
        },
        "has_curriculum": bool(coverage),
        "low_sample": summary.total_postings < min_postings,
        "min_postings": min_postings,
        "summary": {k: (_r(v) if isinstance(v, float) else v) for k, v in asdict(summary).items()},
        "skills": [
            {
                "skill": {
                    "id": r.skill_id,
                    "slug": skills[r.skill_id].slug,
                    "name": skills[r.skill_id].name,
                    "category": skills[r.skill_id].category,
                },
                "demand_share": _r(r.demand_share),
                "required_share": _r(r.required_share),
                "postings_with_skill": r.postings_with_skill,
                "coverage": _r(r.coverage),
                "gap": _r(r.gap),
                "covered_in": units.get(r.skill_id, []),
            }
            for r in rows
        ],
    }
    report = GapReport(
        program_id=program.id,
        role_id=role.id if role else None,
        window_start=window.start if window else date.today().replace(day=1),
        window_end=window.end if window else date.today().replace(day=1),
        postings_considered=summary.total_postings,
        weighted_coverage=_r(summary.weighted_coverage),
        top_n_coverage=_r(summary.top_n_coverage),
        payload=payload,
    )
    session.add(report)
    await session.flush()
    return report


async def gap_by_role(
    session: AsyncSession,
    *,
    program_id: int,
    months: int,
    as_of: date | None,
    top_n: int,
    min_postings: int,
) -> dict[str, Any]:
    """Coverage of every role's demand by one program: the data behind v1's home-page radar
    ("Industry Demand vs Curriculum Coverage" per role), which v1 hardcoded."""
    program = await session.get(Program, program_id)
    if program is None:
        raise NotFoundError(f"Program {program_id} not found")
    coverage, _ = await program_coverage_map(session, program_id)
    window = await resolve_window(session, months, as_of)
    roles = (await session.scalars(select(Role).order_by(Role.name))).all()
    out = []
    for role in roles:
        total, demand = (0, []) if window is None else await window_demand(session, window, role.id)
        summary, _ = compute_gap(total, demand, coverage, top_n)
        out.append(
            {
                "role": {"id": role.id, "slug": role.slug, "name": role.name},
                "postings": total,
                "low_sample": total < min_postings,
                "weighted_coverage": _r(summary.weighted_coverage),
                "top_n_coverage": _r(summary.top_n_coverage),
                "gap_index": _r(summary.gap_index),
            }
        )
    return {
        "program": {"id": program.id, "name": program.name},
        "window": {
            "start": window.start.isoformat() if window else None,
            "end_exclusive": window.end.isoformat() if window else None,
            "months": months,
        },
        "has_curriculum": bool(coverage),
        "min_postings": min_postings,
        "roles": out,
    }
