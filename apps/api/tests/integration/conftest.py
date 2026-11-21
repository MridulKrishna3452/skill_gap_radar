"""Integration fixtures: a dedicated test database, migrated once, truncated and re-seeded per
test. The database is DATABASE_URL's database name + "_test" (or TEST_DATABASE_URL), so dev
data is never touched."""

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings

API_DIR = Path(__file__).resolve().parents[2]
ENABLED = os.getenv("RUN_INTEGRATION") == "1"


def _test_db_url() -> str:
    if os.getenv("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    url = make_url(Settings().DATABASE_URL)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


async def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin = create_async_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target.database}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    if not ENABLED:
        pytest.skip("set RUN_INTEGRATION=1")
    url = _test_db_url()
    asyncio.run(_ensure_database(url))
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_DIR, env=env, check=True
    )
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url  # tasks and CLI code read settings from the environment
    get_settings.cache_clear()
    yield url
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    get_settings.cache_clear()


TABLES = (
    "audit_log, refresh_tokens, user_skills, student_profiles, faculty_program_assignments, users, "
    "gap_reports, skill_demand_monthly, unit_skills, course_units, courses, "
    "curriculum_documents, programs, universities, posting_skills, job_postings, companies, "
    "ingestion_runs, job_sources, learning_content, role_skills, roles, skill_aliases, skills"
)


@pytest.fixture
async def factory(test_db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from app.seed.loader import seed_reference_data

    engine = create_async_engine(test_db_url)
    f = async_sessionmaker(engine, expire_on_commit=False)
    async with f() as session:
        await session.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        await seed_reference_data(session)
        await session.commit()
    yield f
    await engine.dispose()


class RecordingQueue:
    def __init__(self) -> None:
        self.sent: list[tuple[str, tuple[Any, ...]]] = []

    async def send(self, name: str, *args: Any) -> None:
        self.sent.append((name, args))


@pytest.fixture
def queue() -> RecordingQueue:
    return RecordingQueue()


def _test_redis_url() -> str:
    """Database 15 of the configured Redis, flushed per test (dev data lives in db 0)."""
    base = Settings().REDIS_URL.rsplit("/", 1)[0]
    return os.getenv("TEST_REDIS_URL", f"{base}/15")


GENEROUS = "10000/60"


@pytest.fixture
def test_settings(test_db_url: str) -> Settings:
    # Never inherit real credentials from a developer's .env: tests must not depend on them.
    # Rate limits are generous here; tests of the limits themselves lower them.
    return Settings(
        ENV="test",
        DATABASE_URL=test_db_url,
        REDIS_URL=_test_redis_url(),
        ANALYTICS_MIN_POSTINGS=30,
        ADZUNA_APP_ID="",
        ADZUNA_APP_KEY=SecretStr(""),
        JWT_SECRET=SecretStr("test-secret-" + "x" * 40),
        RATE_LIMIT_LOGIN=GENEROUS,
        RATE_LIMIT_LOGIN_IP=GENEROUS,
        RATE_LIMIT_REGISTER=GENEROUS,
        RATE_LIMIT_REFRESH=GENEROUS,
        RATE_LIMIT_EXPENSIVE=GENEROUS,
        RATE_LIMIT_PUBLIC=GENEROUS,
    )


@pytest.fixture
async def api(
    factory: async_sessionmaker[AsyncSession], test_settings: Settings, queue: RecordingQueue
) -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app(test_settings)
    async with app.router.lifespan_context(app):
        app.state.task_queue = queue
        await app.state.redis.flushdb()
        transport = ASGITransport(app=app)
        # https, so Secure cookies are stored and sent as a browser would.
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            yield client


@dataclass
class Account:
    id: uuid.UUID
    email: str
    password: str
    role: str
    headers: dict[str, str]


PASSWORD = "correct horse battery staple"


@pytest.fixture
def make_user(
    factory: async_sessionmaker[AsyncSession], test_settings: Settings
) -> Callable[..., Awaitable[Account]]:
    """Create an account directly (test fixture data) and return it with a Bearer header."""
    from app.services.auth.service import create_user
    from app.services.auth.tokens import create_access_token

    counter = iter(range(1, 10_000))

    async def make(role: str = "student", email: str | None = None) -> Account:
        address = email or f"{role}{next(counter)}@example.test"
        async with factory() as session:
            user = await create_user(session, address, PASSWORD, role=role)
            await session.commit()
        token = create_access_token(user.id, user.role, test_settings).token
        return Account(user.id, address, PASSWORD, role, {"Authorization": f"Bearer {token}"})

    return make
