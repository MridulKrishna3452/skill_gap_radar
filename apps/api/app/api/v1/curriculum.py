"""Universities, programs and curriculum uploads (v1: GET /curriculum and the PDF parser)."""

from typing import Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import Pagination, get_app_settings, get_db, get_task_queue, pagination
from app.api.v1.schemas import (
    CurriculumOut,
    DocumentOut,
    Page,
    ProgramIn,
    ProgramOut,
    UniversityIn,
    UniversityOut,
    UploadResponse,
)
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.models import (
    Course,
    CourseUnit,
    CurriculumDocument,
    Program,
    Skill,
    UnitSkill,
    University,
)
from app.services.curriculum.service import UploadTooLargeError, create_document
from app.workers.queue import TaskQueue

router = APIRouter(tags=["curriculum"])


@router.post(
    "/universities",
    response_model=UniversityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a university",
)
async def create_university(
    body: UniversityIn, session: AsyncSession = Depends(get_db)
) -> University:
    uni = University(name=body.name.strip(), country=body.country.lower() if body.country else None)
    session.add(uni)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"University '{body.name}' already exists") from exc
    return uni


@router.get("/universities", response_model=Page[UniversityOut], summary="List universities")
async def list_universities(
    page: Pagination = Depends(pagination), session: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    total = await session.scalar(select(func.count()).select_from(University)) or 0
    rows = (
        await session.scalars(
            select(University).order_by(University.name).limit(page.limit).offset(page.offset)
        )
    ).all()
    return {"items": rows, "total": total, "limit": page.limit, "offset": page.offset}


@router.post(
    "/programs",
    response_model=ProgramOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a degree program",
)
async def create_program(body: ProgramIn, session: AsyncSession = Depends(get_db)) -> Program:
    if await session.get(University, body.university_id) is None:
        raise NotFoundError(f"University {body.university_id} not found")
    program = Program(university_id=body.university_id, name=body.name.strip(), degree=body.degree)
    session.add(program)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(f"Program '{body.name}' already exists at this university") from exc
    return program


@router.get("/programs", response_model=Page[ProgramOut], summary="List programs")
async def list_programs(
    page: Pagination = Depends(pagination),
    university_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conds = [Program.university_id == university_id] if university_id else []
    total = await session.scalar(select(func.count()).select_from(Program).where(*conds)) or 0
    rows = (
        await session.scalars(
            select(Program)
            .where(*conds)
            .order_by(Program.name)
            .limit(page.limit)
            .offset(page.offset)
        )
    ).all()
    return {"items": rows, "total": total, "limit": page.limit, "offset": page.offset}


@router.get("/programs/{program_id}", response_model=ProgramOut, summary="Get a program")
async def get_program(program_id: int, session: AsyncSession = Depends(get_db)) -> Program:
    program = await session.get(Program, program_id)
    if program is None:
        raise NotFoundError(f"Program {program_id} not found")
    return program


@router.post(
    "/programs/{program_id}/curriculum",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a syllabus PDF for a program",
    description="Stores the PDF and queues parsing in a worker. Re-uploading the same file "
    "returns the existing document (HTTP 200) and creates no new rows. A different file "
    "replaces the program's curriculum once it parses successfully.",
    responses={
        200: {"model": UploadResponse, "description": "Same file already uploaded"},
        413: {"description": "File too large"},
        422: {"description": "Not a PDF"},
    },
)
async def upload_curriculum(
    program_id: int,
    response: Response,
    file: UploadFile = File(..., description="Syllabus PDF"),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    queue: TaskQueue = Depends(get_task_queue),
) -> dict[str, Any]:
    data = await file.read(settings.CURRICULUM_MAX_BYTES + 1)
    if len(data) > settings.CURRICULUM_MAX_BYTES:
        raise UploadTooLargeError(
            f"File exceeds the {settings.CURRICULUM_MAX_BYTES // (1024 * 1024)} MB limit"
        )
    doc, created = await create_document(session, program_id, file.filename or "", data, settings)
    queued = created or doc.status == "superseded"
    if not created:
        response.status_code = status.HTTP_200_OK
        if queued:  # an older version re-uploaded: make it current again
            doc.status = "queued"
    await session.commit()
    if queued:
        await queue.send("curriculum.parse_document", doc.id)
    return {"document": doc, "created": created, "queued": queued}


@router.get(
    "/programs/{program_id}/curriculum/documents",
    response_model=list[DocumentOut],
    summary="Uploaded syllabus documents for a program",
)
async def list_documents(
    program_id: int, session: AsyncSession = Depends(get_db)
) -> list[CurriculumDocument]:
    if await session.get(Program, program_id) is None:
        raise NotFoundError(f"Program {program_id} not found")
    return list(
        (
            await session.scalars(
                select(CurriculumDocument)
                .where(CurriculumDocument.program_id == program_id)
                .order_by(CurriculumDocument.uploaded_at.desc())
            )
        ).all()
    )


@router.get(
    "/curriculum/documents/{document_id}",
    response_model=DocumentOut,
    summary="Parse status of an uploaded syllabus",
)
async def get_document(
    document_id: int, session: AsyncSession = Depends(get_db)
) -> CurriculumDocument:
    doc = await session.get(CurriculumDocument, document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found")
    return doc


@router.get(
    "/programs/{program_id}/curriculum",
    response_model=CurriculumOut,
    summary="Parsed curriculum: courses, units and the skills each unit covers",
)
async def get_curriculum(
    program_id: int, session: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    program = await session.get(Program, program_id)
    if program is None:
        raise NotFoundError(f"Program {program_id} not found")
    courses = (
        await session.scalars(
            select(Course)
            .where(Course.program_id == program_id)
            .order_by(Course.position)
            .options(selectinload(Course.units).selectinload(CourseUnit.skills))
        )
    ).all()
    document = None
    if courses:
        document = await session.get(CurriculumDocument, courses[0].document_id)
    skill_ids = {us.skill_id for c in courses for u in c.units for us in u.skills}
    skills = {
        s.id: s for s in (await session.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()
    }

    def unit_skills(items: list[UnitSkill]) -> list[dict[str, Any]]:
        return [
            {
                "skill": {
                    "id": us.skill_id,
                    "slug": skills[us.skill_id].slug,
                    "name": skills[us.skill_id].name,
                },
                "coverage": us.coverage,
                "evidence": us.evidence,
            }
            for us in sorted(items, key=lambda x: (-x.coverage, x.skill_id))
        ]

    return {
        "program": program,
        "document": document,
        "courses": [
            {
                "id": c.id,
                "position": c.position,
                "code": c.code,
                "title": c.title,
                "units": [
                    {
                        "id": u.id,
                        "position": u.position,
                        "title": u.title,
                        "content": u.content,
                        "learning_outcomes": u.learning_outcomes,
                        "skills": unit_skills(u.skills),
                    }
                    for u in c.units
                ],
            }
            for c in courses
        ],
    }
