"""Curriculum: universities, programs, uploaded syllabus documents, courses, units, unit skills."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.db.base import Base


class University(Base):
    __tablename__ = "universities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    country: Mapped[str | None] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (UniqueConstraint("university_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    university_id: Mapped[int] = mapped_column(
        ForeignKey("universities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    degree: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    university: Mapped[University] = relationship()


class CurriculumDocument(Base):
    """An uploaded syllabus PDF. The latest parsed document defines the program's curriculum."""

    __tablename__ = "curriculum_documents"
    __table_args__ = (
        UniqueConstraint("program_id", "sha256"),
        CheckConstraint(
            "status IN ('queued', 'parsing', 'parsed', 'failed', 'superseded')", name="status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # Stored in the database so the API and worker containers need no shared volume.
    content: Mapped[bytes] = deferred(mapped_column(LargeBinary))
    status: Mapped[str] = mapped_column(String(20), server_default="queued")
    parser_strategy: Mapped[str | None] = mapped_column(String(30))
    page_count: Mapped[int | None] = mapped_column(Integer)
    units_parsed: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("program_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    code: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(500))

    units: Mapped[list["CourseUnit"]] = relationship(
        cascade="all, delete-orphan", order_by="CourseUnit.position"
    )


class CourseUnit(Base):
    __tablename__ = "course_units"
    __table_args__ = (UniqueConstraint("course_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    learning_outcomes: Mapped[str | None] = mapped_column(Text)

    skills: Mapped[list["UnitSkill"]] = relationship(cascade="all, delete-orphan")


class UnitSkill(Base):
    __tablename__ = "unit_skills"
    __table_args__ = (CheckConstraint("coverage > 0 AND coverage <= 1", name="coverage"),)

    unit_id: Mapped[int] = mapped_column(
        ForeignKey("course_units.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), primary_key=True, index=True)
    # Graded 0-1: how central the skill is to the unit (see services/curriculum/coverage.py).
    coverage: Mapped[float] = mapped_column(Float)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
