"""Celery tasks. Each is idempotent: re-running it after a crash gives the same end state."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import IngestionRun, JobSource
from app.services.analytics.demand import refresh_monthly_demand
from app.services.curriculum.service import parse_document
from app.services.extraction.service import extract_pending, mark_stale
from app.services.ingestion.adzuna import AdzunaConnector
from app.services.ingestion.base import IngestionConfigError
from app.services.ingestion.runner import execute_run
from app.workers.celery_app import celery_app
from app.workers.db import run_with_db

logger = logging.getLogger(__name__)


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    return {"status": "ok", "at": datetime.now(tz=UTC).isoformat()}


async def _refresh(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as session:
        rows = await refresh_monthly_demand(session)
        await session.commit()
    return rows


async def ingest_and_process(
    factory: async_sessionmaker[AsyncSession], run_id: int
) -> dict[str, Any]:
    """Fetch, store, extract skills from new postings, refresh the demand series."""
    async with factory() as session:
        run = await session.get(IngestionRun, run_id)
        if run is None:
            raise LookupError(f"ingestion run {run_id} not found")
        source = await session.scalar(select(JobSource).where(JobSource.id == run.source_id))
        if source is None:
            raise RuntimeError("source disappeared during processing")
        if source.key != "adzuna":
            raise IngestionConfigError(f"No queued connector for source '{source.key}'")
    connector = AdzunaConnector(get_settings())
    counts = await execute_run(factory, run_id, connector)
    extracted = await extract_pending(factory)
    demand_rows = await _refresh(factory)
    return {
        "run_id": run_id,
        "inserted": counts.inserted,
        "duplicates": counts.duplicates,
        "errors": counts.errors,
        "extracted": extracted,
        "demand_rows": demand_rows,
    }


@celery_app.task(name="ingestion.run")
def ingestion_run(run_id: int) -> dict[str, Any]:
    return run_with_db(lambda f: ingest_and_process(f, run_id))


@celery_app.task(name="extraction.extract_pending")
def extraction_pending() -> dict[str, int]:
    async def body(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
        done = await extract_pending(factory)
        return {"extracted": done, "demand_rows": await _refresh(factory)}

    return run_with_db(body)


@celery_app.task(name="extraction.reextract_stale")
def extraction_reextract_stale() -> dict[str, int]:
    """After a taxonomy or calibration change: re-extract postings from older versions."""

    async def body(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
        async with factory() as session:
            marked = await mark_stale(session)
            await session.commit()
        done = await extract_pending(factory)
        return {"marked": marked, "extracted": done, "demand_rows": await _refresh(factory)}

    return run_with_db(body)


@celery_app.task(name="analytics.refresh_demand")
def analytics_refresh_demand() -> dict[str, int]:
    return {"rows": run_with_db(_refresh)}


@celery_app.task(name="curriculum.parse_document")
def curriculum_parse_document(document_id: int) -> dict[str, Any]:
    async def body(factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
        doc = await parse_document(factory, document_id, get_settings())
        return {"document_id": doc.id, "status": doc.status, "units": doc.units_parsed}

    return run_with_db(body)
