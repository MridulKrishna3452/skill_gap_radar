"""Job postings (v1: GET /jobs, the jobs table and its CSV export)."""

import csv
import io
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import Pagination, current_user, expensive_rate_limit, get_db, pagination
from app.api.v1.schemas import JobDetail, JobFacets, JobSummary, Page
from app.core.errors import NotFoundError
from app.models import Company, JobPosting, JobSource, PostingSkill, Role, Skill

router = APIRouter(prefix="/jobs", tags=["jobs"])


def escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _skill_ref(skill: Skill) -> dict[str, Any]:
    return {"id": skill.id, "slug": skill.slug, "name": skill.name}


def _summary(
    p: JobPosting, skills: dict[int, Skill], roles: dict[int, str], detail: bool
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": p.id,
        "title": p.title,
        "company": p.company.name if p.company else None,
        "location": p.location,
        "country": p.country,
        "posted_at": p.posted_at,
        "source": {
            "key": p.source.key,
            "name": p.source.name,
            "is_synthetic": p.source.is_synthetic,
        },
        "role": roles.get(p.role_id) if p.role_id else None,
        "url": p.url,
        "salary_min": float(p.salary_min) if p.salary_min is not None else None,
        "salary_max": float(p.salary_max) if p.salary_max is not None else None,
        "salary_currency": p.salary_currency,
        "salary_is_estimated": p.salary_is_estimated,
        "employment_type": p.employment_type,
        "extraction_status": p.extraction_status,
    }
    ps = sorted(p.skills, key=lambda s: (-s.confidence, s.skill_id))
    if not detail:
        ps = [s for s in ps if not s.implied]
    out["skills"] = [
        {
            "skill": _skill_ref(skills[s.skill_id]),
            "requirement": s.requirement,
            "confidence": s.confidence,
            "implied": s.implied,
            **({"evidence": s.evidence} if detail else {}),
        }
        for s in ps
    ]
    if detail:
        out.update(
            description=p.description,
            location_raw=p.location_raw,
            category=p.category,
            experience_text=p.experience_text,
            extractor_version=p.extractor_version,
        )
    return out


async def _lookups(
    session: AsyncSession, postings: list[JobPosting]
) -> tuple[dict[int, Skill], dict[int, str]]:
    ids = {s.skill_id for p in postings for s in p.skills}
    skills = {
        s.id: s for s in (await session.scalars(select(Skill).where(Skill.id.in_(ids)))).all()
    }
    roles = {r.id: r.slug for r in (await session.scalars(select(Role))).all()}
    return skills, roles


def job_filters(
    q: str | None = Query(None, max_length=100, description="Text in the title"),
    source: str | None = Query(None, description="Source key, e.g. adzuna"),
    location: str | None = Query(None, max_length=100, description="Normalised location"),
    company: str | None = Query(None, max_length=100, description="Text in the company name"),
    skill: str | None = Query(None, description="Skill slug; postings that mention it"),
    requirement: str | None = Query(
        None,
        pattern="^(required|nice_to_have|unspecified)$",
        description="With skill: only postings where it has this requirement level",
    ),
    role: str | None = Query(None, description="Role slug"),
    posted_from: date | None = Query(None),
    posted_to: date | None = Query(None, description="Inclusive"),
    include_synthetic: bool = Query(False, description="Include synthetic (test) sources"),
) -> list[ColumnElement[bool]]:
    """Shared filters for listing, exporting and summarising postings."""
    conds: list[ColumnElement[bool]] = []
    if not include_synthetic:
        conds.append(
            JobPosting.source_id.in_(select(JobSource.id).where(JobSource.is_synthetic.is_(False)))
        )
    if q:
        conds.append(JobPosting.title.ilike(f"%{escape_like(q)}%", escape="\\"))
    if source:
        conds.append(JobPosting.source_id.in_(select(JobSource.id).where(JobSource.key == source)))
    if location:
        conds.append(JobPosting.location.ilike(escape_like(location), escape="\\"))
    if company:
        conds.append(
            JobPosting.company_id.in_(
                select(Company.id).where(
                    Company.name.ilike(f"%{escape_like(company)}%", escape="\\")
                )
            )
        )
    if skill:
        sub = (
            select(PostingSkill.posting_id)
            .join(Skill, Skill.id == PostingSkill.skill_id)
            .where(Skill.slug == skill)
        )
        if requirement:
            sub = sub.where(PostingSkill.requirement == requirement)
        conds.append(JobPosting.id.in_(sub))
    if role:
        conds.append(JobPosting.role_id.in_(select(Role.id).where(Role.slug == role)))
    if posted_from:
        conds.append(JobPosting.posted_at >= datetime.combine(posted_from, time(), tzinfo=UTC))
    if posted_to:
        conds.append(
            JobPosting.posted_at
            < datetime.combine(posted_to + timedelta(days=1), time(), tzinfo=UTC)
        )
    return conds


