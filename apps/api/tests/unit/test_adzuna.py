"""Adzuna connector against a mocked HTTP API (never the real one)."""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from app.core.config import Settings
from app.services.ingestion.adzuna import AdzunaConnector, parse_result
from app.services.ingestion.base import FetchProblem, IngestionConfigError, RawPosting
from tests.adzuna_fixtures import adzuna_page, adzuna_result

BASE = "https://api.adzuna.test/v1/api"
KEY = "secret-key-123"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        ENV="test",
        ADZUNA_APP_ID="app-id",
        ADZUNA_APP_KEY=SecretStr(KEY),
        ADZUNA_BASE_URL=BASE,
        ADZUNA_MIN_SECONDS_BETWEEN_CALLS=0,
    )


async def no_sleep(_: float) -> None:
    return None


async def collect(connector: AdzunaConnector, params: dict[str, Any]) -> list[Any]:
    return [item async for item in connector.fetch(params)]


def test_parse_result_maps_fields() -> None:
    p = parse_result(adzuna_result(1), "in")
    assert p.external_id == "4000000001"
    assert p.posted_at == datetime(2026, 10, 15, 8, 30, tzinfo=UTC)
    assert p.company == "Acme Analytics Pvt Ltd"
    assert p.salary_currency == "INR"
    assert p.salary_is_estimated is True
    assert p.employment_type == "full time permanent"
    assert p.url and p.url.startswith("https://www.adzuna.in/")


def test_parse_result_without_salary_has_no_currency() -> None:
    p = parse_result(adzuna_result(1, salary_min=None, salary_max=None), "gb")
    assert p.salary_currency is None


def test_not_configured() -> None:
    with pytest.raises(IngestionConfigError):
        AdzunaConnector(Settings(ENV="test", ADZUNA_APP_ID="", ADZUNA_APP_KEY=SecretStr("")))


def test_validate_params() -> None:
    assert AdzunaConnector.validate_params({"country": "IN", "pages": 2, "what": "python"}, 5) == {
        "country": "in",
        "pages": 2,
        "what": "python",
    }
    with pytest.raises(IngestionConfigError):
        AdzunaConnector.validate_params({"country": "zz"}, 5)
    with pytest.raises(IngestionConfigError):
        AdzunaConnector.validate_params({"pages": 9}, 5)


@respx.mock
async def test_paginates_until_short_page(settings: Settings) -> None:
    full = adzuna_page([adzuna_result(i) for i in range(50)])
    last = adzuna_page([adzuna_result(100 + i) for i in range(3)])
    route1 = respx.get(f"{BASE}/jobs/in/search/1").mock(return_value=httpx.Response(200, json=full))
    route2 = respx.get(f"{BASE}/jobs/in/search/2").mock(return_value=httpx.Response(200, json=last))
    route3 = respx.get(f"{BASE}/jobs/in/search/3").mock(return_value=httpx.Response(200, json=last))
    items = await collect(AdzunaConnector(settings, sleep=no_sleep), {"pages": 3, "what": "data"})
    assert len(items) == 53
    assert all(isinstance(i, RawPosting) for i in items)
    assert route1.called and route2.called and not route3.called
    sent = route1.calls[0].request.url.params
    assert sent["what"] == "data" and sent["results_per_page"] == "50"


@respx.mock
async def test_bad_credentials_stop_the_run_without_leaking_key(settings: Settings) -> None:
    respx.get(f"{BASE}/jobs/in/search/1").mock(return_value=httpx.Response(401))
    items = await collect(AdzunaConnector(settings, sleep=no_sleep), {"pages": 2})
    assert len(items) == 1
    assert isinstance(items[0], FetchProblem) and items[0].fatal
    assert KEY not in items[0].message


@respx.mock
async def test_retries_server_errors_then_succeeds(settings: Settings) -> None:
    route = respx.get(f"{BASE}/jobs/in/search/1").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=adzuna_page([adzuna_result(1)]))]
    )
    items = await collect(AdzunaConnector(settings, sleep=no_sleep), {"pages": 1})
    assert route.call_count == 2
    assert [type(i) for i in items] == [RawPosting]


@respx.mock
async def test_gives_up_after_retries(settings: Settings) -> None:
    respx.get(f"{BASE}/jobs/in/search/1").mock(return_value=httpx.Response(500))
    items = await collect(AdzunaConnector(settings, sleep=no_sleep), {"pages": 1})
    assert len(items) == 1 and isinstance(items[0], FetchProblem)
    assert "after 3 attempts" in items[0].message


@respx.mock
async def test_unusable_record_is_reported_not_guessed(settings: Settings) -> None:
    bad = adzuna_result(2)
    del bad["created"]
    respx.get(f"{BASE}/jobs/in/search/1").mock(
        return_value=httpx.Response(200, json=adzuna_page([adzuna_result(1), bad]))
    )
    items = await collect(AdzunaConnector(settings, sleep=no_sleep), {"pages": 1})
    assert isinstance(items[0], RawPosting)
    assert isinstance(items[1], FetchProblem)
