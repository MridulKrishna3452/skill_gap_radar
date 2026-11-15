import asyncio

from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import FakeEngine, FakeRedis


async def test_live_returns_ok_and_version(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "2.0.0.dev0"}


async def test_ready_ok_when_dependencies_answer(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def test_ready_503_when_redis_down(app: FastAPI, client: AsyncClient) -> None:
    app.state.redis = FakeRedis(fail=ConnectionError("refused"))
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"] == {"database": "ok", "redis": "error"}


async def test_ready_503_when_database_errors(app: FastAPI, client: AsyncClient) -> None:
    app.state.engine = FakeEngine(fail=OSError("password authentication failed for user x"))
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body == {"status": "degraded", "checks": {"database": "error", "redis": "ok"}}
    assert "password" not in resp.text  # failure cause is logged, never returned


async def test_ready_times_out_slow_dependency(app: FastAPI, client: AsyncClient) -> None:
    class SlowRedis(FakeRedis):
        async def ping(self) -> bool:
            await asyncio.sleep(5)
            return True

    app.state.redis = SlowRedis()
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["redis"] == "error"
