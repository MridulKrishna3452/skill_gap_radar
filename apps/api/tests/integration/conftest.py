"""Integration fixtures: a dedicated test database, migrated once, truncated and re-seeded per
test. The database is DATABASE_URL's database name + "_test" (or TEST_DATABASE_URL), so dev
data is never touched."""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
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


@pytest.fixture
def test_settings(test_db_url: str) -> Settings:
    # Never inherit real credentials from a developer's .env: tests must not depend on them.
    return Settings(
        ENV="test",
        DATABASE_URL=test_db_url,
        ANALYTICS_MIN_POSTINGS=30,
        ADZUNA_APP_ID="",
        ADZUNA_APP_KEY=SecretStr(""),
    )


@pytest.fixture
async def api(
    factory: async_sessionmaker[AsyncSession], test_settings: Settings, queue: RecordingQueue
) -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app(test_settings)
    async with app.router.lifespan_context(app):
        app.state.task_queue = queue
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
