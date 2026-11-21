"""Gap analysis and recommendations (v1: GET /gap, GET /recommendations)."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, expensive_rate_limit, get_app_settings, get_db
from app.api.v1.schemas import GapReportOut, RecommendationsResponse, RoleGapResponse
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models import GapReport
from app.services.analytics.gap import DEFAULT_TOP_N, gap_by_role, gap_report
from app.services.recommendations import recommend

# Gap endpoints store a report per call, so they need a signed-in user and a rate limit.
GAP_ACCESS = [Depends(current_user), Depends(expensive_rate_limit)]
router = APIRouter(tags=["analytics"])


def _report_out(report: GapReport) -> dict[str, Any]:
    return {"id": report.id, "computed_at": report.computed_at, **report.payload}


@router.get(
    "/gap",
    response_model=GapReportOut,
    summary="Skill gap between a program's curriculum and market demand",
    description="Computes the gap from current data and stores it as a report. "
    "gap = demand_share * (1 - coverage) per skill; see the field descriptions for the "
    "summary metrics.",
    dependencies=GAP_ACCESS,
)
async def get_gap(
    program_id: int = Query(..., description="Program whose curriculum is compared"),
    role: str | None = Query(None, description="Role slug; omit to compare with all postings"),
    months: int | None = Query(None, ge=1, le=60, description="Window length in months"),
    as_of: date | None = Query(None, description="Last month of the window (default: latest)"),
    top_n: int = Query(DEFAULT_TOP_N, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    report = await gap_report(
        session,
        program_id=program_id,
        role_slug=role,
        months=months or settings.ANALYTICS_DEFAULT_WINDOW_MONTHS,
        as_of=as_of,
        top_n=top_n,
        min_postings=settings.ANALYTICS_MIN_POSTINGS,
    )
    await session.refresh(report)
    return _report_out(report)


@router.get(
    "/gap/by-role",
    response_model=RoleGapResponse,
    summary="How well a program covers each role's demand",
    description="Per role: postings in the window and demand-weighted coverage. Replaces v1's "
    "hardcoded home-page radar with computed values.",
    dependencies=GAP_ACCESS,
)
async def get_gap_by_role(
    program_id: int = Query(...),
    months: int | None = Query(None, ge=1, le=60),
    as_of: date | None = Query(None),
    top_n: int = Query(DEFAULT_TOP_N, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    return await gap_by_role(
        session,
        program_id=program_id,
        months=months or settings.ANALYTICS_DEFAULT_WINDOW_MONTHS,
        as_of=as_of,
        top_n=top_n,
        min_postings=settings.ANALYTICS_MIN_POSTINGS,
    )


@router.get(
    "/gap/reports/{report_id}",
    response_model=GapReportOut,
    summary="A stored gap report",
    dependencies=GAP_ACCESS,
)
async def get_gap_report(report_id: int, session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    report = await session.get(GapReport, report_id)
    if report is None:
        raise NotFoundError(f"Gap report {report_id} not found")
    return _report_out(report)


@router.get(
    "/recommendations",
    response_model=RecommendationsResponse,
    summary="Skills to learn for a target role, prioritised by market demand",
)
async def get_recommendations(
    role: str = Query(..., description="Role slug, e.g. data-engineer (see GET /roles)"),
    program_id: int | None = Query(None, description="Skip skills this program already covers"),
    months: int | None = Query(None, ge=1, le=60),
    as_of: date | None = Query(None),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    return await recommend(
        session,
        role_slug=role,
        program_id=program_id,
        months=months or settings.ANALYTICS_DEFAULT_WINDOW_MONTHS,
        as_of=as_of,
        min_postings=settings.ANALYTICS_MIN_POSTINGS,
    )
