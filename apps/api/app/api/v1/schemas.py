"""Request and response models for the v1 API (shown in OpenAPI)."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Page[T](BaseModel):
    items: list[T]
    total: int = Field(description="Total matching items, ignoring limit/offset")
    limit: int
    offset: int


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- taxonomy ---------------------------------------------------------------------------


class SkillRef(ORM):
    id: int
    slug: str
    name: str


class SkillOut(SkillRef):
    category: str
    parent: SkillRef | None = None
    esco_uri: str | None = None


class AliasOut(ORM):
    alias: str
    requires_context: bool
    case_sensitive_form: str | None


class SkillDetail(SkillOut):
    description: str | None
    context_terms: list[str]
    aliases: list[AliasOut]


class RoleOut(ORM):
    id: int
    slug: str
    name: str
    title_patterns: list[str]
    core_skills: list[SkillRef] = Field(
        description="Editorial core skills (v1 role_requirements); empty for newer roles"
    )


# ---- jobs -------------------------------------------------------------------------------


class PostingSkillOut(BaseModel):
    skill: SkillRef
    requirement: Literal["required", "nice_to_have", "unspecified"]
    confidence: float
    implied: bool


class EvidenceOut(BaseModel):
    field: str
    start: int
    end: int
    text: str
    rule: str
    requirement: str | None = None


class PostingSkillDetail(PostingSkillOut):
    evidence: list[EvidenceOut]


class SourceRef(ORM):
    key: str
    name: str
    is_synthetic: bool


class JobSummary(BaseModel):
    id: int
    title: str
    company: str | None
    location: str | None
    country: str | None
    posted_at: datetime
    source: SourceRef
    role: str | None = Field(description="Role slug assigned from the title, if any")
    url: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_is_estimated: bool | None
    employment_type: str | None
    extraction_status: str
    skills: list[PostingSkillOut]


class JobDetail(JobSummary):
    description: str
    location_raw: str | None
    category: str | None
    experience_text: str | None
    extractor_version: str | None
    skills: list[PostingSkillDetail]  # type: ignore[assignment]


class FacetBucket(BaseModel):
    key: str | None = Field(description="Bucket value; null = not known for those postings")
    count: int


class JobFacets(BaseModel):
    total: int
    by_role: list[FacetBucket]
    by_source: list[FacetBucket]
    by_category: list[FacetBucket]
    by_location: list[FacetBucket]
    by_month: list[FacetBucket] = Field(description="YYYY-MM of posted_at (UTC)")


# ---- demand and trends ------------------------------------------------------------------


class WindowOut(BaseModel):
    start: date | None
    end_exclusive: date | None
    months: int


class SkillDemandOut(BaseModel):
    skill: SkillRef
    postings_with_skill: int
    required_postings: int
    share: float = Field(description="Share of postings in the window that mention the skill")
    required_share: float


class DemandResponse(BaseModel):
    window: WindowOut
    role: str | None
    total_postings: int
    low_sample: bool = Field(description="True when total_postings < ANALYTICS_MIN_POSTINGS")
    items: list[SkillDemandOut]
    total: int
    limit: int
    offset: int


class SeriesPointOut(BaseModel):
    month: date
    total_postings: int
    postings_with_skill: int
    share: float
    change_pp: float | None = Field(description="share minus previous month's share")
    change_rel: float | None = Field(description="change_pp / previous share; null if it was 0")


class SkillTrendResponse(BaseModel):
    skill: SkillRef
    role: str | None
    series: list[SeriesPointOut]


class MoverOut(BaseModel):
    skill: SkillRef
    share_prev: float
    share_curr: float
    change_pp: float
    change_rel: float | None


class MoversResponse(BaseModel):
    role: str | None
    current_month: date | None
    previous_month: date | None
    current_postings: int
    previous_postings: int
    low_sample: bool
    thresholds: dict[str, float]
    growing: list[MoverOut]
    declining: list[MoverOut]
    emerging: list[MoverOut]


# ---- curriculum -------------------------------------------------------------------------


class UniversityIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=2, examples=["in"])


class UniversityOut(ORM):
    id: int
    name: str
    country: str | None


class ProgramIn(BaseModel):
    university_id: int
    name: str = Field(min_length=2, max_length=255, examples=["B.Tech Computer Science"])
    degree: str | None = Field(default=None, max_length=60, examples=["B.Tech"])


class ProgramOut(ORM):
    id: int
    university_id: int
    name: str
    degree: str | None


class DocumentOut(ORM):
    id: int
    program_id: int
    filename: str
    sha256: str
    size_bytes: int
    status: Literal["queued", "parsing", "parsed", "failed", "superseded"]
    parser_strategy: str | None
    page_count: int | None
    units_parsed: int | None
    error: str | None
    uploaded_at: datetime
    parsed_at: datetime | None


class UploadResponse(BaseModel):
    document: DocumentOut
    created: bool = Field(description="False when the same file was already uploaded")
    queued: bool = Field(description="True when a parse job was queued")


class UnitSkillOut(BaseModel):
    skill: SkillRef
    coverage: float
    evidence: list[EvidenceOut]


class UnitOut(BaseModel):
    id: int
    position: int
    title: str
    content: str
    learning_outcomes: str | None
    skills: list[UnitSkillOut]


class CourseOut(BaseModel):
    id: int
    position: int
    code: str | None
    title: str
    units: list[UnitOut]


class CurriculumOut(BaseModel):
    program: ProgramOut
    document: DocumentOut | None
    courses: list[CourseOut]


# ---- gap and recommendations ------------------------------------------------------------


class CoveringUnit(BaseModel):
    unit_id: int
    unit: str
    course: str
    coverage: float


class GapSkillOut(BaseModel):
    skill: dict[str, Any]
    demand_share: float
    required_share: float
    postings_with_skill: int
    coverage: float
    gap: float = Field(description="demand_share * (1 - coverage)")
    covered_in: list[CoveringUnit]


class GapSummaryOut(BaseModel):
    total_postings: int
    skills_in_demand: int
    weighted_coverage: float | None = Field(
        description="sum(demand*coverage)/sum(demand) over all demanded skills"
    )
    top_n: int
    top_n_coverage: float | None = Field(
        description="Mean coverage of the top-N skills by demand (not by gap; v1 bug fixed)"
    )
    top_n_covered_count: int
    gap_index: float | None = Field(description="1 - weighted_coverage")


class GapReportOut(BaseModel):
    id: int
    computed_at: datetime
    program: dict[str, Any]
    role: dict[str, Any] | None
    window: WindowOut
    has_curriculum: bool
    low_sample: bool
    min_postings: int
    summary: GapSummaryOut
    skills: list[GapSkillOut]


class RoleGapOut(BaseModel):
    role: SkillRef = Field(description="id / slug / name of the role")
    postings: int
    low_sample: bool
    weighted_coverage: float | None
    top_n_coverage: float | None
    gap_index: float | None


class RoleGapResponse(BaseModel):
    program: dict[str, Any]
    window: WindowOut
    has_curriculum: bool
    min_postings: int
    roles: list[RoleGapOut]


class LearningOut(BaseModel):
    difficulty: str
    estimated_weeks: float
    steps: list[str]
    content_source: str = Field(description="Origin of the text, e.g. editorial:v1")


class RecommendationItem(BaseModel):
    skill: SkillRef
    reason: list[Literal["role_core_skill", "market_demand"]]
    priority: Literal["high", "medium", "low", "insufficient_data"]
    demand_share: float
    coverage: float | None
    coverage_status: Literal["covered", "partial", "missing"] | None
    learning: LearningOut | None


class RecommendationsResponse(BaseModel):
    role: dict[str, Any]
    program: dict[str, Any] | None
    window: WindowOut
    role_postings: int
    low_sample: bool
    thresholds: dict[str, float]
    items: list[RecommendationItem]


# ---- ingestion --------------------------------------------------------------------------


class SourceOut(ORM):
    id: int
    key: str
    name: str
    kind: str
    is_synthetic: bool
    licence: str | None
    homepage_url: str | None


class AdzunaParams(BaseModel):
    country: str = Field(default="in", min_length=2, max_length=2)
    what: str | None = Field(default=None, max_length=200, examples=["software developer"])
    where: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=100, examples=["it-jobs"])
    pages: int = Field(default=1, ge=1, le=200)
    max_days_old: int | None = Field(default=None, ge=1, le=365)


class IngestionRunIn(BaseModel):
    source: Literal["adzuna"] = "adzuna"
    params: AdzunaParams = AdzunaParams()


class IngestionRunOut(ORM):
    id: int
    source: SourceRef
    status: str
    params: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    fetched: int
    inserted: int
    duplicates: int
    errors: int
    error_samples: list[str]
    created_at: datetime
