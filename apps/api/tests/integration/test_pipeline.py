"""End-to-end Phase 1 pipeline against real Postgres: ingestion (mocked Adzuna), dedup,
extraction, demand, curriculum upload/parse, gap and recommendations."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.models import (
    Course,
    CourseUnit,
    CurriculumDocument,
    IngestionRun,
    JobPosting,
    PostingSkill,
    SkillDemandMonthly,
)
from app.services.analytics.demand import refresh_monthly_demand
from app.services.curriculum.service import parse_document
from app.services.extraction.service import extract_pending
from app.services.ingestion.base import RawPosting
from app.services.ingestion.runner import create_run, execute_run, get_or_create_source
from app.workers.tasks import ingest_and_process
from tests.adzuna_fixtures import adzuna_page, adzuna_result
from tests.integration.conftest import RecordingQueue
from tests.pdfs import LAYOUT_ONLY, V1_STYLE, make_pdf

pytestmark = pytest.mark.integration
Factory = async_sessionmaker[AsyncSession]
ADZUNA = "https://api.adzuna.test/v1/api"


class ListConnector:
    """Feeds fixed postings into the real runner (test fixture data only)."""

    key = "list"

    def __init__(self, postings: list[RawPosting]) -> None:
        self.postings = postings

    async def fetch(self, params: dict[str, Any]) -> AsyncIterator[RawPosting]:
        for p in self.postings:
            yield p


def posting(i: int, desc: str, title: str = "Data Engineer", month: int = 10) -> RawPosting:
    return RawPosting(
        external_id=f"t{i}",
        title=title,
        # Unique text per posting: identical text would be (correctly) deduplicated.
        description=f"{desc} (ref {i})",
        posted_at=datetime(2026, month, 5 + i % 20, tzinfo=UTC),
        company="Fixture Co",
        location="Pune",
    )


async def load(
    factory: Factory, postings: list[RawPosting], *, key: str = "fixture", synthetic: bool = False
) -> None:
    async with factory() as s:
        source = await get_or_create_source(
            s, key, kind="file", is_synthetic=synthetic, licence="test fixture"
        )
        run = await create_run(s, source, {})
        await s.commit()
        run_id = run.id
    await execute_run(factory, run_id, ListConnector(postings))
    await extract_pending(factory)
    async with factory() as s:
        await refresh_monthly_demand(s)
        await s.commit()


async def count(factory: Factory, model: Any) -> int:
    async with factory() as s:
        return int(await s.scalar(select(func.count()).select_from(model)) or 0)


@pytest.fixture
def adzuna_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADZUNA_APP_ID", "test-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-key")
    monkeypatch.setenv("ADZUNA_BASE_URL", ADZUNA)
    monkeypatch.setenv("ADZUNA_MIN_SECONDS_BETWEEN_CALLS", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---- ingestion --------------------------------------------------------------------------


@respx.mock
async def test_adzuna_ingestion_end_to_end_and_idempotent(
    factory: Factory, adzuna_env: None
) -> None:
    page1 = adzuna_page([adzuna_result(i) for i in range(50)])
    page2 = adzuna_page([adzuna_result(100 + i) for i in range(10)])
    respx.get(f"{ADZUNA}/jobs/in/search/1").mock(return_value=httpx.Response(200, json=page1))
    respx.get(f"{ADZUNA}/jobs/in/search/2").mock(return_value=httpx.Response(200, json=page2))

    async def run_once() -> tuple[int, dict[str, Any]]:
        async with factory() as s:
            source = await get_or_create_source(s, "adzuna")
            run = await create_run(s, source, {"country": "in", "pages": 2})
            await s.commit()
            run_id = run.id
        return run_id, await ingest_and_process(factory, run_id)

    run_id, result = await run_once()
    assert result["inserted"] == 60 and result["duplicates"] == 0 and result["errors"] == 0
    assert result["extracted"] == 60
    async with factory() as s:
        run = await s.get(IngestionRun, run_id)
        assert run is not None
        assert (run.status, run.fetched, run.inserted) == ("succeeded", 60, 60)
        p = await s.scalar(select(JobPosting).where(JobPosting.external_id == "4000000001"))
        assert p is not None
        assert p.title == "Data Engineer 1"  # <strong> highlight removed
        assert p.location == "Bengaluru"
        assert p.extraction_status == "done"
        assert p.salary_is_estimated is True
        skills = {
            row[0]: row[1]
            for row in (
                await s.execute(
                    select(PostingSkill.skill_id, PostingSkill.requirement).where(
                        PostingSkill.posting_id == p.id
                    )
                )
            ).all()
        }
    assert len(skills) >= 4  # python, sql, spark, airflow
    assert await count(factory, SkillDemandMonthly) > 0

    # Re-running the same fetch inserts nothing and counts duplicates.
    run_id2, result2 = await run_once()
    assert result2["inserted"] == 0 and result2["duplicates"] == 60
    assert await count(factory, JobPosting) == 60
    async with factory() as s:
        run2 = await s.get(IngestionRun, run_id2)
        assert run2 is not None and run2.status == "succeeded" and run2.duplicates == 60


@respx.mock
async def test_adzuna_auth_failure_marks_run_failed(factory: Factory, adzuna_env: None) -> None:
    respx.get(f"{ADZUNA}/jobs/in/search/1").mock(return_value=httpx.Response(401))
    async with factory() as s:
        run = await create_run(s, await get_or_create_source(s, "adzuna"), {"pages": 1})
        await s.commit()
        run_id = run.id
    await ingest_and_process(factory, run_id)
    async with factory() as s:
        run = await s.get(IngestionRun, run_id)
        assert run is not None and run.status == "failed"
        assert "test-key" not in " ".join(run.error_samples)


async def test_cross_source_duplicate_content_is_skipped(factory: Factory) -> None:
    await load(factory, [posting(1, "Python and SQL")], key="a")
    await load(factory, [posting(1, "Python and SQL")], key="b")
    assert await count(factory, JobPosting) == 1


async def test_synthetic_sources_are_excluded_from_analytics(
    factory: Factory, api: AsyncClient
) -> None:
    await load(factory, [posting(1, "Python")], key="real")
    await load(
        factory,
        [posting(i, "Python and Rust programming") for i in range(2, 6)],
        key="synthetic-demo",
        synthetic=True,
    )
    jobs = (await api.get("/api/v1/jobs")).json()
    assert jobs["total"] == 1
    assert (await api.get("/api/v1/jobs?include_synthetic=true")).json()["total"] == 5
    demand = (await api.get("/api/v1/skills/demand")).json()
    assert demand["total_postings"] == 1
    assert {i["skill"]["slug"] for i in demand["items"]} == {"python"}


async def test_demand_changes_with_data(factory: Factory, api: AsyncClient) -> None:
    """No hardcoded metrics: numbers come from stored postings and move when they change."""
    await load(factory, [posting(1, "Python"), posting(2, "Java")])
    first = (await api.get("/api/v1/skills/demand")).json()
    await load(factory, [posting(3, "Python"), posting(4, "Python")], key="more")
    second = (await api.get("/api/v1/skills/demand")).json()
    share = lambda d: next(i["share"] for i in d["items"] if i["skill"]["slug"] == "python")  # noqa: E731
    assert (first["total_postings"], share(first)) == (2, 0.5)
    assert (second["total_postings"], share(second)) == (4, 0.75)


# ---- curriculum -------------------------------------------------------------------------


async def make_program(api: AsyncClient) -> int:
    uni = await api.post("/api/v1/universities", json={"name": "Test University", "country": "in"})
    assert uni.status_code == 201, uni.text
    prog = await api.post(
        "/api/v1/programs",
        json={"university_id": uni.json()["id"], "name": "B.Tech CSE", "degree": "B.Tech"},
    )
    assert prog.status_code == 201, prog.text
    return int(prog.json()["id"])


async def upload(
    api: AsyncClient, program_id: int, data: bytes, name: str = "s.pdf"
) -> httpx.Response:
    return await api.post(
        f"/api/v1/programs/{program_id}/curriculum",
        files={"file": (name, data, "application/pdf")},
    )


async def test_curriculum_upload_parse_and_no_duplicates(
    factory: Factory, api: AsyncClient, queue: RecordingQueue, test_settings: Settings
) -> None:
    program_id = await make_program(api)
    pdf = make_pdf(V1_STYLE)

    r = await upload(api, program_id, pdf)
    assert r.status_code == 202, r.text
    doc_id = r.json()["document"]["id"]
    assert queue.sent == [("curriculum.parse_document", (doc_id,))]
    doc = await parse_document(factory, doc_id, test_settings)
    assert (doc.status, doc.parser_strategy, doc.units_parsed) == ("parsed", "regex", 3)

    cur = (await api.get(f"/api/v1/programs/{program_id}/curriculum")).json()
    assert [c["title"] for c in cur["courses"]] == ["Advanced Data Engineering", "Machine Learning"]
    unit1 = cur["courses"][0]["units"][0]
    covered = {s["skill"]["slug"]: s["coverage"] for s in unit1["skills"]}
    assert covered["sql"] == 0.5 and covered["postgresql"] == 0.5

    # Same file again: 200, same document, nothing new queued, no new rows.
    again = await upload(api, program_id, pdf)
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["document"]["id"] == doc_id
    assert len(queue.sent) == 1
    assert await count(factory, CurriculumDocument) == 1
    assert await count(factory, CourseUnit) == 3

    # A new version replaces the curriculum instead of adding to it.
    r2 = await upload(api, program_id, make_pdf(LAYOUT_ONLY), "v2.pdf")
    assert r2.status_code == 202
    await parse_document(factory, r2.json()["document"]["id"], test_settings)
    assert await count(factory, Course) == 2
    assert await count(factory, CourseUnit) == 3
    docs = (await api.get(f"/api/v1/programs/{program_id}/curriculum/documents")).json()
    assert sorted(d["status"] for d in docs) == ["parsed", "superseded"]

    # Re-uploading the old version makes it current again (re-parse queued).
    back = await upload(api, program_id, pdf)
    assert back.status_code == 200 and back.json()["queued"] is True


async def test_curriculum_rejects_bad_uploads(api: AsyncClient, test_settings: Settings) -> None:
    program_id = await make_program(api)
    r = await upload(api, program_id, b"MZ\x90\x00 not a pdf", "evil.pdf")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_upload"
    big = b"%PDF-" + b"0" * test_settings.CURRICULUM_MAX_BYTES
    r = await upload(api, program_id, big)
    assert r.status_code == 413
    assert (await upload(api, 9999, make_pdf(V1_STYLE))).status_code == 404


async def test_failed_parse_is_recorded(
    factory: Factory, api: AsyncClient, test_settings: Settings
) -> None:
    program_id = await make_program(api)
    r = await upload(api, program_id, make_pdf([("Just a paragraph.", 10, False)]))
    doc = await parse_document(factory, r.json()["document"]["id"], test_settings)
    assert doc.status == "failed" and doc.error and "Could not find course units" in doc.error
    assert await count(factory, Course) == 0


# ---- gap and recommendations ------------------------------------------------------------


async def test_gap_matches_hand_computed_values(
    factory: Factory, api: AsyncClient, test_settings: Settings
) -> None:
    """4 postings (Oct 2026): python in 3, sql/kafka/docker in 1 each.
    Curriculum (V1_STYLE): sql 0.5 (one content mention), python 0.5, kafka 0, docker 0.
        shares: python 0.75, sql 0.25, kafka 0.25, docker 0.25
        gaps:   python 0.375, kafka 0.25, docker 0.25, sql 0.125
        weighted coverage = (0.75*0.5 + 0.25*0.5) / 1.5 = 0.3333
    """
    await load(
        factory,
        [
            posting(1, "Python, SQL"),
            posting(2, "Python, Kafka"),
            posting(3, "Python"),
            posting(4, "Docker"),
        ],
    )
    program_id = await make_program(api)
    r = await upload(api, program_id, make_pdf(V1_STYLE))
    await parse_document(factory, r.json()["document"]["id"], test_settings)

    gap = (await api.get(f"/api/v1/gap?program_id={program_id}&role=data-engineer")).json()
    rows = {s["skill"]["slug"]: s for s in gap["skills"]}
    assert set(rows) == {"python", "sql", "kafka", "docker"}
    assert [s["skill"]["slug"] for s in gap["skills"]][:1] == ["python"]
    assert rows["python"]["demand_share"] == 0.75 and rows["python"]["coverage"] == 0.5
    assert rows["python"]["gap"] == 0.375
    assert rows["sql"]["gap"] == 0.125
    assert rows["kafka"]["gap"] == 0.25 and rows["kafka"]["coverage"] == 0.0
    assert gap["summary"]["weighted_coverage"] == pytest.approx(0.3333, abs=1e-4)
    assert gap["summary"]["total_postings"] == 4
    assert gap["low_sample"] is True  # 4 < ANALYTICS_MIN_POSTINGS
    assert gap["window"]["start"] == "2026-05-01" and gap["window"]["end_exclusive"] == "2026-11-01"
    assert rows["sql"]["covered_in"][0]["course"] == "Advanced Data Engineering"

    stored = (await api.get(f"/api/v1/gap/reports/{gap['id']}")).json()
    assert stored["summary"] == gap["summary"]

    recs = (
        await api.get(f"/api/v1/recommendations?role=data-engineer&program_id={program_id}")
    ).json()
    items = {i["skill"]["slug"]: i for i in recs["items"]}
    assert recs["role_postings"] == 4 and recs["low_sample"] is True
    assert items["kafka"]["priority"] == "insufficient_data"
    assert items["kafka"]["coverage_status"] == "missing"
    assert items["spark"]["learning"]["content_source"] == "editorial:v1"
    assert "role_core_skill" in items["spark"]["reason"]


async def test_recommendation_priority_uses_demand_share(
    factory: Factory, api: AsyncClient, test_settings: Settings
) -> None:
    descs = ["Python and Kafka"] * 12 + ["Python"] * 20 + ["Python and Airflow"] * 4
    await load(factory, [posting(i, d) for i, d in enumerate(descs)])
    recs = (await api.get("/api/v1/recommendations?role=data-engineer")).json()
    items = {i["skill"]["slug"]: i for i in recs["items"]}
    assert recs["role_postings"] == 36 and recs["low_sample"] is False
    assert items["python"]["priority"] == "high"  # 36/36
    assert items["kafka"]["priority"] == "high"  # 12/36 = 0.33
    assert items["airflow"]["priority"] == "medium"  # 4/36 = 0.11
    assert items["snowflake"]["priority"] == "low"  # 0/36
    assert items["python"]["coverage"] is None  # no program given


# ---- endpoints: pagination and filters ---------------------------------------------------


async def test_jobs_endpoint_pagination_and_filters(factory: Factory, api: AsyncClient) -> None:
    await load(
        factory,
        [
            posting(1, "Requirements: Python. Kafka is a plus.", "Data Engineer"),
            posting(2, "Java and Spring Boot", "Java Developer"),
            posting(3, "Docker, Kubernetes", "DevOps Engineer", month=9),
        ],
    )
    page = (await api.get("/api/v1/jobs?limit=2&offset=0")).json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["limit"] == 2
    assert page["items"][0]["posted_at"] >= page["items"][1]["posted_at"]
    rest = (await api.get("/api/v1/jobs?limit=2&offset=2")).json()
    assert len(rest["items"]) == 1

    async def ids(q: str) -> list[str]:
        return [j["title"] for j in (await api.get(f"/api/v1/jobs?{q}")).json()["items"]]

    assert await ids("skill=python") == ["Data Engineer"]
    assert await ids("skill=kafka&requirement=nice_to_have") == ["Data Engineer"]
    assert await ids("skill=kafka&requirement=required") == []
    assert await ids("role=devops-engineer") == ["DevOps Engineer"]
    assert await ids("q=java") == ["Java Developer"]
    assert await ids("q=%25") == []  # wildcard is matched literally
    assert await ids("location=pune") != []
    assert await ids("posted_to=2026-09-30") == ["DevOps Engineer"]
    assert (await api.get("/api/v1/jobs?limit=1000")).status_code == 422

    job_id = page["items"][0]["id"]
    detail = (await api.get(f"/api/v1/jobs/{job_id}")).json()
    assert detail["description"] and detail["extractor_version"].startswith("2.0+")
    ev = detail["skills"][0]["evidence"][0]
    assert {"field", "start", "end", "text", "rule"} <= set(ev)
    missing = await api.get("/api/v1/jobs/999999")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


async def test_taxonomy_and_trend_endpoints(factory: Factory, api: AsyncClient) -> None:
    await load(
        factory,
        [
            posting(1, "Python", month=9),
            posting(2, "Python and SQL", month=10),
            posting(3, "SQL", month=10),
        ],
    )
    skills = (await api.get("/api/v1/skills?q=postgres")).json()
    assert [s["slug"] for s in skills["items"]] == ["postgresql"]
    assert skills["items"][0]["parent"]["slug"] == "sql"
    assert (await api.get("/api/v1/skills?category=cloud&limit=2")).json()["total"] >= 3
    detail = (await api.get("/api/v1/skills/react")).json()
    assert any(a["requires_context"] for a in detail["aliases"])
    assert (await api.get("/api/v1/skills/nope")).status_code == 404

    roles = (await api.get("/api/v1/roles")).json()
    de = next(r for r in roles if r["slug"] == "data-engineer")
    assert [s["slug"] for s in de["core_skills"]][:2] == ["python", "sql"]

    trend = (await api.get("/api/v1/trends/skills/python")).json()
    assert [(p["month"], p["share"]) for p in trend["series"]] == [
        ("2026-09-01", 1.0),
        ("2026-10-01", 0.5),
    ]
    assert trend["series"][1]["change_pp"] == -0.5

    movers = (await api.get("/api/v1/trends/movers")).json()
    assert movers["current_month"] == "2026-10-01"
    assert movers["low_sample"] is True and movers["growing"] == []

    demand = (await api.get("/api/v1/skills/demand?limit=1&offset=1")).json()
    assert demand["total"] == 2 and len(demand["items"]) == 1


async def test_movers_with_enough_postings(factory: Factory, api: AsyncClient) -> None:
    sep = [posting(i, "Java", month=9) for i in range(30)]
    octo = [posting(100 + i, "Python" if i < 15 else "Java", month=10) for i in range(30)]
    await load(factory, sep + octo)
    m = (await api.get("/api/v1/trends/movers")).json()
    assert m["low_sample"] is False
    assert m["growing"][0]["skill"]["slug"] == "python"
    assert m["growing"][0]["change_pp"] == 0.5
    assert m["declining"][0]["skill"]["slug"] == "java"
    assert m["emerging"][0]["skill"]["slug"] == "python"


async def test_ingestion_endpoints(api: AsyncClient, queue: RecordingQueue) -> None:
    sources = (await api.get("/api/v1/sources")).json()
    assert [s["key"] for s in sources] == ["adzuna"]
    r = await api.post("/api/v1/ingestion/runs", json={"source": "adzuna"})
    if os.getenv("ADZUNA_APP_ID"):
        pytest.skip("a real Adzuna key is configured in this environment")
    assert r.status_code == 503 and r.json()["error"]["code"] == "service_unavailable"
    assert queue.sent == []
    assert (await api.get("/api/v1/ingestion/runs")).json()["total"] == 0
    assert (await api.get("/api/v1/ingestion/runs/1")).status_code == 404


async def test_ingestion_trigger_queues_a_run(
    factory: Factory, test_settings: Settings, queue: RecordingQueue
) -> None:
    from httpx import ASGITransport

    from app.main import create_app

    settings = test_settings.model_copy(
        update={
            "ADZUNA_APP_ID": "id",
            "ADZUNA_APP_KEY": test_settings.ADZUNA_APP_KEY.__class__("k"),
        }
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.task_queue = queue
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post(
                "/api/v1/ingestion/runs",
                json={"source": "adzuna", "params": {"what": "python", "pages": 2}},
            )
            assert r.status_code == 202, r.text
            run = r.json()
            assert run["status"] == "queued" and run["params"] == {
                "country": "in",
                "pages": 2,
                "what": "python",
            }
            assert queue.sent == [("ingestion.run", (run["id"],))]
            bad = await c.post("/api/v1/ingestion/runs", json={"params": {"country": "zz"}})
            assert bad.status_code == 400
            listed = (await c.get("/api/v1/ingestion/runs")).json()
            assert listed["total"] == 1 and listed["items"][0]["source"]["key"] == "adzuna"


async def test_seed_is_idempotent(factory: Factory) -> None:
    from app.models import Skill, SkillAlias
    from app.seed.loader import seed_reference_data

    before = (await count(factory, Skill), await count(factory, SkillAlias))
    async with factory() as s:
        await seed_reference_data(s)
        await s.commit()
    assert (await count(factory, Skill), await count(factory, SkillAlias)) == before


async def test_export_and_facets(factory: Factory, api: AsyncClient) -> None:
    await load(
        factory,
        [
            posting(1, "Requirements: Python. Kafka is a plus.", "Data Engineer"),
            posting(2, "Docker, Kubernetes", "DevOps Engineer", month=9),
            posting(3, "Sales targets", "Sales Executive"),
        ],
    )
    r = await api.get("/api/v1/jobs/export?role=data-engineer")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("id,title,company")
    assert len(lines) == 2
    assert "Python" in lines[1] and "Kafka" in lines[1]

    f = (await api.get("/api/v1/jobs/facets")).json()
    assert f["total"] == 3
    assert {b["key"]: b["count"] for b in f["by_role"]} == {
        "data-engineer": 1,
        "devops-engineer": 1,
        None: 1,
    }
    assert f["by_source"] == [{"key": "fixture", "count": 3}]
    assert [b["key"] for b in f["by_month"]] == ["2026-09", "2026-10"]
    assert f["by_location"] == [{"key": "Pune", "count": 3}]


async def test_gap_by_role(factory: Factory, api: AsyncClient, test_settings: Settings) -> None:
    await load(factory, [posting(1, "Python and SQL"), posting(2, "Docker", "DevOps Engineer")])
    program_id = await make_program(api)
    r = await upload(api, program_id, make_pdf(V1_STYLE))
    await parse_document(factory, r.json()["document"]["id"], test_settings)
    data = (await api.get(f"/api/v1/gap/by-role?program_id={program_id}")).json()
    roles = {x["role"]["slug"]: x for x in data["roles"]}
    assert data["has_curriculum"] is True
    # Data Engineer: python 1/1 (cov 0.5), sql 1/1 (cov 0.5) -> weighted coverage 0.5
    assert roles["data-engineer"]["postings"] == 1
    assert roles["data-engineer"]["weighted_coverage"] == 0.5
    # DevOps: docker 1/1, not taught -> 0
    assert roles["devops-engineer"]["weighted_coverage"] == 0.0
    # No postings for the role -> no number rather than a made-up one
    assert roles["qa-engineer"]["postings"] == 0
    assert roles["qa-engineer"]["weighted_coverage"] is None
