from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


class FakeConnection:
    def __init__(self, fail: BaseException | None) -> None:
        self.fail = fail

    async def execute(self, *_: Any) -> None:
        if self.fail:
            raise self.fail


class FakeEngine:
    """Stands in for AsyncEngine in unit tests: connect() succeeds or raises `fail`."""

    def __init__(self, fail: BaseException | None = None) -> None:
        self.fail = fail

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[FakeConnection]:
        yield FakeConnection(self.fail)


class FakeRedis:
    def __init__(self, fail: BaseException | None = None) -> None:
        self.fail = fail

    async def ping(self) -> bool:
        if self.fail:
            raise self.fail
        return True


@pytest.fixture
def settings() -> Settings:
    return Settings(ENV="test", CORS_ORIGINS=["http://localhost:3000"], HEALTHCHECK_TIMEOUT=0.2)


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    # Unit tests skip the lifespan (no real DB/Redis) and install fakes instead.
    application = create_app(settings)
    application.state.engine = FakeEngine()
    application.state.redis = FakeRedis()
    yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
