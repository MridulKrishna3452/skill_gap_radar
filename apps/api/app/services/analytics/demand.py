"""Skill demand from stored postings.

Demand share of a skill = postings mentioning it / all postings, over the same set of
postings (a window, a month, a role). Shares, not raw counts, so months with more postings
do not look like "more demand" (v1 compared raw counts).

Only postings from non-synthetic sources with completed extraction are counted.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import ColumnElement, Integer, and_, cast, delete, func, insert, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobPosting, JobSource, PostingSkill, SkillDemandMonthly


def counted_postings() -> ColumnElement[bool]:
    """Filter for postings that count in analytics."""
    return and_(
        JobPosting.extraction_status == "done",
        JobPosting.source_id.in_(select(JobSource.id).where(JobSource.is_synthetic.is_(False))),
    )


def month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


@dataclass(frozen=True)
class Window:
    start: date  # inclusive, first of month
    end: date  # exclusive, first of the month after the last included month

    @property
    def last_month(self) -> date:
        return add_months(self.end, -1)

    @property
    def start_dt(self) -> datetime:
        return datetime.combine(self.start, time(), tzinfo=UTC)

    @property
    def end_dt(self) -> datetime:
        return datetime.combine(self.end, time(), tzinfo=UTC)


async def latest_data_month(session: AsyncSession) -> date | None:
    latest = await session.scalar(select(func.max(JobPosting.posted_at)).where(counted_postings()))
    return month_floor(latest.astimezone(UTC).date()) if latest else None


async def resolve_window(session: AsyncSession, months: int, as_of: date | None) -> Window | None:
    """Window of `months` whole months ending with as_of's month, or with the latest month that
    has data. None when there is no data at all."""
    last = month_floor(as_of) if as_of else await latest_data_month(session)
    if last is None:
        return None
    return Window(start=add_months(last, -(months - 1)), end=add_months(last, 1))


@dataclass(frozen=True)
class SkillDemand:
    skill_id: int
    postings_with_skill: int
    required_postings: int


async def window_demand(
    session: AsyncSession, window: Window, role_id: int | None
) -> tuple[int, list[SkillDemand]]:
    """(total postings in window, per-skill posting counts) for a role or all roles."""
    conds = [
        counted_postings(),
        JobPosting.posted_at >= window.start_dt,
        JobPosting.posted_at < window.end_dt,
    ]
    if role_id is not None:
        conds.append(JobPosting.role_id == role_id)
    total = await session.scalar(select(func.count()).select_from(JobPosting).where(*conds)) or 0
    rows = (
        await session.execute(
            select(
                PostingSkill.skill_id,
                func.count(),
                func.count().filter(PostingSkill.requirement == "required"),
            )
            .join(JobPosting, JobPosting.id == PostingSkill.posting_id)
            .where(*conds)
            .group_by(PostingSkill.skill_id)
        )
    ).all()
    return int(total), [SkillDemand(r[0], int(r[1]), int(r[2])) for r in rows]


async def refresh_monthly_demand(session: AsyncSession) -> int:
    """Rebuild skill_demand_monthly from postings. Returns the number of rows written."""
    await session.execute(delete(SkillDemandMonthly))
    month = func.date_trunc("month", func.timezone("UTC", JobPosting.posted_at)).cast(
        SkillDemandMonthly.month.type
    )
    written = 0
    for by_role in (False, True):
        role_col = JobPosting.role_id if by_role else cast(null(), Integer).label("role_id")
        base_where = [counted_postings()]
        if by_role:
            base_where.append(JobPosting.role_id.is_not(None))
        totals = (
            select(month.label("month"), role_col.label("role_id"), func.count().label("n"))
            .where(*base_where)
            .group_by(month, *([JobPosting.role_id] if by_role else []))
            .subquery()
        )
        per_skill = (
            select(
                PostingSkill.skill_id.label("skill_id"),
                month.label("month"),
                role_col.label("role_id"),
                func.count().label("k"),
                func.count().filter(PostingSkill.requirement == "required").label("req"),
            )
            .join(JobPosting, JobPosting.id == PostingSkill.posting_id)
            .where(*base_where)
            .group_by(PostingSkill.skill_id, month, *([JobPosting.role_id] if by_role else []))
            .subquery()
        )
        join_cond = per_skill.c.month == totals.c.month
        if by_role:
            join_cond = and_(join_cond, per_skill.c.role_id == totals.c.role_id)
        source = select(
            per_skill.c.skill_id,
            per_skill.c.month,
            per_skill.c.role_id,
            per_skill.c.k,
            per_skill.c.req,
            totals.c.n,
            (per_skill.c.k * 1.0 / totals.c.n),
        ).join(totals, join_cond)
        result = await session.execute(
            insert(SkillDemandMonthly).from_select(
                [
                    "skill_id",
                    "month",
                    "role_id",
                    "postings_with_skill",
                    "required_postings",
                    "total_postings",
                    "share",
                ],
                source,
            )
        )
        written += int(result.rowcount or 0)  # type: ignore[attr-defined]
    return written


async def monthly_totals(session: AsyncSession, role_id: int | None) -> dict[date, int]:
    """Counted postings per month (all roles, or one role)."""
    month = func.date_trunc("month", func.timezone("UTC", JobPosting.posted_at))
    conds = [counted_postings()]
    if role_id is not None:
        conds.append(JobPosting.role_id == role_id)
    rows = (await session.execute(select(month, func.count()).where(*conds).group_by(month))).all()
    return {r[0].date(): int(r[1]) for r in rows}
