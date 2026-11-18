"""Run the extractor over stored postings and persist posting_skills."""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import JobPosting, PostingSkill
from app.services.extraction.extractor import SkillExtractor
from app.services.extraction.taxonomy import get_extractor

logger = logging.getLogger(__name__)


def posting_skill_rows(
    posting_id: int, extractor: SkillExtractor, title: str, description: str
) -> list[PostingSkill]:
    return [
        PostingSkill(
            posting_id=posting_id,
            skill_id=s.skill_id,
            requirement=s.requirement,
            confidence=round(s.confidence, 4),
            implied=s.implied,
            evidence=[e.as_dict() for e in s.evidence[:10]],
        )
        for s in extractor.extract([("title", title), ("description", description)])
    ]


async def extract_postings(session: AsyncSession, postings: list[JobPosting]) -> int:
    extractor = await get_extractor(session)
    now = datetime.now(tz=UTC)
    ids = [p.id for p in postings]
    await session.execute(delete(PostingSkill).where(PostingSkill.posting_id.in_(ids)))
    for posting in postings:
        try:
            session.add_all(
                posting_skill_rows(posting.id, extractor, posting.title, posting.description)
            )
            posting.extraction_status = "done"
        except Exception:
            logger.exception("Extraction failed for posting %s", posting.id)
            posting.extraction_status = "failed"
        posting.extractor_version = extractor.version
        posting.extracted_at = now
    await session.flush()
    return len(postings)


async def extract_pending(
    session_factory: async_sessionmaker[AsyncSession], batch_size: int = 200
) -> int:
    """Extract every posting with extraction_status='pending'. Returns how many were done.

    Rows are claimed with FOR UPDATE SKIP LOCKED so parallel workers never double-process.
    """
    total = 0
    while True:
        async with session_factory() as session:
            batch = list(
                (
                    await session.scalars(
                        select(JobPosting)
                        .where(JobPosting.extraction_status == "pending")
                        .order_by(JobPosting.id)
                        .limit(batch_size)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            if not batch:
                return total
            total += await extract_postings(session, batch)
            await session.commit()


async def mark_stale(session: AsyncSession) -> int:
    """Queue re-extraction for postings processed by another taxonomy/extractor version."""
    extractor = await get_extractor(session)
    result = await session.execute(
        update(JobPosting)
        .where(
            (JobPosting.extractor_version.is_(None))
            | (JobPosting.extractor_version != extractor.version)
        )
        .values(extraction_status="pending")
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
