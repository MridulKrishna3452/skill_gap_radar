"""Curriculum upload, parsing and storage.

- Upload stores the PDF (validated) as a curriculum_documents row. Uploading the same bytes
  again for the same program returns the existing document: no duplicate rows.
- Parsing runs in a Celery worker. A successful parse replaces the program's courses, units
  and unit skills in one transaction and marks the previous document superseded, so a program
  always has exactly one current curriculum.
"""

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.models import Course, CourseUnit, CurriculumDocument, Program, UnitSkill
from app.services.curriculum.coverage import unit_coverage
from app.services.curriculum.parser import CurriculumParseError, parse_pdf
from app.services.extraction.taxonomy import get_extractor

logger = logging.getLogger(__name__)
PDF_MAGIC = b"%PDF-"


class InvalidUploadError(AppError):
    status_code = 422
    code = "invalid_upload"


class UploadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


def validate_pdf(data: bytes, settings: Settings) -> None:
    if len(data) > settings.CURRICULUM_MAX_BYTES:
        raise UploadTooLargeError(
            f"File exceeds the {settings.CURRICULUM_MAX_BYTES // (1024 * 1024)} MB limit"
        )
    if not data.startswith(PDF_MAGIC):
        raise InvalidUploadError("File is not a PDF (missing %PDF- header)")


async def create_document(
    session: AsyncSession, program_id: int, filename: str, data: bytes, settings: Settings
) -> tuple[CurriculumDocument, bool]:
    """Store an upload. Returns (document, created)."""
    if await session.get(Program, program_id) is None:
        raise NotFoundError(f"Program {program_id} not found")
    validate_pdf(data, settings)
    digest = hashlib.sha256(data).hexdigest()
    existing = await session.scalar(
        select(CurriculumDocument).where(
            CurriculumDocument.program_id == program_id, CurriculumDocument.sha256 == digest
        )
    )
    if existing is not None:
        return existing, False
    doc = CurriculumDocument(
        program_id=program_id,
        filename=(filename or "syllabus.pdf")[:255],
        sha256=digest,
        size_bytes=len(data),
        content=data,
        status="queued",
    )
    session.add(doc)
    await session.flush()
    return doc, True


async def _mark_failed(
    session_factory: async_sessionmaker[AsyncSession], document_id: int, message: str
) -> CurriculumDocument:
    async with session_factory() as session:
        doc = await session.get(CurriculumDocument, document_id)
        if doc is None:
            raise LookupError(f"curriculum document {document_id} not found")
        doc.status, doc.error, doc.parsed_at = "failed", message, datetime.now(tz=UTC)
        await session.commit()
        return doc


async def parse_document(
    session_factory: async_sessionmaker[AsyncSession], document_id: int, settings: Settings
) -> CurriculumDocument:
    async with session_factory() as session:
        doc = await session.get(CurriculumDocument, document_id)
        if doc is None:
            raise LookupError(f"curriculum document {document_id} not found")
        doc.status = "parsing"
        await session.commit()
        data = await session.scalar(
            select(CurriculumDocument.content).where(CurriculumDocument.id == document_id)
        )
        filename, program_id = doc.filename, doc.program_id

    try:
        result = parse_pdf(data or b"", filename, settings.CURRICULUM_MAX_PAGES)
    except CurriculumParseError as exc:
        logger.info("Curriculum document %s failed to parse: %s", document_id, exc)
        return await _mark_failed(session_factory, document_id, str(exc))

    async with session_factory() as session:
        extractor = await get_extractor(session)
        await session.execute(delete(Course).where(Course.program_id == program_id))
        for c_pos, parsed_course in enumerate(result.courses, start=1):
            course = Course(
                program_id=program_id,
                document_id=document_id,
                position=c_pos,
                code=parsed_course.code,
                title=parsed_course.title,
            )
            for u_pos, parsed_unit in enumerate(parsed_course.units, start=1):
                unit = CourseUnit(
                    position=u_pos,
                    title=parsed_unit.title,
                    content=parsed_unit.content,
                    learning_outcomes=parsed_unit.learning_outcomes,
                )
                unit.skills = [
                    UnitSkill(skill_id=cov.skill_id, coverage=cov.coverage, evidence=cov.evidence)
                    for cov in unit_coverage(
                        extractor,
                        course_title=parsed_course.title,
                        unit_title=parsed_unit.title,
                        content=parsed_unit.content,
                        outcomes=parsed_unit.learning_outcomes,
                    )
                ]
                course.units.append(unit)
            session.add(course)
        await session.execute(
            update(CurriculumDocument)
            .where(
                CurriculumDocument.program_id == program_id,
                CurriculumDocument.id != document_id,
                CurriculumDocument.status == "parsed",
            )
            .values(status="superseded")
        )
        doc = await session.get(CurriculumDocument, document_id)
        if doc is None:
            raise RuntimeError("doc disappeared during processing")
        doc.status = "parsed"
        doc.parser_strategy = result.strategy
        doc.page_count = result.page_count
        doc.units_parsed = result.unit_count
        doc.error = None
        doc.parsed_at = datetime.now(tz=UTC)
        await session.commit()
        await session.refresh(doc)
        return doc


async def recompute_unit_skills(session: AsyncSession) -> int:
    """Re-grade every stored unit with the current taxonomy (after taxonomy changes)."""
    extractor = await get_extractor(session)
    rows = (
        await session.execute(
            select(CourseUnit, Course.title).join(Course, Course.id == CourseUnit.course_id)
        )
    ).all()
    await session.execute(delete(UnitSkill))
    for unit, course_title in rows:
        for cov in unit_coverage(
            extractor,
            course_title=course_title,
            unit_title=unit.title,
            content=unit.content,
            outcomes=unit.learning_outcomes,
        ):
            session.add(
                UnitSkill(
                    unit_id=unit.id,
                    skill_id=cov.skill_id,
                    coverage=cov.coverage,
                    evidence=cov.evidence,
                )
            )
    await session.flush()
    return len(rows)
