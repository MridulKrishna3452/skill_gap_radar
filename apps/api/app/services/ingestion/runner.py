"""Runs one ingestion: connector -> normalise -> dedup -> store, with tracked counts.

Dedup is enforced by the database: (source_id, external_id) and content_hash are unique, and
inserts use ON CONFLICT DO NOTHING, so re-running the same fetch inserts nothing new and
counts the rows as duplicates. Postings are committed in batches so a crash keeps progress.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Company, IngestionRun, JobPosting, JobSource
from app.services.ingestion.base import FetchProblem, RawPosting, SourceConnector
from app.services.normalize import (
    clean_html,
    company_key,
    content_hash,
    normalize_company,
    normalize_location,
    normalize_title,
)
from app.services.roles import classify_title, load_rules

logger = logging.getLogger(__name__)
BATCH_SIZE = 100
MAX_ERROR_SAMPLES = 20


@dataclass
class RunCounts:
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    errors: int = 0
    error_samples: list[str] = field(default_factory=list)
    inserted_ids: list[int] = field(default_factory=list)

    def problem(self, message: str) -> None:
        self.errors += 1
        if len(self.error_samples) < MAX_ERROR_SAMPLES:
            self.error_samples.append(message[:300])


async def get_or_create_source(
    session: AsyncSession,
    key: str,
    *,
    name: str | None = None,
    kind: str = "file",
    is_synthetic: bool = False,
    licence: str | None = None,
) -> JobSource:
    source = await session.scalar(select(JobSource).where(JobSource.key == key))
    if source is None:
        source = JobSource(
            key=key, name=name or key, kind=kind, is_synthetic=is_synthetic, licence=licence
        )
        session.add(source)
        await session.flush()
    return source


async def create_run(
    session: AsyncSession, source: JobSource, params: dict[str, Any]
) -> IngestionRun:
    run = IngestionRun(source_id=source.id, status="queued", params=params)
    session.add(run)
    await session.flush()
    return run


async def _company_id(session: AsyncSession, name: str | None, cache: dict[str, int]) -> int | None:
    normalized = normalize_company(name)
    if normalized is None:
        return None
    key = company_key(normalized)
    if not key:
        return None
    if key in cache:
        return cache[key]
    await session.execute(
        insert(Company)
        .values(name=normalized, normalized_name=key)
        .on_conflict_do_nothing(index_elements=["normalized_name"])
    )
    company_id = await session.scalar(select(Company.id).where(Company.normalized_name == key))
    if company_id is None:
        raise RuntimeError("company_id disappeared during processing")
    cache[key] = company_id
    return company_id


def _posting_values(raw: RawPosting) -> dict[str, Any]:
    title = normalize_title(raw.title)
    description = clean_html(raw.description, keep_lines=True)
    if not title or not description:
        raise ValueError("empty title or description after cleaning")
    return {
        "external_id": raw.external_id,
        "title": title[:500],
        "description": description,
        "location_raw": (raw.location or None) and raw.location[:500],
        "location": normalize_location(raw.location),
        "country": raw.country,
        "salary_min": raw.salary_min,
        "salary_max": raw.salary_max,
        "salary_currency": raw.salary_currency,
        "salary_is_estimated": raw.salary_is_estimated,
        "employment_type": raw.employment_type,
        "category": raw.category,
        "experience_text": raw.experience_text,
        "url": raw.url,
        "posted_at": raw.posted_at,
    }


async def execute_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: int,
    connector: SourceConnector,
) -> RunCounts:
    counts = RunCounts()
    async with session_factory() as session:
        run = await session.get(IngestionRun, run_id)
        if run is None:
            raise LookupError(f"ingestion run {run_id} not found")
        run.status = "running"
        run.started_at = datetime.now(tz=UTC)
        source_id, params = run.source_id, dict(run.params)
        await session.commit()

    companies: dict[str, int] = {}
    fatal = False
    try:
        async with session_factory() as session:
            rules = await load_rules(session)
            pending = 0
            async for item in connector.fetch(params):
                if isinstance(item, FetchProblem):
                    counts.problem(item.message)
                    if item.fatal:
                        fatal = True
                        break
                    continue
                counts.fetched += 1
                try:
                    values = _posting_values(item)
                except ValueError as exc:
                    counts.problem(f"{item.external_id}: {exc}")
                    continue
                company_id = await _company_id(session, item.company, companies)
                normalized_company = normalize_company(item.company)
                values.update(
                    source_id=source_id,
                    ingestion_run_id=run_id,
                    company_id=company_id,
                    content_hash=content_hash(
                        values["title"],
                        normalized_company,
                        values["location"],
                        values["description"],
                    ),
                    role_id=classify_title(values["title"], rules),
                )
                new_id = await session.scalar(
                    insert(JobPosting)
                    .values(**values)
                    .on_conflict_do_nothing()
                    .returning(JobPosting.id)
                )
                if new_id is None:
                    counts.duplicates += 1
                else:
                    counts.inserted += 1
                    counts.inserted_ids.append(new_id)
                pending += 1
                if pending >= BATCH_SIZE:
                    await session.commit()
                    pending = 0
            await session.commit()
    except Exception as exc:
        logger.exception("Ingestion run %s crashed", run_id)
        counts.problem(f"run aborted: {type(exc).__name__}")
        fatal = True

    async with session_factory() as session:
        # Count what was actually committed: after a crash the last batch was rolled back.
        committed = list(
            (
                await session.scalars(
                    select(JobPosting.id).where(JobPosting.ingestion_run_id == run_id)
                )
            ).all()
        )
        counts.inserted, counts.inserted_ids = len(committed), committed
        run = await session.get(IngestionRun, run_id)
        if run is None:
            raise RuntimeError("run disappeared during processing")
        run.fetched, run.inserted = counts.fetched, counts.inserted
        run.duplicates, run.errors = counts.duplicates, counts.errors
        run.error_samples = counts.error_samples
        run.finished_at = datetime.now(tz=UTC)
        if fatal and counts.fetched == 0:
            run.status = "failed"
        elif fatal or counts.errors:
            run.status = "partial"
        else:
            run.status = "succeeded"
        await session.commit()
    logger.info(
        "Ingestion run %s: fetched=%s inserted=%s duplicates=%s errors=%s",
        run_id,
        counts.fetched,
        counts.inserted,
        counts.duplicates,
        counts.errors,
    )
    return counts
