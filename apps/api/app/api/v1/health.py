"""Liveness and readiness probes.

- /health/live: the process is up. Never touches dependencies, so a slow database does not
  get healthy containers restarted.
- /health/ready: Postgres and Redis answer within HEALTHCHECK_TIMEOUT. Returns 503 otherwise,
  so a load balancer stops routing traffic to this instance.
"""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["system"])
logger = logging.getLogger(__name__)

CheckStatus = Literal["ok", "error"]


class LiveResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadyResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckStatus]


@router.get("/live", response_model=LiveResponse)
async def live(request: Request) -> LiveResponse:
    return LiveResponse(status="ok", version=request.app.state.settings.APP_VERSION)


async def _check_database(request: Request) -> None:
    async with request.app.state.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis(request: Request) -> None:
    await request.app.state.redis.ping()


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={503: {"model": ReadyResponse, "description": "A dependency is unavailable"}},
)
async def ready(request: Request, response: Response) -> ReadyResponse:
    timeout = request.app.state.settings.HEALTHCHECK_TIMEOUT
    checks: dict[str, CheckStatus] = {}

    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            await asyncio.wait_for(check(request), timeout=timeout)
            checks[name] = "ok"
        except Exception as exc:
            # Log the cause server-side; the response only says which dependency failed.
            logger.warning("Readiness check %s failed: %s", name, type(exc).__name__)
            checks[name] = "error"

    healthy = all(status == "ok" for status in checks.values())
    if not healthy:
        response.status_code = 503
    return ReadyResponse(status="ok" if healthy else "degraded", checks=checks)
