"""Mocked Adzuna API responses (shape of GET /jobs/{country}/search/{page}). Test-only data."""

from typing import Any


def adzuna_result(i: int, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": str(4000000000 + i),
        "title": f"<strong>Data Engineer</strong> {i}",
        "description": "Requirements: Python, SQL and Apache Spark. Airflow is a plus.",
        "created": "2026-10-15T08:30:00Z",
        "redirect_url": f"https://www.adzuna.in/land/ad/{4000000000 + i}",
        "company": {"display_name": "Acme Analytics Pvt Ltd"},
        "location": {"display_name": "Bangalore, Karnataka", "area": ["India", "Karnataka"]},
        "category": {"label": "IT Jobs", "tag": "it-jobs"},
        "salary_min": 800000,
        "salary_max": 1200000,
        "salary_is_predicted": "1",
        "contract_time": "full_time",
        "contract_type": "permanent",
    }
    item.update(overrides)
    return item


def adzuna_page(results: list[dict[str, Any]], count: int | None = None) -> dict[str, Any]:
    return {"results": results, "count": count if count is not None else len(results)}
