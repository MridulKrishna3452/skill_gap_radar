"""Pluggable job-source framework.

A connector turns one external source into a stream of RawPosting items (or FetchProblem
items for records/pages it could not use). The runner (runner.py) does everything else:
normalisation, dedup, storage and run accounting, identically for every source.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass
class RawPosting:
    external_id: str
    title: str
    description: str
    posted_at: datetime
    company: str | None = None
    location: str | None = None
    country: str | None = None
    url: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_is_estimated: bool | None = None
    employment_type: str | None = None
    category: str | None = None
    experience_text: str | None = None


@dataclass
class FetchProblem:
    """A record or page that could not be used. message must not contain secrets."""

    message: str
    fatal: bool = False  # stop the run (e.g. authentication failure)


class SourceConnector(Protocol):
    key: str

    def fetch(self, params: dict[str, Any]) -> AsyncIterator[RawPosting | FetchProblem]: ...


class IngestionConfigError(Exception):
    """The source cannot run as configured (missing credentials, bad parameters)."""
