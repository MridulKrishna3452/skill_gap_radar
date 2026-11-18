"""Job sources and ingestion runs.

Phase 2 restricts triggering runs to admins; until then the API is only exposed on localhost.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import Pagination, get_app_settings, get_db, get_task_queue, pagination
from app.api.v1.schemas import IngestionRunIn, IngestionRunOut, Page, SourceOut
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError, ServiceUnavailableError
from app.models import IngestionRun, JobSource
from app.services.ingestion.adzuna import AdzunaConnector
from app.services.ingestion.base import IngestionConfigError
from app.services.ingestion.runner import create_run
from app.workers.queue import TaskQueue

router = APIRouter(tags=["ingestion"])


@router.get("/sources", response_model=list[SourceOut], summary="Registered job sources")
async def list_sources(session: AsyncSession = Depends(get_db)) -> list[JobSource]:
    return list((await session.scalars(select(JobSource).order_by(JobSource.key))).all())


@router.post(
    "/ingestion/runs",
    response_model=IngestionRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an ingestion run",
    description="Queues a fetch from the source. Extraction and the demand time series are "
    "refreshed automatically when the run finishes. Returns 503 if the source is not "
    "configured (e.g. Adzuna credentials missing).",
)
async def start_run(
    body: IngestionRunIn,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    queue: TaskQueue = Depends(get_task_queue),
) -> IngestionRun:
    if not settings.adzuna_enabled:
        raise ServiceUnavailableError(
            "Adzuna is not configured: set ADZUNA_APP_ID and ADZUNA_APP_KEY"
        )
    try:
        params = AdzunaConnector.validate_params(
            body.params.model_dump(exclude_none=True), settings.ADZUNA_MAX_PAGES_PER_RUN
        )
    except IngestionConfigError as exc:
        raise AppError(str(exc)) from exc
    source = await session.scalar(select(JobSource).where(JobSource.key == body.source))
    if source is None:
        raise NotFoundError(f"Source '{body.source}' is not registered (run the seed command)")
    run = await create_run(session, source, params)
    await session.commit()
    await queue.send("ingestion.run", run.id)
    await session.refresh(run, ["source"])
    return run


@router.get("/ingestion/runs", response_model=Page[IngestionRunOut], summary="Ingestion runs")
async def list_runs(
    page: Pagination = Depends(pagination),
    source: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conds = (
        [IngestionRun.source_id.in_(select(JobSource.id).where(JobSource.key == source))]
        if source
        else []
    )
    total = await session.scalar(select(func.count()).select_from(IngestionRun).where(*conds)) or 0
    rows = (
        await session.scalars(
            select(IngestionRun)
            .where(*conds)
            .options(selectinload(IngestionRun.source))
            .order_by(IngestionRun.id.desc())
            .limit(page.limit)
            .offset(page.offset)
        )
    ).all()
    return {"items": rows, "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/ingestion/runs/{run_id}", response_model=IngestionRunOut, summary="One ingestion run")
async def get_run(run_id: int, session: AsyncSession = Depends(get_db)) -> IngestionRun:
    run = await session.scalar(
        select(IngestionRun)
        .where(IngestionRun.id == run_id)
        .options(selectinload(IngestionRun.source))
    )
    if run is None:
        raise NotFoundError(f"Ingestion run {run_id} not found")
    return run
