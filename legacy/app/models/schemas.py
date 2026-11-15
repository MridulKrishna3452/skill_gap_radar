from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field

class Job(BaseModel):
    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Hiring company")
    location: str = Field(..., description="Job location")
    experience: str = Field(..., description="Required experience level")
    description: str = Field(..., description="Full job description")
    skills_raw: str = Field(..., description="Comma-separated raw skills listed in job posting")
    source: str = Field(..., description="Source of the job posting (e.g. Internshala, Naukri)")
    date_posted: str = Field(..., description="Date when job was posted")
    url: str = Field(..., description="Job posting URL")
    salary: Optional[str] = Field("Not Disclosed", description="Offered salary range")
    employment_type: Optional[str] = Field("Full-time", description="Full-time, Part-time, Contract, etc.")
    category: Optional[str] = Field("Software Engineering", description="Job category (e.g., Software, Data, AI, Cloud)")

class Skill(BaseModel):
    name: str = Field(..., description="Standardized name of the skill")
    frequency: int = Field(1, description="Count of occurrences")
    confidence: float = Field(1.0, description="Extraction confidence score (0.0 to 1.0)")
    source: str = Field(..., description="Where the skill was extracted from")

class Curriculum(BaseModel):
    university: str = Field(..., description="University name")
    course: str = Field(..., description="Course name (e.g., B.Tech Computer Science)")
    subject: str = Field(..., description="Subject or Module title")
    unit: Optional[str] = Field(None, description="Syllabus unit name/number")
    topic: str = Field(..., description="Topic description")
    learning_outcomes: Optional[str] = Field(None, description="Expected learning outcomes")

class Trend(BaseModel):
    skill_name: str
    period: str  # e.g., "2026-W25" or "2026-M06"
    frequency: int
    growth_rate: float

class Recommendation(BaseModel):
    career_goal: str
    missing_skill: str
    priority: str  # High, Medium, Low
    difficulty: str  # Beginner, Intermediate, Advanced
    estimated_learning_time: str  # e.g., "4 weeks"
    learning_roadmap: List[str]

class University(BaseModel):
    name: str
    location: str
    syllabus_parsed_date: str = Field(default_factory=lambda: datetime.now().isoformat())

class UserProfile(BaseModel):
    username: str
    target_role: str
    current_skills: List[str]
