import pytest

from app.services.extraction.taxonomy import read_seed
from app.services.roles import classify_title, compile_rules

ROLES = read_seed("roles.json")["roles"]
RULES = compile_rules([(i, r["match_priority"], r["title_patterns"]) for i, r in enumerate(ROLES)])
SLUG = {i: r["slug"] for i, r in enumerate(ROLES)}


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Data Engineer - Spark", "data-engineer"),
        ("Machine Learning Engineer", "machine-learning-engineer"),
        ("GenAI Engineer (LLM)", "ai-engineer"),
        ("DevOps / SRE Engineer", "devops-engineer"),
        ("Software Development Engineer II", "software-engineer"),
        ("Full Stack Developer (MERN)", "full-stack-developer"),
        ("Java Developer", "software-engineer"),
        ("Sales Executive", None),
    ],
)
def test_classify_title(title: str, expected: str | None) -> None:
    role = classify_title(title, RULES)
    assert (SLUG[role] if role is not None else None) == expected


def test_whole_word_patterns_only() -> None:
    # "sre" occurs inside "presales" but is not a whole word there.
    assert classify_title("Presales Consultant", RULES) is None
