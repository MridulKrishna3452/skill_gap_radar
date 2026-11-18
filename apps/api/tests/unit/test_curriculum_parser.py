import pytest

from app.services.curriculum.parser import CurriculumParseError, parse_pdf
from tests.pdfs import LAYOUT_ONLY, V1_STYLE, make_pdf


def test_regex_strategy_reads_v1_format() -> None:
    result = parse_pdf(make_pdf(V1_STYLE), "syllabus.pdf", max_pages=50)
    assert result.strategy == "regex"
    assert [c.title for c in result.courses] == ["Advanced Data Engineering", "Machine Learning"]
    assert [c.code for c in result.courses] == ["CS 301", "CS 302"]
    first = result.courses[0].units
    assert [u.title for u in first] == [
        "Unit 1: Relational Data Processing",
        "Unit 2: Distributed Systems Foundations",
    ]
    assert "PostgreSQL" in first[0].content
    assert first[0].content.startswith("SQL databases")  # "Topics:" prefix removed
    assert first[0].learning_outcomes == "Write complex SQL queries."
    assert result.unit_count == 3


def test_layout_strategy_when_no_unit_markers() -> None:
    result = parse_pdf(make_pdf(LAYOUT_ONLY), "cloud.pdf", max_pages=50)
    assert result.strategy == "layout"
    titles = {c.title: [u.title for u in c.units] for c in result.courses}
    assert titles == {
        "Cloud Computing": ["Virtualisation Basics", "Kubernetes Orchestration"],
        "Web Development": ["Frontend Engineering"],
    }


def test_units_without_course_heading_use_file_name() -> None:
    pdf = make_pdf([("Module 1 - Basics", 11, False), ("Python syntax and types", 10, False)])
    result = parse_pdf(pdf, "intro_programming.pdf", max_pages=50)
    assert result.courses[0].title == "intro programming"


def test_roman_numeral_units() -> None:
    pdf = make_pdf(
        [
            ("Subject: Operating Systems", 14, False),
            ("UNIT IV: Memory", 11, False),
            ("Paging and segmentation", 10, False),
        ]
    )
    result = parse_pdf(pdf, "os.pdf", max_pages=50)
    assert result.courses[0].units[0].title == "UNIT IV: Memory"


def test_body_text_course_codes_are_not_headings() -> None:
    pdf = make_pdf([("Unit 1: Quality", 11, False), ("ISO 9001 standards and audits", 10, False)])
    result = parse_pdf(pdf, "q.pdf", max_pages=50)
    assert len(result.courses) == 1
    assert "ISO 9001" in result.courses[0].units[0].content


def test_no_units_fails_instead_of_inventing_topics() -> None:
    pdf = make_pdf([("Some text about the department.", 10, False), ("More text.", 10, False)])
    with pytest.raises(CurriculumParseError, match="Could not find course units"):
        parse_pdf(pdf, "x.pdf", max_pages=50)


def test_not_a_pdf() -> None:
    with pytest.raises(CurriculumParseError, match="not a readable PDF"):
        parse_pdf(b"%PDF-1.7 garbage", "x.pdf", max_pages=50)


def test_page_limit() -> None:
    lines = [("Unit 1: A", 11, False)] + [("text", 10, False)] * 120
    with pytest.raises(CurriculumParseError, match="limit is 1"):
        parse_pdf(make_pdf(lines), "x.pdf", max_pages=1)


def test_empty_pdf_is_reported_as_needing_ocr() -> None:
    import pymupdf

    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page()
    data = doc.tobytes()
    with pytest.raises(CurriculumParseError, match="OCR"):
        parse_pdf(data, "scan.pdf", max_pages=50)
