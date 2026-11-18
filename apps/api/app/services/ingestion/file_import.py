"""CSV / JSON import for licensed job-posting datasets.

The file's columns are mapped onto the canonical fields below with an optional column map
({"title": "job_title", ...}). Rows without a usable title, description or posting date are
reported as problems, never filled in with guesses (v1 used "today" for unparseable dates).
"""

import csv
import hashlib
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.ingestion.base import FetchProblem, IngestionConfigError, RawPosting

CANONICAL_FIELDS = (
    "external_id",
    "title",
    "description",
    "posted_at",
    "company",
    "location",
    "country",
    "url",
    "salary_min",
    "salary_max",
    "salary_currency",
    "employment_type",
    "category",
    "experience_text",
)
REQUIRED_FIELDS = ("title", "description", "posted_at")
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%b %d, %Y",
    "%Y-%m-%d %H:%M:%S",
)


def parse_date(value: str) -> datetime:
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"unrecognised date {value[:40]!r}") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(str(value).replace(",", ""))


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as fh:
            yield from csv.DictReader(fh)
    elif suffix in (".json", ".jsonl"):
        with path.open(encoding="utf-8") as fh:
            if suffix == ".jsonl":
                for line in fh:
                    if line.strip():
                        yield json.loads(line)
            else:
                data = json.load(fh)
                items = data.get("jobs", data.get("results")) if isinstance(data, dict) else data
                if not isinstance(items, list):
                    raise IngestionConfigError("JSON must be a list or have a 'jobs' list")
                yield from items
    else:
        raise IngestionConfigError("Supported file types: .csv, .json, .jsonl")


def row_to_posting(row: dict[str, Any], mapping: dict[str, str]) -> RawPosting:
    def get(name: str) -> Any:
        value = row.get(mapping.get(name, name))
        return value.strip() if isinstance(value, str) else value

    missing = [f for f in REQUIRED_FIELDS if not get(f)]
    if missing:
        raise ValueError(f"missing {', '.join(missing)}")
    title, description = str(get("title")), str(get("description"))
    external_id = (
        get("external_id")
        or hashlib.sha256(
            f"{title}\x1f{get('company')}\x1f{get('posted_at')}\x1f{description}".encode()
        ).hexdigest()
    )
    country = get("country")
    return RawPosting(
        external_id=str(external_id)[:255],
        title=title,
        description=description,
        posted_at=parse_date(str(get("posted_at"))),
        company=get("company") or None,
        location=get("location") or None,
        country=str(country).lower()[:2] if country else None,
        url=get("url") or None,
        salary_min=_float(get("salary_min")),
        salary_max=_float(get("salary_max")),
        salary_currency=(get("salary_currency") or None),
        employment_type=get("employment_type") or None,
        category=get("category") or None,
        experience_text=get("experience_text") or None,
    )


class FileConnector:
    key = "file"

    def __init__(self, path: Path, mapping: dict[str, str] | None = None) -> None:
        if not path.is_file():
            raise IngestionConfigError(f"File not found: {path}")
        unknown = set(mapping or {}) - set(CANONICAL_FIELDS)
        if unknown:
            raise IngestionConfigError(f"Unknown fields in column map: {sorted(unknown)}")
        self.path = path
        self.mapping = mapping or {}

    async def fetch(self, params: dict[str, Any]) -> AsyncIterator[RawPosting | FetchProblem]:
        for i, row in enumerate(_rows(self.path), start=1):
            try:
                yield row_to_posting(row, self.mapping)
            except (ValueError, TypeError) as exc:
                yield FetchProblem(f"row {i}: {exc}")
