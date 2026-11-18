"""Skill extraction v2: alias matching, disambiguation, requirement, evidence, implied skills."""

import pytest

from app.services.extraction.extractor import SkillExtractor
from app.services.extraction.taxonomy import specs_from_seed


@pytest.fixture(scope="module")
def extractor() -> SkillExtractor:
    return SkillExtractor(specs_from_seed())


def slugs(ex: SkillExtractor, title: str, desc: str, *, implied: bool = False) -> set[str]:
    return {
        s.slug
        for s in ex.extract([("title", title), ("description", desc)])
        if implied or not s.implied
    }


def test_v1_extraction_case_still_passes(extractor: SkillExtractor) -> None:
    # legacy/tests/test_modules.py::test_nlp_extraction
    text = (
        "We are seeking a senior DevOps specialist who knows Docker, Kubernetes, AWS, "
        "and can write Python scripts."
    )
    assert {"docker", "kubernetes", "aws", "python", "devops"} <= slugs(extractor, "", text)


@pytest.mark.parametrize(
    ("text", "present", "absent"),
    [
        ("Frontend role: React, Redux and TypeScript.", {"react"}, set()),
        ("You must react quickly to production incidents.", set(), {"react"}),
        ("Services written in Go and Python, deployed on Kubernetes.", {"go"}, set()),
        ("Be ready to go through code reviews and go the extra mile.", set(), {"go"}),
        ("Serverless with AWS: Lambda, API Gateway, DynamoDB.", {"aws"}, set()),
        ("Python: list comprehensions and lambda expressions.", set(), {"aws"}),
        ("Big data with Spark and Hadoop on clusters.", {"spark", "hadoop"}, set()),
        ("We hope to spark curiosity in every learner.", set(), {"spark"}),
        ("Excel in a fast paced environment.", set(), {"excel"}),
        ("Advanced Excel, pivot tables and VLOOKUP.", {"excel"}, set()),
        ("Statistical modelling in R with ggplot2 and tidyverse.", {"r"}, set()),
        ("Strong R&D background, r is not mentioned as a language.", set(), {"r"}),
        ("Embedded firmware in C and C++ for microcontroller boards.", {"c", "cpp"}, set()),
        ("Grade C students are welcome.", set(), {"c"}),
    ],
)
def test_ambiguous_aliases_need_context(
    extractor: SkillExtractor, text: str, present: set[str], absent: set[str]
) -> None:
    found = slugs(extractor, "", text)
    assert present <= found, found
    assert not (absent & found), found


def test_longest_match_wins(extractor: SkillExtractor) -> None:
    found = slugs(extractor, "", "Experience with Apache Spark and GitHub Actions.")
    assert "spark" in found
    assert "github-actions" in found


def test_requirement_levels(extractor: SkillExtractor) -> None:
    desc = (
        "Requirements:\n"
        "- 3+ years of Python\n"
        "- Docker and Kubernetes\n"
        "Nice to have:\n"
        "- Kafka\n"
        "We use Jira for planning.\n"
        "Knowledge of Terraform is a plus."
    )
    got = {
        s.slug: s.requirement
        for s in extractor.extract([("title", "Backend Engineer"), ("description", desc)])
    }
    assert got["python"] == "required"
    assert got["docker"] == "required"
    assert got["kafka"] == "nice_to_have"
    assert got["jira"] == "nice_to_have"  # still inside the "Nice to have" section
    assert got["terraform"] == "nice_to_have"


def test_title_mentions_are_required(extractor: SkillExtractor) -> None:
    got = {s.slug: s for s in extractor.extract([("title", "Java Developer"), ("description", "")])}
    assert got["java"].requirement == "required"
    assert got["java"].confidence == extractor.rule_confidence["exact_alias:title"]


def test_evidence_spans_point_at_the_text(extractor: SkillExtractor) -> None:
    desc = "Build APIs with FastAPI on PostgreSQL."
    for skill in extractor.extract([("description", desc)]):
        for ev in skill.evidence:
            assert desc[ev.start : ev.end] == ev.text


def test_parent_skills_are_implied(extractor: SkillExtractor) -> None:
    result = {s.slug: s for s in extractor.extract([("description", "PostgreSQL and PySpark.")])}
    assert result["sql"].implied is True
    assert result["spark"].implied is True
    assert result["postgresql"].implied is False
    assert result["sql"].evidence[0].rule == "implied_by:postgresql"


def test_direct_mention_beats_implied(extractor: SkillExtractor) -> None:
    result = {s.slug: s for s in extractor.extract([("description", "SQL and PostgreSQL.")])}
    assert result["sql"].implied is False


def test_confidence_bounds_and_version(extractor: SkillExtractor) -> None:
    for s in extractor.extract([("description", "Python, Go, React, Excel, SQL, AWS Lambda")]):
        assert 0 < s.confidence <= 1
    assert extractor.version.startswith("2.0+")


def test_empty_text(extractor: SkillExtractor) -> None:
    assert extractor.extract([("title", ""), ("description", "   ")]) == []
