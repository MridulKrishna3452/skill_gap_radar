"""Ported v1 normalizer tests (legacy/tests/test_modules.py::test_job_cleaning) plus 2.0 fixes."""

import pytest

from app.services.normalize import (
    clean_html,
    company_key,
    content_hash,
    normalize_company,
    normalize_location,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Google Inc.", "Google"),  # v1 case
        ("Hedgehog Private Limited", "Hedgehog"),  # v1 case
        ("Infosys Pvt. Ltd.", "Infosys"),
        ("Acme Corporation", "Acme"),
        ("IBM", "IBM"),  # v1 title-cased this to "Ibm"
        ("TATA CONSULTANCY SERVICES LIMITED", "Tata Consultancy Services"),
        ("zoho corp", "Zoho"),
        ("Co-operative Bank", "Co-operative Bank"),
    ],
)
def test_normalize_company(raw: str, expected: str) -> None:
    assert normalize_company(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "Ltd"])
def test_normalize_company_empty_is_none_not_invented(raw: str | None) -> None:
    # v1 returned "Unknown Company".
    assert normalize_company(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Bangalore Urban", "Bengaluru"),  # v1 case
        ("work from home", "Remote"),  # v1 case
        ("Bengaluru, Karnataka", "Bengaluru"),
        ("New Delhi", "Delhi NCR"),
        ("Gurgaon, Haryana", "Gurugram"),
        ("Navi Mumbai", "Mumbai"),
        ("Chennai", "Chennai"),
        ("jaipur, rajasthan", "Jaipur, Rajasthan"),
    ],
)
def test_normalize_location(raw: str, expected: str) -> None:
    assert normalize_location(raw) == expected


def test_missing_location_is_unknown_not_remote() -> None:
    # v1 mapped an empty location to "Remote", inventing a fact.
    assert normalize_location(None) is None
    assert normalize_location("") is None


def test_clean_html() -> None:
    assert clean_html("<p>Python &amp; <b>SQL</b></p>") == "Python & SQL"
    assert clean_html("<ul><li>Docker</li><li>Kubernetes</li></ul>", keep_lines=True) == (
        "Docker\nKubernetes"
    )
    assert clean_html(None) == ""


def test_company_key_ignores_case_and_punctuation() -> None:
    assert company_key("Tata Consultancy Services") == company_key("tata-consultancy  services")


def test_content_hash_ignores_case_and_whitespace_only() -> None:
    a = content_hash("Data Engineer", "Acme", "Pune", "Build  pipelines")
    assert a == content_hash("data engineer", "ACME", "pune", "Build pipelines")
    assert a != content_hash("Data Engineer", "Acme", "Pune", "Build models")
