import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.ingestion.base import FetchProblem, IngestionConfigError, RawPosting
from app.services.ingestion.file_import import FileConnector, parse_date


async def collect(c: FileConnector) -> list[RawPosting | FetchProblem]:
    return [i async for i in c.fetch({})]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-03-04", datetime(2026, 3, 4, tzinfo=UTC)),
        ("2026-03-04T10:00:00Z", datetime(2026, 3, 4, 10, tzinfo=UTC)),
        ("04/03/2026", datetime(2026, 3, 4, tzinfo=UTC)),
        ("4 Mar 2026", datetime(2026, 3, 4, tzinfo=UTC)),
    ],
)
def test_parse_date(value: str, expected: datetime) -> None:
    assert parse_date(value) == expected


def test_parse_date_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="unrecognised date"):
        parse_date("last week")


async def test_csv_with_column_map(tmp_path: Path) -> None:
    f = tmp_path / "jobs.csv"
    f.write_text(
        "job_title,company,date,text,job_id\n"
        "Data Engineer,Acme,2026-01-05,Python and SQL,a1\n"
        "Analyst,Beta,,Excel,a2\n",
        encoding="utf-8",
    )
    items = await collect(
        FileConnector(
            f,
            {
                "title": "job_title",
                "posted_at": "date",
                "description": "text",
                "external_id": "job_id",
            },
        )
    )
    assert isinstance(items[0], RawPosting) and items[0].external_id == "a1"
    # A row without a date is reported, never stamped with "today" (v1 did that).
    assert isinstance(items[1], FetchProblem) and "posted_at" in items[1].message


async def test_json_list_and_generated_ids_are_stable(tmp_path: Path) -> None:
    rows = [{"title": "Dev", "description": "Go", "posted_at": "2026-02-01", "company": "X"}]
    f = tmp_path / "jobs.json"
    f.write_text(json.dumps({"jobs": rows}), encoding="utf-8")
    first = await collect(FileConnector(f))
    second = await collect(FileConnector(f))
    assert isinstance(first[0], RawPosting) and isinstance(second[0], RawPosting)
    assert first[0].external_id == second[0].external_id


def test_rejects_unknown_map_fields_and_types(tmp_path: Path) -> None:
    f = tmp_path / "x.csv"
    f.write_text("a\n", encoding="utf-8")
    with pytest.raises(IngestionConfigError):
        FileConnector(f, {"salary": "pay"})
    with pytest.raises(IngestionConfigError):
        FileConnector(tmp_path / "missing.csv")
