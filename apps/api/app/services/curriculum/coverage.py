"""Graded coverage: how well a unit (and a program) covers a skill, on a 0-1 scale.

Unit grade = the highest grade among the places the skill is mentioned:

    unit title                     1.0   the unit is about this skill
    course title                   0.8   the whole course is about it
    unit content, 3+ mentions      0.7
    unit content, 2 mentions       0.6
    unit content, 1 mention        0.5   mentioned among other topics
    learning outcomes only         0.4

Program coverage of a skill = the highest unit grade in the program (0 if never mentioned).
Broader skills inherit the grade of the narrower skill that implies them (PostgreSQL -> SQL).
These grades are a documented heuristic, not a measured quantity.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.services.extraction.extractor import ExtractedSkill, SkillExtractor

FIELD_GRADES = {"unit_title": 1.0, "course_title": 0.8, "outcomes": 0.4}
CONTENT_GRADES = {1: 0.5, 2: 0.6}
CONTENT_GRADE_MANY = 0.7


@dataclass
class UnitCoverage:
    skill_id: int
    coverage: float
    evidence: list[dict[str, Any]]


def grade(skill: ExtractedSkill) -> float:
    best = 0.0
    content_mentions = Counter(e.field for e in skill.evidence)["content"]
    for ev in skill.evidence:
        if ev.field == "content":
            g = CONTENT_GRADES.get(content_mentions, CONTENT_GRADE_MANY)
        else:
            g = FIELD_GRADES.get(ev.field, 0.0)
        best = max(best, g)
    return best


def unit_coverage(
    extractor: SkillExtractor,
    *,
    course_title: str,
    unit_title: str,
    content: str,
    outcomes: str | None,
) -> list[UnitCoverage]:
    fields = [
        ("course_title", course_title),
        ("unit_title", unit_title),
        ("content", content),
        ("outcomes", outcomes or ""),
    ]
    out = []
    for skill in extractor.extract(fields, with_requirement=False):
        g = grade(skill)
        if g > 0:
            evidence = [
                {"field": e.field, "start": e.start, "end": e.end, "text": e.text, "rule": e.rule}
                for e in skill.evidence[:10]
            ]
            out.append(UnitCoverage(skill.skill_id, g, evidence))
    return out


def program_coverage(unit_grades: Iterable[tuple[int, float]]) -> dict[int, float]:
    """(skill_id, unit grade) pairs -> skill_id: program coverage (max over units)."""
    result: dict[int, float] = {}
    for skill_id, g in unit_grades:
        result[skill_id] = max(result.get(skill_id, 0.0), g)
    return result
