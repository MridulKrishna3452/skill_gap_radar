import pytest

from app.services.recommendations import coverage_status, priority_for


@pytest.mark.parametrize(
    ("share", "total", "expected"),
    [
        (0.45, 100, "high"),
        (0.30, 100, "high"),
        (0.12, 100, "medium"),
        (0.02, 100, "low"),
        (0.0, 100, "low"),
        (0.90, 5, "insufficient_data"),
    ],
)
def test_priority_from_demand_share(share: float, total: int, expected: str) -> None:
    assert priority_for(share, total, min_postings=30) == expected


def test_coverage_status() -> None:
    assert coverage_status(1.0) == "covered"
    assert coverage_status(0.5) == "partial"
    assert coverage_status(0.0) == "missing"
