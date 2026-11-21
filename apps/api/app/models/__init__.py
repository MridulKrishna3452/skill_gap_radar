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
from app.models.users import (
    AuditLog,
    FacultyProgramAssignment,
    RefreshToken,
    StudentProfile,
    User,
    UserSkill,
)

__all__ = [
    "AuditLog",
    "Company",
    "Course",
    "CourseUnit",
    "CurriculumDocument",
    "FacultyProgramAssignment",
    "GapReport",
    "IngestionRun",
    "JobPosting",
    "JobSource",
    "LearningContent",
    "PostingSkill",
    "Program",
    "RefreshToken",
    "Role",
    "RoleSkill",
    "Skill",
    "SkillAlias",
    "SkillDemandMonthly",
    "StudentProfile",
    "UnitSkill",
    "University",
    "User",
    "UserSkill",
]
