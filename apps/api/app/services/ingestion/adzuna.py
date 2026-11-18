"""Adzuna job search API connector.

GET {base}/jobs/{country}/search/{page}?app_id&app_key&results_per_page&what&where&max_days_old

Notes on the data (they matter for analytics):
- `description` is a snippet (a few hundred characters), not the full ad, so extraction
  sees only part of each posting.
- `salary_is_predicted` = "1" means Adzuna estimated the salary; we store that flag.
- Titles can contain <strong> highlight tags, removed by the runner's HTML cleaning.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.services.ingestion.base import (
    FetchProblem,
    IngestionConfigError,
    RawPosting,
)

logger = logging.getLogger(__name__)

SUPPORTED_COUNTRIES = frozenset(
    {
        "in",
        "gb",
        "us",
        "au",
        "ca",
        "de",
        "fr",
        "nl",
        "sg",
        "nz",
        "za",
        "br",
        "pl",
        "it",
        "es",
        "at",
        "be",
        "ch",
        "mx",
    }
)
CURRENCY_BY_COUNTRY = {
    "in": "INR",
    "gb": "GBP",
    "us": "USD",
    "au": "AUD",
    "ca": "CAD",
    "sg": "SGD",
    "nz": "NZD",
    "za": "ZAR",
    "br": "BRL",
    "pl": "PLN",
    "mx": "MXN",
    "ch": "CHF",
}
EURO_COUNTRIES = frozenset({"de", "fr", "nl", "it", "es", "at", "be"})
RESULTS_PER_PAGE = 50
MAX_RETRIES = 3


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_result(item: dict[str, Any], country: str) -> RawPosting:
    """Map one Adzuna result to RawPosting. Raises KeyError/ValueError on unusable records."""
    contract_time = item.get("contract_time")
    contract_type = item.get("contract_type")
    employment = (
        " ".join(str(p).replace("_", " ") for p in (contract_time, contract_type) if p) or None
    )
    predicted = item.get("salary_is_predicted")
    currency = "EUR" if country in EURO_COUNTRIES else CURRENCY_BY_COUNTRY.get(country)
    salary_min, salary_max = _num(item.get("salary_min")), _num(item.get("salary_max"))
    return RawPosting(
        external_id=str(item["id"]),
        title=str(item["title"]),
        description=str(item.get("description") or ""),
        posted_at=_parse_dt(str(item["created"])),
        company=(item.get("company") or {}).get("display_name"),
        location=(item.get("location") or {}).get("display_name"),
        country=country,
        url=item.get("redirect_url"),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency if (salary_min or salary_max) else None,
        salary_is_estimated=(str(predicted) == "1") if predicted is not None else None,
        employment_type=employment,
        category=(item.get("category") or {}).get("label"),
    )


class AdzunaConnector:
    key = "adzuna"

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        if not settings.adzuna_enabled:
            raise IngestionConfigError(
                "Adzuna is not configured: set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env"
            )
        self.settings = settings
        self._client = client
        self._sleep = sleep

    @staticmethod
    def validate_params(params: dict[str, Any], max_pages: int) -> dict[str, Any]:
        country = str(params.get("country", "in")).lower()
        if country not in SUPPORTED_COUNTRIES:
            raise IngestionConfigError(f"Unsupported Adzuna country: {country}")
        pages = int(params.get("pages", 1))
        if not 1 <= pages <= max_pages:
            raise IngestionConfigError(f"pages must be between 1 and {max_pages}")
        clean: dict[str, Any] = {"country": country, "pages": pages}
        for key in ("what", "where", "category"):
            if params.get(key):
                clean[key] = str(params[key])[:200]
        if params.get("max_days_old") is not None:
            clean["max_days_old"] = max(1, min(int(params["max_days_old"]), 365))
        return clean

    async def _get_page(
        self, client: httpx.AsyncClient, country: str, page: int, query: dict[str, Any]
    ) -> dict[str, Any] | FetchProblem:
        url = f"{self.settings.ADZUNA_BASE_URL}/jobs/{country}/search/{page}"
        auth = {
            "app_id": self.settings.ADZUNA_APP_ID,
            "app_key": self.settings.ADZUNA_APP_KEY.get_secret_value(),
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.get(url, params={**auth, **query}, timeout=30)
            except httpx.HTTPError as exc:
                problem = f"page {page}: network error ({type(exc).__name__})"
            else:
                if resp.status_code == 200:
                    data: dict[str, Any] = resp.json()
                    return data
                if resp.status_code in (401, 403):
                    return FetchProblem(
                        f"Adzuna rejected the credentials (HTTP {resp.status_code})", fatal=True
                    )
                problem = f"page {page}: HTTP {resp.status_code}"
                if resp.status_code not in (429, 500, 502, 503, 504):
                    return FetchProblem(problem)
            if attempt < MAX_RETRIES:
                await self._sleep(2**attempt)
        return FetchProblem(problem + f" after {MAX_RETRIES} attempts")

    async def fetch(self, params: dict[str, Any]) -> AsyncIterator[RawPosting | FetchProblem]:
        p = self.validate_params(params, self.settings.ADZUNA_MAX_PAGES_PER_RUN)
        country = p["country"]
        query: dict[str, Any] = {"results_per_page": RESULTS_PER_PAGE}
        for key in ("what", "where", "max_days_old"):
            if key in p:
                query[key] = p[key]
        if "category" in p:
            query["category"] = p["category"]

        client = self._client or httpx.AsyncClient(headers={"Accept": "application/json"})
        try:
            for page in range(1, p["pages"] + 1):
                if page > 1:
                    await self._sleep(self.settings.ADZUNA_MIN_SECONDS_BETWEEN_CALLS)
                data = await self._get_page(client, country, page, query)
                if isinstance(data, FetchProblem):
                    yield data
                    if data.fatal:
                        return
                    continue
                results = data.get("results") or []
                for item in results:
                    try:
                        yield parse_result(item, country)
                    except (KeyError, ValueError, TypeError) as exc:
                        yield FetchProblem(f"page {page}: unusable record ({type(exc).__name__})")
                if len(results) < RESULTS_PER_PAGE:
                    break  # last page
        finally:
            if self._client is None:
                await client.aclose()
