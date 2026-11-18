"""Monthly skill demand trends (shares, not counts) and month-over-month change.

    share_t       = postings in month t mentioning the skill / postings in month t
    change_pp     = share_t - share_{t-1}                   (percentage points, as a fraction)
    change_rel    = change_pp / share_{t-1}                  (None when share_{t-1} = 0)

Movers compare the latest month with data to the month before it. Both months need at least
`min_postings` postings, otherwise the result is flagged and no movers are listed.

    growing   : change_pp > 0, largest first
    declining : change_pp < 0, most negative first
    emerging  : share_{t-1} < EMERGING_PREV_MAX and share_t >= EMERGING_MIN_SHARE
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SkillDemandMonthly
from app.services.analytics.demand import add_months, monthly_totals

EMERGING_PREV_MAX = 0.01
EMERGING_MIN_SHARE = 0.03


@dataclass(frozen=True)
class SeriesPoint:
    month: date
    total_postings: int
    postings_with_skill: int
    share: float
    change_pp: float | None
    change_rel: float | None


def build_series(totals: Mapping[date, int], counts: Mapping[date, int]) -> list[SeriesPoint]:
    """Monthly share series over every month that has postings; missing months are 0 for the
    skill (the month had postings, none mentioned it)."""
    points: list[SeriesPoint] = []
    prev: SeriesPoint | None = None
    for month in sorted(totals):
        total = totals[month]
        k = counts.get(month, 0)
        share = k / total if total else 0.0
        change_pp = change_rel = None
        if prev is not None and prev.month == add_months(month, -1):
            change_pp = share - prev.share
            change_rel = change_pp / prev.share if prev.share > 0 else None
        point = SeriesPoint(month, total, k, share, change_pp, change_rel)
        points.append(point)
        prev = point
    return points


@dataclass(frozen=True)
class Mover:
    skill_id: int
    share_prev: float
    share_curr: float
    change_pp: float
    change_rel: float | None


def compute_movers(
    prev: Mapping[int, float], curr: Mapping[int, float], limit: int
) -> dict[str, list[Mover]]:
    movers = []
    for skill_id in set(prev) | set(curr):
        p, c = prev.get(skill_id, 0.0), curr.get(skill_id, 0.0)
        movers.append(Mover(skill_id, p, c, c - p, (c - p) / p if p > 0 else None))
    growing = sorted(
        (m for m in movers if m.change_pp > 0), key=lambda m: (-m.change_pp, m.skill_id)
    )
    declining = sorted(
        (m for m in movers if m.change_pp < 0), key=lambda m: (m.change_pp, m.skill_id)
    )
    emerging = sorted(
        (
            m
            for m in movers
            if m.share_prev < EMERGING_PREV_MAX and m.share_curr >= EMERGING_MIN_SHARE
        ),
        key=lambda m: (-m.share_curr, m.skill_id),
    )
    return {
        "growing": growing[:limit],
        "declining": declining[:limit],
        "emerging": emerging[:limit],
    }


async def skill_month_counts(
    session: AsyncSession, skill_id: int, role_id: int | None
) -> dict[date, int]:
    cond = (
        SkillDemandMonthly.role_id.is_(None)
        if role_id is None
        else SkillDemandMonthly.role_id == role_id
    )
    rows = (
        await session.execute(
            select(SkillDemandMonthly.month, SkillDemandMonthly.postings_with_skill).where(
                SkillDemandMonthly.skill_id == skill_id, cond
            )
        )
    ).all()
    return {r[0]: int(r[1]) for r in rows}


async def month_shares(session: AsyncSession, month: date, role_id: int | None) -> dict[int, float]:
    cond = (
        SkillDemandMonthly.role_id.is_(None)
        if role_id is None
        else SkillDemandMonthly.role_id == role_id
    )
    rows = (
        await session.execute(
            select(SkillDemandMonthly.skill_id, SkillDemandMonthly.share).where(
                SkillDemandMonthly.month == month, cond
            )
        )
    ).all()
    return {r[0]: float(r[1]) for r in rows}


async def series_for_skill(
    session: AsyncSession, skill_id: int, role_id: int | None
) -> list[SeriesPoint]:
    totals = await monthly_totals(session, role_id)
    counts = await skill_month_counts(session, skill_id, role_id)
    return build_series(totals, counts)
