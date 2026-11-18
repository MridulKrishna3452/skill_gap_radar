"""ORM models. Importing this package registers every table on Base.metadata."""

from app.models.analytics import GapReport, SkillDemandMonthly
from app.models.curriculum import (
    Course,
    CourseUnit,
    CurriculumDocument,
    Program,
    UnitSkill,
    University,
)
from app.models.jobs import Company, IngestionRun, JobPosting, JobSource, PostingSkill
from app.models.taxonomy import LearningContent, Role, RoleSkill, Skill, SkillAlias

__all__ = [
    "Company",
    "Course",
    "CourseUnit",
    "CurriculumDocument",
    "GapReport",
    "IngestionRun",
    "JobPosting",
    "JobSource",
    "LearningContent",
    "PostingSkill",
    "Program",
    "Role",
    "RoleSkill",
    "Skill",
    "SkillAlias",
    "SkillDemandMonthly",
    "UnitSkill",
    "University",
]
