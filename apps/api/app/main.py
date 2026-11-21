"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import create_engine, create_session_factory
from app.workers.queue import CeleryQueue

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings)
    redis = Redis.from_url(settings.REDIS_URL, socket_timeout=settings.HEALTHCHECK_TIMEOUT)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = redis
    logger.info("%s %s starting (env=%s)", settings.APP_NAME, settings.APP_VERSION, settings.ENV)
    if settings.jwt_secret_generated:
        logger.warning(
            "JWT_SECRET is not set: using a random per-process secret. Sessions end when the "
            "API restarts. Set JWT_SECRET (32+ characters) to keep them."
        )
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.LOG_LEVEL, json_output=settings.is_production)

    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version=settings.APP_VERSION,
        description="Career intelligence and skill gap analysis platform.",
        lifespan=lifespan,
        # Interactive docs are useful locally but needless attack surface in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
    )
    app.state.settings = settings
    app.state.task_queue = CeleryQueue()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    # Added last so it wraps everything, including CORS responses and error handlers.
    app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()
