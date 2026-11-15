"""Runs against real Postgres and Redis after `alembic upgrade head`.

Enabled with RUN_INTEGRATION=1 (CI sets it and provides service containers).
"""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1"),
]


@pytest.fixture
async def live_client() -> AsyncIterator[tuple[AsyncClient, object]]:
    app = create_app(Settings(ENV="test"))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def test_ready_against_real_services(live_client: tuple[AsyncClient, object]) -> None:
    client, _ = live_client
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200, resp.text
    assert resp.json()["checks"] == {"database": "ok", "redis": "ok"}


async def test_migrations_enabled_extensions(live_client: tuple[AsyncClient, object]) -> None:
    _, app = live_client
    async with app.state.engine.connect() as conn:  # type: ignore[attr-defined]
        rows = await conn.execute(text("SELECT extname FROM pg_extension"))
        extensions = {r[0] for r in rows}
    assert {"vector", "pg_trgm"} <= extensions


async def test_vector_similarity_works(live_client: tuple[AsyncClient, object]) -> None:
    _, app = live_client
    async with app.state.engine.connect() as conn:  # type: ignore[attr-defined]
        distance = await conn.scalar(text("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector"))
    assert distance == pytest.approx(1.0)
