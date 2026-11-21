"""Skill extraction v2: alias matching, disambiguation, requirement, evidence, implied skills."""

import pytest

from app.services.extraction.extractor import EXTRACTOR_VERSION, SkillExtractor
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
        # Seen in a real syllabus (Pondicherry University B.Tech CSE, 2023-24).
        ("Solid-state lasers (ruby - Neodymium) - dye lasers.", set(), {"ruby"}),
        ("Backend developer: Ruby, Python and PostgreSQL.", {"ruby"}, set()),
        ("Design of an Absolute Loader - A Simple Bootstrap Loader.", set(), {"css"}),
        ("Responsive web pages with HTML5, CSS3 and Bootstrap.", {"css"}, set()),
        ("Schematic capture and electronic system design flow.", set(), {"system-design"}),
        ("File system design details - file and directory layout.", set(), {"system-design"}),
        ("Strong system design skills for scalable backend services.", {"system-design"}, set()),
    ],
)
def test_ambiguous_aliases_need_context(
    extractor: SkillExtractor, text: str, present: set[str], absent: set[str]
) -> None:
    found = slugs(extractor, "", text)
    assert present <= found, found
    assert not (absent & found), found


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Testing methodologies are not test automation, and vice versa.
        (
            "Manual testing and exploratory testing of desktop software.",
            {"manual-testing", "exploratory-testing"},
        ),
        ("Systematic regression testing before each release.", {"regression-testing"}),
        ("Build test automation frameworks with Selenium and Cypress.", {"test-automation"}),
        ("Unit tests with pytest and JUnit.", {"unit-testing"}),
        # The most specific skill wins; the parent is only implied.
        ("Mobile apps in React Native.", {"react-native"}),
        ("Styling with Tailwind CSS.", {"tailwind-css"}),
        ("Testing Pega Smart Dispute for Issuers.", {"pega-smart-dispute"}),
    ],
)
def test_specific_skills(extractor: SkillExtractor, text: str, expected: set[str]) -> None:
    assert slugs(extractor, "", text) == expected


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
    assert extractor.version.startswith(f"{EXTRACTOR_VERSION}+")


def test_empty_text(extractor: SkillExtractor) -> None:
    assert extractor.extract([("title", ""), ("description", "   ")]) == []


@pytest.mark.parametrize(
    ("text", "absent", "present"),
    [
        # Found in real Adzuna snippets, which are cut off with an ellipsis.
        ("expertise in DevOps methodologies and CI/C…", {"c"}, {"devops"}),
        ("Skill : Javascript, HTML/CSS, Python and R…", {"r"}, {"python"}),
        ("Strong Java…", {"java"}, set()),
        ("Strong Java...", {"java"}, set()),
        # Not the start of another skill's alias: a complete word, kept.
        ("Cloud on AWS…", set(), {"aws"}),
        ("Strong Java.", set(), {"java"}),
    ],
)
def test_truncated_words_that_could_be_another_skill_are_dropped(
    extractor: SkillExtractor, text: str, absent: set[str], present: set[str]
) -> None:
    found = slugs(extractor, "", text)
    assert not (absent & found), found
    assert present <= found, found
