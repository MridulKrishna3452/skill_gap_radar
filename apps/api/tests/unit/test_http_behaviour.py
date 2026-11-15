from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel

from app.core.errors import NotFoundError


def _add_test_routes(app: FastAPI) -> None:
    class Payload(BaseModel):
        email: str
        age: int

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail: /etc/db.conf")

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("Skill not found")

    @app.post("/echo")
    async def echo(payload: Payload) -> Payload:
        return payload


async def test_request_id_generated_and_returned(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert len(resp.headers["x-request-id"]) == 32


async def test_valid_request_id_is_echoed(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["x-request-id"] == "abc-123"


async def test_unsafe_request_id_is_replaced(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live", headers={"X-Request-ID": "bad id\r\nx: y"})
    assert resp.headers["x-request-id"] != "bad id\r\nx: y"
    assert len(resp.headers["x-request-id"]) == 32


async def test_security_headers_present(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in resp.headers  # HSTS only in production


async def test_unknown_route_uses_error_shape(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/nope")
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == resp.headers["x-request-id"]


async def test_app_error_maps_to_status(app: FastAPI, client: AsyncClient) -> None:
    _add_test_routes(app)
    resp = await client.get("/missing")
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "Skill not found"


async def test_unhandled_error_is_generic_500(app: FastAPI, client: AsyncClient) -> None:
    _add_test_routes(app)
    resp = await client.get("/boom")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "secret" not in resp.text
    assert resp.headers["x-request-id"]


async def test_validation_error_does_not_echo_input(app: FastAPI, client: AsyncClient) -> None:
    _add_test_routes(app)
    resp = await client.post("/echo", json={"email": "a@b.c", "age": "hunter2-not-a-number"})
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", "age"]
    assert "hunter2" not in resp.text


async def test_cors_allows_configured_origin_only(client: AsyncClient) -> None:
    ok = await client.options(
        "/api/v1/health/live",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"

    bad = await client.options(
        "/api/v1/health/live",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers
