# CLAUDE.md

Guidance for Claude (and any contributor) working on SkillRadar AI 2.0.

## Source of truth

[ROADMAP.md](ROADMAP.md) is the single source of truth for project progress: which phase is
active, what each phase must deliver and when it counts as complete. Read it at the start of
every session before doing any work. Architecture decisions live in
[docs/decisions.md](docs/decisions.md); the frozen v1 app and its known bugs are described in
[legacy/NOTICE.md](legacy/NOTICE.md).

## Rules

1. **Never skip a phase.** Work only on the current phase in ROADMAP.md. Phases run in order.
2. **Never mark a phase complete without meeting its completion criteria.** Every checkbox in
   the phase must be checked, with evidence, and the phase gate checklist must pass.
3. **Run tests before completing each phase**: lint, type checks, unit and integration tests,
   and the Docker stack, as listed in the phase gate checklist.
4. **Update ROADMAP.md whenever progress changes**: tick criteria as they are met, update the
   status table, and add a change-log entry. Record every measured number (data volumes,
   model scores, test counts, API size) in [docs/metrics.md](docs/metrics.md) with its date
   and source, phase by phase. Only measured values go there, never estimates.
5. **Ask the project owner for approval before starting each major phase.** Present the phase
   scope from ROADMAP.md and wait for an explicit yes.
6. **Preserve existing functionality.** Do not remove or break anything that works, including
   v1 features, without a written reason recorded in ROADMAP.md or docs/decisions.md and the
   owner's agreement.

Also from the project brief: never present mock data as real data, never hardcode analytics or
dashboard metrics, and never commit API keys or credentials. See "Standards that apply to every
phase" in ROADMAP.md.

## Repository layout

```
apps/api/      FastAPI backend + Celery workers (Python 3.12)
apps/web/      Next.js frontend (Phase 6)
packages/ml/   Shared ML code (when introduced)
docs/          Decisions, schema, security and API docs
legacy/        Frozen v1 — reference only; do not modify, do not import from it
```

## Commands

Run from `apps/api` with the virtualenv active (`.venv/Scripts/activate` on Windows).

```bash
ruff check . && ruff format --check .   # lint and format
mypy app                                # types (strict)
pytest                                  # unit tests
RUN_INTEGRATION=1 pytest                # + integration tests (needs Postgres and Redis)
alembic upgrade head                    # apply migrations
```

Full stack from the repo root: `docker compose up --build` (copy `.env.example` to `.env` first).

## Conventions

- Schema changes only through Alembic migrations, each with a working downgrade.
- Errors use the standard shape `{"error": {"code", "message", "request_id", "details"?}}`;
  raise `AppError` subclasses from services.
- No side effects at import time; resources are created in the app lifespan.
- External APIs (job sources, Claude) are mocked in tests, never called.
- Commit only when asked; end commit messages with the attribution line in use for this repo.
