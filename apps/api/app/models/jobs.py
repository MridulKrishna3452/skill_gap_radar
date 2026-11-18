"""Job market data: sources, ingestion runs, companies, postings and extracted posting skills."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobSource(Base):
    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))  # "api" | "file"
    # Synthetic sources exist only for testing/demo and are excluded from analytics.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, server_default="false")
    licence: Mapped[str | None] = mapped_column(Text)
    homepage_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("kind IN ('api', 'file')", name="kind"),)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("job_sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), server_default="queued")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched: Mapped[int] = mapped_column(Integer, server_default="0")
    inserted: Mapped[int] = mapped_column(Integer, server_default="0")
    duplicates: Mapped[int] = mapped_column(Integer, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, server_default="0")
    # Short, non-sensitive error summaries (never API keys or full responses).
    error_samples: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[JobSource] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed')", name="status"
        ),
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True)


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("job_sources.id"))
    external_id: Mapped[str] = mapped_column(String(255))
    # SHA-256 over normalised title/company/location/description: catches the same posting
    # arriving twice, within a source or across sources.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    ingestion_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(500))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    location_raw: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(255), index=True)
    country: Mapped[str | None] = mapped_column(String(2))
    description: Mapped[str] = mapped_column(Text)
    salary_min: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_is_estimated: Mapped[bool | None] = mapped_column(Boolean)
    employment_type: Mapped[str | None] = mapped_column(String(60))
    category: Mapped[str | None] = mapped_column(String(120))
    experience_text: Mapped[str | None] = mapped_column(String(120))
    url: Mapped[str | None] = mapped_column(String(2000))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), index=True
    )
    extraction_status: Mapped[str] = mapped_column(String(20), server_default="pending")
    extractor_version: Mapped[str | None] = mapped_column(String(40))
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[JobSource] = relationship()
    company: Mapped[Company | None] = relationship()
    skills: Mapped[list["PostingSkill"]] = relationship(cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint(
            "extraction_status IN ('pending', 'done', 'failed')", name="extraction_status"
        ),
    )


class PostingSkill(Base):
    __tablename__ = "posting_skills"

    posting_id: Mapped[int] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), primary_key=True)
    requirement: Mapped[str] = mapped_column(String(20))  # required | nice_to_have | unspecified
    confidence: Mapped[float] = mapped_column(Float)
    # True when only a narrower skill was mentioned (PostgreSQL -> SQL).
    implied: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # [{"start", "end", "text", "field", "rule"}] character offsets into the field.
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")

    __table_args__ = (
        CheckConstraint(
            "requirement IN ('required', 'nice_to_have', 'unspecified')", name="requirement"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        Index("ix_posting_skills_skill_id", "skill_id"),
    )