@router.get("", response_model=Page[JobSummary], summary="List job postings")
async def list_jobs(
    page: Pagination = Depends(pagination),
    conds: list[ColumnElement[bool]] = Depends(job_filters),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    total = await session.scalar(select(func.count()).select_from(JobPosting).where(*conds)) or 0
    postings = list(
        (
            await session.scalars(
                select(JobPosting)
                .where(*conds)
                .options(
                    selectinload(JobPosting.company),
                    selectinload(JobPosting.source),
                    selectinload(JobPosting.skills),
                )
                .order_by(JobPosting.posted_at.desc(), JobPosting.id.desc())
                .limit(page.limit)
                .offset(page.offset)
            )
        ).all()
    )
    skills, roles = await _lookups(session, postings)
    return {
        "items": [_summary(p, skills, roles, detail=False) for p in postings],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
    }


EXPORT_MAX_ROWS = 10_000
EXPORT_COLUMNS = [
    "id",
    "title",
    "company",
    "location",
    "country",
    "posted_at",
    "source",
    "role",
    "url",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_is_estimated",
    "employment_type",
    "skills_required",
    "skills_nice_to_have",
    "skills_unspecified",
]


@router.get(
    "/export",
    summary="Download postings as CSV (v1: 'Export jobs CSV')",
    description=f"Same filters as GET /jobs. At most {EXPORT_MAX_ROWS} rows, newest first. "
    "Skill columns list directly mentioned skills (not implied ones), separated by ';'.",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
    # Signed-in users only, and rate-limited: a full export is the most expensive read.
    dependencies=[Depends(current_user), Depends(expensive_rate_limit)],
)
async def export_jobs(
    limit: int = Query(EXPORT_MAX_ROWS, ge=1, le=EXPORT_MAX_ROWS),
    conds: list[ColumnElement[bool]] = Depends(job_filters),
    session: AsyncSession = Depends(get_db),
) -> Response:
    postings = list(
        (
            await session.scalars(
                select(JobPosting)
                .where(*conds)
                .options(
                    selectinload(JobPosting.company),
                    selectinload(JobPosting.source),
                    selectinload(JobPosting.skills),
                )
                .order_by(JobPosting.posted_at.desc(), JobPosting.id.desc())
                .limit(limit)
            )
        ).all()
    )
    skills, roles = await _lookups(session, postings)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    for p in postings:
        s = _summary(p, skills, roles, detail=False)
        by_req: dict[str, list[str]] = {"required": [], "nice_to_have": [], "unspecified": []}
        for item in s["skills"]:
            by_req[item["requirement"]].append(item["skill"]["name"])
        writer.writerow(
            [
                s["id"],
                s["title"],
                s["company"],
                s["location"],
                s["country"],
                s["posted_at"].isoformat(),
                s["source"]["key"],
                s["role"],
                s["url"],
                s["salary_min"],
                s["salary_max"],
                s["salary_currency"],
                s["salary_is_estimated"],
                s["employment_type"],
                "; ".join(by_req["required"]),
                "; ".join(by_req["nice_to_have"]),
                "; ".join(by_req["unspecified"]),
            ]
        )
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="jobs.csv"'},
    )


@router.get(
    "/facets",
    response_model=JobFacets,
    summary="Posting counts by role, source, category, location and month",
    description="Same filters as GET /jobs. Replaces v1's 'Job Market Distribution by Role' "
    "chart and headline counts, computed from stored postings.",
)
async def job_facets(
    top: int = Query(20, ge=1, le=100, description="Max buckets for category and location"),
    conds: list[ColumnElement[bool]] = Depends(job_filters),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    total = await session.scalar(select(func.count()).select_from(JobPosting).where(*conds)) or 0

    async def bucket(
        key: Any, join: tuple[Any, Any] | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        stmt = select(key, func.count()).select_from(JobPosting)
        if join is not None:
            stmt = stmt.outerjoin(*join)
        stmt = stmt.where(*conds).group_by(key).order_by(func.count().desc(), key)
        if limit:
            stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).all()
        return [{"key": None if k is None else str(k), "count": int(n)} for k, n in rows]

    month = func.to_char(func.timezone("UTC", JobPosting.posted_at), "YYYY-MM")
    return {
        "total": total,
        "by_role": await bucket(Role.slug, (Role, Role.id == JobPosting.role_id)),
        "by_source": await bucket(JobSource.key, (JobSource, JobSource.id == JobPosting.source_id)),
        "by_category": await bucket(JobPosting.category, limit=top),
        "by_location": await bucket(JobPosting.location, limit=top),
        "by_month": sorted(await bucket(month), key=lambda b: b["key"] or ""),
    }


@router.get("/{job_id}", response_model=JobDetail, summary="Get one posting with skill evidence")
async def get_job(job_id: int, session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    posting = await session.scalar(
        select(JobPosting)
        .where(JobPosting.id == job_id)
        .options(
            selectinload(JobPosting.company),
            selectinload(JobPosting.source),
            selectinload(JobPosting.skills),
        )
    )
    if posting is None:
        raise NotFoundError(f"Job {job_id} not found")
    skills, roles = await _lookups(session, [posting])
    return _summary(posting, skills, roles, detail=True)
