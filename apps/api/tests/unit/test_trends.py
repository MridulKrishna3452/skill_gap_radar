from datetime import date

import pytest

from app.services.analytics.demand import add_months
from app.services.analytics.trends import build_series, compute_movers

JAN, FEB, APR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 4, 1)


def test_share_series_and_month_over_month() -> None:
    s = build_series({JAN: 10, FEB: 20, APR: 5}, {JAN: 5, FEB: 5})
    assert [p.share for p in s] == [0.5, 0.25, 0.0]
    assert s[0].change_pp is None
    assert s[1].change_pp == pytest.approx(-0.25)
    assert s[1].change_rel == pytest.approx(-0.5)
    # March has no postings, so April has no consecutive previous month to compare with.
    assert s[2].change_pp is None


def test_shares_not_raw_counts() -> None:
    # Same count, twice the postings: demand share halves (v1 compared raw counts).
    s = build_series({JAN: 10, FEB: 20}, {JAN: 4, FEB: 4})
    assert s[1].change_pp == pytest.approx(-0.2)


def test_change_rel_none_when_previous_zero() -> None:
    s = build_series({JAN: 10, FEB: 10}, {FEB: 3})
    assert s[1].change_pp == pytest.approx(0.3)
    assert s[1].change_rel is None


def test_movers() -> None:
    prev = {1: 0.10, 2: 0.30, 3: 0.005}
    curr = {1: 0.25, 2: 0.20, 3: 0.04, 4: 0.05}
    m = compute_movers(prev, curr, limit=10)
    assert [x.skill_id for x in m["growing"]] == [1, 4, 3]
    assert [x.skill_id for x in m["declining"]] == [2]
    assert [x.skill_id for x in m["emerging"]] == [4, 3]
    assert m["growing"][0].change_pp == pytest.approx(0.15)
    assert m["growing"][0].change_rel == pytest.approx(1.5)


def test_add_months() -> None:
    assert add_months(JAN, -1) == date(2025, 12, 1)
    assert add_months(date(2026, 11, 1), 2) == date(2027, 1, 1)
