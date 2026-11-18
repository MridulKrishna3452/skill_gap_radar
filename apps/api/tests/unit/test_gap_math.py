"""Gap math against hand-computed values.

Fixture: 10 postings in the window.
    skill  postings  required  coverage   share  gap = share * (1 - coverage)
    A=1       8         6        1.0       0.8    0.0
    B=2       5         1        0.5       0.5    0.25
    C=3       2         0        0.0       0.2    0.2
    D=4       1         0        0.8       0.1    0.02
sum(share) = 1.6; sum(share * coverage) = 0.8 + 0.25 + 0 + 0.08 = 1.13
weighted_coverage = 1.13 / 1.6 = 0.70625; gap_index = 0.29375
top-2 by demand = A, B -> mean coverage 0.75
"""

import pytest

from app.services.analytics.demand import SkillDemand
from app.services.analytics.gap import compute_gap

DEMAND = [SkillDemand(1, 8, 6), SkillDemand(2, 5, 1), SkillDemand(3, 2, 0), SkillDemand(4, 1, 0)]
COVERAGE = {1: 1.0, 2: 0.5, 4: 0.8}


def test_per_skill_rows() -> None:
    _, rows = compute_gap(10, DEMAND, COVERAGE, top_n=2)
    assert [r.skill_id for r in rows] == [2, 3, 4, 1]  # sorted by gap
    by_id = {r.skill_id: r for r in rows}
    assert by_id[1].demand_share == pytest.approx(0.8)
    assert by_id[1].required_share == pytest.approx(0.6)
    assert by_id[2].gap == pytest.approx(0.25)
    assert by_id[3].gap == pytest.approx(0.2)
    assert by_id[3].coverage == 0.0
    assert by_id[4].gap == pytest.approx(0.02)
    assert by_id[1].gap == pytest.approx(0.0)


def test_summary() -> None:
    summary, _ = compute_gap(10, DEMAND, COVERAGE, top_n=2)
    assert summary.total_postings == 10
    assert summary.skills_in_demand == 4
    assert summary.weighted_coverage == pytest.approx(0.70625)
    assert summary.gap_index == pytest.approx(0.29375)
    assert summary.top_n == 2
    assert summary.top_n_coverage == pytest.approx(0.75)
    assert summary.top_n_covered_count == 2


def test_regression_v1_coverage_bias() -> None:
    """legacy/NOTICE.md: v1 measured coverage over the top 20 skills *sorted by gap*.

    On this fixture v1's method gives (B 0.5 + C 0.0) / 2 = 0.25 for the top 2, because sorting
    by gap first picks the uncovered skills. The demand-ranked top 2 is A and B: 0.75.
    """
    summary, rows = compute_gap(10, DEMAND, COVERAGE, top_n=2)
    v1_style = sum(r.coverage for r in rows[:2]) / 2
    assert v1_style == pytest.approx(0.25)
    assert summary.top_n_coverage == pytest.approx(0.75)


def test_no_postings_gives_no_numbers() -> None:
    summary, rows = compute_gap(0, DEMAND, COVERAGE)
    assert rows == []
    assert summary.weighted_coverage is None
    assert summary.top_n_coverage is None
    assert summary.gap_index is None


def test_no_curriculum_means_zero_coverage() -> None:
    summary, rows = compute_gap(10, DEMAND, {})
    assert summary.weighted_coverage == 0.0
    assert summary.gap_index == 1.0
    assert rows[0].skill_id == 1  # biggest demand, nothing covered -> biggest gap


def test_changes_when_data_changes() -> None:
    """No hardcoded metrics: different inputs give different outputs."""
    a, _ = compute_gap(10, DEMAND, COVERAGE)
    c, _ = compute_gap(10, DEMAND, {**COVERAGE, 3: 1.0})
    assert a.weighted_coverage != c.weighted_coverage
