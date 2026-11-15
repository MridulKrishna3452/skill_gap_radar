# SkillRadar AI 2.0

Career intelligence and skill gap analysis platform: real job-market data, NLP skill
extraction, curriculum intelligence, resume analysis, semantic job matching, personalised
roadmaps, demand forecasting and a RAG career assistant.

> Status: **Phase 0 (foundation)**. The v1 Dash/SQLite app is frozen in [`legacy/`](legacy/NOTICE.md).
> Architecture decisions: [`docs/decisions.md`](docs/decisions.md).

## Repository layout

```
apps/api/        FastAPI backend + Celery workers (Python 3.12)
apps/web/        Next.js frontend (from Phase 4)
packages/ml/     Shared ML package (from Phase 2)
docs/            Architecture decisions, API and schema docs
legacy/          Frozen v1, reference only
```

## Run the stack (Docker)

```bash
cp .env.example .env          # then edit the placeholder password
docker compose up --build
```

- API docs: http://localhost:8000/docs
- Readiness (checks Postgres + Redis): http://localhost:8000/api/v1/health/ready

## Backend development without Docker for the app

Postgres (with pgvector) and Redis still need to be running, e.g. `docker compose up db redis`.

```bash
cd apps/api
py -3.12 -m venv .venv            # or python3.12 -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.lock && pip install --no-deps -e .
alembic upgrade head
uvicorn app.main:app --reload
```

## Checks

```bash
cd apps/api
ruff check . && ruff format --check . && mypy app
pytest                         # unit tests
RUN_INTEGRATION=1 pytest       # + integration tests against real Postgres/Redis
```

CI (GitHub Actions) runs all of the above, a migration up/down/up round trip, a Docker build and
a secret scan on every push and pull request.

## Dependencies

`pyproject.toml` declares version ranges; `requirements.lock` (runtime, used by the Docker image)
and `requirements-dev.lock` (runtime + tooling, used by CI) pin exact versions. To update:
reinstall in a fresh venv and re-run `pip freeze --exclude skillradar-api` into each file.
