# SkillRadar AI 2.0

Career intelligence and skill gap analysis platform: real job-market data, NLP skill
extraction, curriculum intelligence, resume analysis, semantic job matching, personalised
roadmaps, demand forecasting and a RAG career assistant.

> Status: **Phase 1 (v1 functionality on real data) in progress**. The v1 Dash/SQLite app is frozen in [`legacy/`](legacy/NOTICE.md).
> Progress and phase plan: [`ROADMAP.md`](ROADMAP.md) · Architecture decisions: [`docs/decisions.md`](docs/decisions.md).

## Repository layout

```
apps/api/        FastAPI backend + Celery workers (Python 3.12)
apps/web/        Next.js frontend (Phase 6)
packages/ml/     Shared ML package (when introduced)
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

## Loading real data (Phase 1)

Reference data (skills taxonomy, roles, sources) is loaded automatically by the `migrate`
service, or by hand with `python -m app.cli seed`. Run commands from `apps/api`
(`python -m app.cli --help` lists them all):

```bash
# Job postings from Adzuna: set ADZUNA_APP_ID / ADZUNA_APP_KEY in .env first
python -m app.cli ingest-adzuna --country in --what "software developer" --pages 5
#   or through the API: POST /api/v1/ingestion/runs (runs in the worker)

# A licensed dataset (CSV / JSON / JSONL), with a column map if needed
python -m app.cli import-file --path jobs.csv --source my-dataset --name "My dataset" \
    --licence "CC BY 4.0, https://..." --map title=job_title posted_at=date

# A real syllabus PDF: create a university and program via the API, then upload
#   POST /api/v1/programs/{id}/curriculum   (parsed in the worker)
python -m app.cli parse-curriculum --program-id 1 --path syllabus.pdf   # or synchronously
```

Analytics (demand, trends, gap, recommendations) only count non-synthetic sources and flag
results computed from fewer than `ANALYTICS_MIN_POSTINGS` postings. Extraction quality is
measured on a hand-labelled set: see [`data/eval_sets/README.md`](data/eval_sets/README.md).
Docs: [`docs/schema.md`](docs/schema.md), [`docs/v1-parity.md`](docs/v1-parity.md).

## Accounts (Phase 2)

Writes and personal data need an account. Create the first admin from `apps/api` (the
password is read from a prompt, or from stdin with `--password-stdin`):

```bash
python -m app.cli create-user --email you@example.com --role admin
```

Then sign in with `POST /api/v1/auth/login` and send the returned `access_token` as
`Authorization: Bearer <token>`. Students register with `POST /api/v1/auth/register`.
Faculty accounts are created by an admin (`POST /api/v1/admin/users`) and assigned to programs.
Roles, tokens, rate limits and the full access table: [`docs/security.md`](docs/security.md).

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
