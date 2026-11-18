"""Derived analytics: monthly skill demand time series and stored gap reports.

Both are recomputed from job_postings / posting_skills / unit_skills; nothing here is entered
by hand.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SkillDemandMonthly(Base):
    """Share of (non-synthetic) postings in a month that mention a skill.

    role_id NULL is the all-roles series. NULLS NOT DISTINCT keeps one row per
    (skill, month, role) including the NULL role.
    """

    __tablename__ = "skill_demand_monthly"
    __table_args__ = (
        UniqueConstraint("skill_id", "month", "role_id", postgresql_nulls_not_distinct=True),
        CheckConstraint("share >= 0 AND share <= 1", name="share"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date, index=True)  # first day of the month
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    postings_with_skill: Mapped[int] = mapped_column(Integer)
    required_postings: Mapped[int] = mapped_column(Integer)
    total_postings: Mapped[int] = mapped_column(Integer)
    share: Mapped[float] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GapReport(Base):
    __tablename__ = "gap_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    window_start: Mapped[date] = mapped_column(Date)
    window_end: Mapped[date] = mapped_column(Date)
    postings_considered: Mapped[int] = mapped_column(Integer)
    weighted_coverage: Mapped[float | None] = mapped_column(Float)
    top_n_coverage: Mapped[float | None] = mapped_column(Float)
    # Full result (per-skill rows, parameters) as returned by the API.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
