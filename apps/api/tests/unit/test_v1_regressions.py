"""One regression test per v1 bug listed in legacy/NOTICE.md.

The coverage-% bug has its numeric regression test in test_gap_math.py
(test_regression_v1_coverage_bias). Database-level checks for synthetic data being excluded
from analytics live in tests/integration/test_pipeline.py.
"""

import ast
from pathlib import Path

from fastapi import FastAPI

import app as app_package
from app.core.config import Settings
from app.main import create_app

APP_DIR = Path(app_package.__file__).parent


def _app_sources() -> list[tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in APP_DIR.rglob("*.py")]


def test_bug1_no_mock_job_generators_in_app_code() -> None:
    """v1: NaukriScraper / CareerPagesScraper always generated mock jobs; Internshala fell back
    to mock jobs; loaders wrote mock input files. No production code may generate postings."""
    banned = ("generate_mock", "mock_jobs", "job_templates", "random.choice")
    for path, src in _app_sources():
        for word in banned:
            assert word not in src, f"{word!r} found in {path}"


def test_bug1_every_source_declares_whether_it_is_synthetic() -> None:
    from app.models import JobSource

    assert JobSource.__table__.c.is_synthetic.nullable is False


def test_bug2_curriculum_pdf_is_never_generated_by_the_app() -> None:
    """v1 created its own sample syllabus PDF and parsed it. 2.0 only parses uploaded files."""
    for path, src in _app_sources():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("new_page", "insert_text"):
                raise AssertionError(f"PDF generation call {node.attr} in {path}")
            if isinstance(node, ast.FunctionDef):
                assert "sample_syllabus" not in node.name, path


def test_bug3_no_hardcoded_dashboard_values_in_api() -> None:
    """v1's home radar chart used literal values. The 2.0 analytics modules compute from the
    database; this guards against literal metric lists creeping into them. (The Phase 6 UI has
    its own check.) Numeric behaviour is covered by test_gap_math.test_changes_when_data_changes
    and the integration test test_demand_changes_with_data."""
    for path, src in _app_sources():
        if "analytics" not in path.parts and "recommendations" not in path.stem:
            continue
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.List) and len(node.elts) >= 3:
                nums = [
                    e
                    for e in node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, int | float)
                ]
                assert len(nums) < 3, f"literal number list in {path}:{node.lineno}"


def test_bug5_entry_point_works_without_dash() -> None:
    """v1's run.py called Dash's removed app.run_server. 2.0 serves a FastAPI app via uvicorn
    (`uvicorn app.main:app`); the factory must build without any Dash dependency."""
    application = create_app(Settings(ENV="test"))
    assert isinstance(application, FastAPI)
    for _, src in _app_sources():
        assert "import dash" not in src and "run_server" not in src
