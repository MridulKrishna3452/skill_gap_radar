"""Coverage grading (services/curriculum/coverage.py) with hand-computed expectations."""

import pytest

from app.services.curriculum.coverage import program_coverage, unit_coverage
from app.services.extraction.extractor import SkillExtractor
from app.services.extraction.taxonomy import specs_from_seed


@pytest.fixture(scope="module")
def extractor() -> SkillExtractor:
    return SkillExtractor(specs_from_seed())


@pytest.fixture(scope="module")
def ids() -> dict[str, int]:
    return {s.slug: s.id for s in specs_from_seed()}


def grades(
    ex: SkillExtractor,
    course_title: str = "",
    unit_title: str = "",
    content: str = "",
    outcomes: str | None = None,
) -> dict[int, float]:
    return {
        c.skill_id: c.coverage
        for c in unit_coverage(
            ex, course_title=course_title, unit_title=unit_title, content=content, outcomes=outcomes
        )
    }


def test_unit_title_is_full_coverage(extractor: SkillExtractor, ids: dict[str, int]) -> None:
    assert grades(extractor, unit_title="Unit 3: Docker")[ids["docker"]] == 1.0


def test_course_title(extractor: SkillExtractor, ids: dict[str, int]) -> None:
    assert grades(extractor, course_title="Machine Learning")[ids["machine-learning"]] == 0.8


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("Intro to Kafka.", 0.5),
        ("Kafka topics. Kafka partitions.", 0.6),
        ("Kafka topics. Kafka partitions. Kafka streams.", 0.7),
    ],
)
def test_content_mentions(
    extractor: SkillExtractor, ids: dict[str, int], content: str, expected: float
) -> None:
    assert grades(extractor, content=content)[ids["kafka"]] == expected


def test_outcomes_only(extractor: SkillExtractor, ids: dict[str, int]) -> None:
    assert grades(extractor, outcomes="Write SQL queries")[ids["sql"]] == 0.4


def test_highest_grade_wins(extractor: SkillExtractor, ids: dict[str, int]) -> None:
    g = grades(extractor, unit_title="Unit 1: SQL", content="SQL joins", outcomes="SQL")
    assert g[ids["sql"]] == 1.0


def test_implied_parent_gets_child_grade(extractor: SkillExtractor, ids: dict[str, int]) -> None:
    g = grades(extractor, content="PostgreSQL indexing")
    assert g[ids["postgresql"]] == 0.5
    assert g[ids["sql"]] == 0.5


def test_unmentioned_skill_has_no_row(extractor: SkillExtractor, ids: dict[str, int]) -> None:
    assert ids["kafka"] not in grades(extractor, content="Operating systems and compilers")


def test_program_coverage_is_max_over_units() -> None:
    assert program_coverage([(1, 0.5), (1, 0.8), (2, 0.4)]) == {1: 0.8, 2: 0.4}
