"""Skills taxonomy: skills, their aliases, and job roles.

A skill may have a broader parent (PostgreSQL -> SQL): a posting that mentions the child also
counts as evidence for the parent, marked as implied.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"))
    # ESCO concept URI when the skill was linked to ESCO by exact label match. Never guessed.
    esco_uri: Mapped[str | None] = mapped_column(String(255), unique=True)
    # False for skills imported for reference (e.g. full ESCO) that the extractor ignores.
    extractable: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # Words that, near an ambiguous alias, indicate this skill is meant (see extraction).
    context_terms: Mapped[list[str]] = mapped_column(ARRAY(String(60)), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    aliases: Mapped[list["SkillAlias"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(120))
    # Lower-cased, whitespace-collapsed form; one alias maps to exactly one skill.
    alias_normalized: Mapped[str] = mapped_column(String(120), unique=True)
    # Ambiguous aliases ("go", "react", "lambda") match only with supporting context.
    requires_context: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # Case-sensitive form that, if seen exactly, counts as supporting evidence ("Go", "R").
    case_sensitive_form: Mapped[str | None] = mapped_column(String(120))
    # Next words that rule the match out ("go to", "react quickly", "excel in").
    negative_following: Mapped[list[str]] = mapped_column(ARRAY(String(40)), server_default="{}")
    # Single-letter aliases ("R", "C"): need the exact case form AND supporting context.
    strict: Mapped[bool] = mapped_column(Boolean, server_default="false")

    skill: Mapped[Skill] = relationship(back_populates="aliases")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    # Lower-case phrases; a posting whose title contains one is assigned this role.
    title_patterns: Mapped[list[str]] = mapped_column(ARRAY(String(80)), server_default="{}")
    # Higher wins when a title matches several roles.
    match_priority: Mapped[int] = mapped_column(Integer, server_default="0")

    core_skills: Mapped[list["RoleSkill"]] = relationship(cascade="all, delete-orphan")


class RoleSkill(Base):
    """Editorial core skills per role, carried over from v1's role_requirements."""

    __tablename__ = "role_skills"
    __table_args__ = (UniqueConstraint("role_id", "skill_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, server_default="0")


class LearningContent(Base):
    """Curated learning text per skill (v1 roadmap content), labelled as editorial."""

    __tablename__ = "learning_content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), unique=True)
    difficulty: Mapped[str] = mapped_column(String(20))
    estimated_weeks: Mapped[float] = mapped_column(Float)
    steps: Mapped[list[str]] = mapped_column(ARRAY(Text))
    # Where the text came from, e.g. "editorial:v1". Shown to users as-is.
    content_source: Mapped[str] = mapped_column(String(60))
