# SkillRadar AI 2.0 — Development Roadmap

**This file is the single source of truth for project progress.** Update it whenever progress
changes. A phase is complete only when every item in its *Completion criteria* is checked and
its tests pass. See [CLAUDE.md](CLAUDE.md) for the working rules.

Architecture decisions (data sources, LLM, auth, infrastructure): [docs/decisions.md](docs/decisions.md).

## Status

| Phase | Name | Status | Depends on |
|---|---|---|---|
| 0 | Infrastructure and project setup | 🟡 In progress — awaiting Docker verification | — |
| 1 | Stabilize existing V1 functionality | ⚪ Not started | 0 |
| 2 | Authentication and student profiles | ⚪ Not started | 0, 1 |
| 3 | Resume intelligence and semantic job matching | ⚪ Not started | 1, 2 |
| 4 | Personalized learning roadmaps | ⚪ Not started | 1, 2, 3 |
| 5 | Demand forecasting and RAG career assistant | ⚪ Not started | 1, 3, 4 |
| 6 | Next.js frontend and complete integration | ⚪ Not started | 2, 3, 4, 5 |
| 7 | Testing, security and deployment | ⚪ Not started | 0–6 |

Legend: ⚪ Not started · 🔵 Approved, not started · 🟡 In progress · ✅ Complete

Phases run strictly in order. Each phase starts only after the previous one is ✅ and the
project owner has approved starting it.

## Standards that apply to every phase

- **No mock data as real data.** Synthetic records exist only in test fixtures, or in sources
  flagged `is_synthetic`, which analytics exclude by default.
- **No hardcoded metrics.** Every number shown to a user is computed from stored data by a
  backend query, and an automated test proves it changes when the data changes.
- **Every feature works end to end.** Nothing is merged as a stub, a placeholder button or a
  "coming soon" path that looks functional.
- **Errors and validation.** Inputs are validated with Pydantic; errors use the standard error
  shape; failures are logged with the request ID and never leak internals.
- **Tests.** New code ships with unit tests; anything touching the DB, Redis, files or external
  APIs also gets integration tests. External APIs are mocked in tests, never called.
- **Schema changes only via Alembic migrations**, each with a working downgrade.
- **Documentation.** New endpoints appear in OpenAPI with descriptions and examples; schema
  changes are reflected in `docs/schema.md`.
- **Secrets** come from the environment only; nothing secret is committed.
- **Preserve functionality.** Nothing that works is removed without a written reason in this
  file or in `docs/decisions.md`.

## Phase gate checklist (run before marking any phase ✅)

1. All completion criteria for the phase are checked, with evidence (test names, commands, URLs).
2. `ruff check .`, `ruff format --check .` and `mypy app` pass in `apps/api`.
3. `pytest` passes, including `RUN_INTEGRATION=1 pytest` against real Postgres and Redis.
4. CI is green on the commit that closes the phase.
5. `docker compose up --build` starts cleanly and `/api/v1/health/ready` returns 200.
6. This file is updated: status table, checked criteria, completion date, notes.

---

## Phase 0 — Infrastructure and project setup

**Objective.** A clean, reproducible foundation that every later phase builds on: monorepo,
local stack, database migrations, background workers and CI.

**Features**
- Monorepo layout (`apps/api`, later `apps/web` and `packages/ml`); v1 frozen in `legacy/`.
- FastAPI app factory: validated settings, standard error shape, request-ID and
  security-header middleware, liveness and readiness probes.
- Async SQLAlchemy, Alembic, Postgres extensions `vector` and `pg_trgm`.
- Celery worker on Redis.
- Docker Compose stack: `db` (pgvector), `redis`, `migrate`, `api`, `worker`.
- GitHub Actions: lint, types, migration round trip, tests with service containers, Docker
  build, secret scan.

**Dependencies.** None.

**Deliverables.** `apps/api` skeleton, `docker-compose.yml`, `.env.example`,
`.github/workflows/ci.yml`, `README.md`, `docs/decisions.md`, `legacy/NOTICE.md`.

**Testing requirements**
- Unit tests: health probes (ok, dependency down, timeout), error shape, request ID, security
  headers, CORS allow-list, settings validation, worker ping.
- Integration tests: readiness against real services, extensions present, vector distance query.

**Completion criteria**
- [x] Git repository initialised; v1 preserved unchanged in `legacy/` with a notice.
- [x] FastAPI skeleton with config, logging, errors, middleware and health endpoints.
- [x] Alembic configured; migration `0001` enables `vector` and `pg_trgm`; offline SQL renders.
- [x] Celery app and `system.ping` task.
- [x] Dockerfile (multi-stage, non-root) and Compose stack.
- [x] CI workflow defined.
- [x] Ruff, mypy and unit tests pass locally (20 passed).
- [ ] `docker compose up --build` verified locally; `/api/v1/health/ready` returns 200.
- [ ] Integration tests pass (`RUN_INTEGRATION=1 pytest`) against the Compose services.
- [ ] Alembic upgrade → downgrade → upgrade verified against a real database.
- [ ] Worker processes `system.ping` from the running stack.
- [ ] CI run green on GitHub (requires a remote).

**Notes.** Initial commit `df10e63`. Local Docker daemon was not running during the build, so
the unchecked items still need verification.

---

## Phase 1 — Stabilize existing V1 functionality

**Objective.** Bring every v1 capability into the 2.0 backend, working correctly on real data:
ingestion, skill extraction, curriculum parsing, gap analysis, trends and recommendations. This
is where v1's bugs are fixed and its mock data is replaced, without losing any feature.

**Features**
- **Data model:** skills taxonomy (ESCO + curated tech subset, seeded from the v1 alias
  dictionary), job sources, ingestion runs, companies, job postings, posting skills, roles,
  universities, programs, courses, course units, unit skills, demand time series, gap reports.
- **Ingestion:** pluggable source framework; Adzuna API connector; CSV/JSON import for
  licensed datasets; tracked ingestion runs (fetched / inserted / duplicates / errors);
  content-hash dedup; idempotent re-runs. v1 normalizers ported with tests.
- **Skill extraction v2:** PhraseMatcher over the taxonomy, context disambiguation for
  ambiguous aliases (e.g. "react", "lambda", "go"), required vs nice-to-have detection,
  calibrated confidence, evidence spans. Runs as Celery tasks.
- **Curriculum:** upload real syllabus PDFs; per-unit parsing (v1 regex parser as one
  strategy, plus layout-aware fallback); unit-to-skill mapping; graded coverage 0–1; no
  duplicate rows on re-upload.
- **Gap analysis:** role-weighted gap from recent demand share, per program and role; fixes
  v1's biased coverage % (sorted by gap before taking the top 20).
- **Trends:** monthly skill demand share (not raw counts), month-over-month change.
- **Recommendations:** v1 role roadmaps and curated learning text preserved as labelled
  editorial content; priority driven by actual demand share, not fixed counts.
- **REST endpoints** for everything v1 exposed (`/jobs`, `/skills`, `/curriculum`, `/gap`,
  `/recommendations`), redesigned with pagination and filters under `/api/v1`.
- **Feature parity checklist** in `docs/v1-parity.md` mapping each v1 feature to its 2.0
  equivalent.

**Dependencies.** Phase 0. An Adzuna API key (owner) and at least one real syllabus PDF (owner).

**Deliverables.** Migrations for the core schema, ingestion workers, extraction module,
curriculum parser, gap/trend services, endpoints, `docs/schema.md`, `docs/v1-parity.md`,
labelled extraction evaluation set in `data/eval_sets/`.

**Testing requirements**
- Unit: normalizers (ported v1 tests), alias disambiguation, gap math with hand-computed
  expected values, coverage grading, trend share calculation.
- Integration: ingestion run end to end with a mocked Adzuna response; dedup on re-run;
  curriculum upload → parsed units → coverage; endpoints with pagination and filters.
- ML evaluation: extraction precision / recall / F1 on the labelled set, reported and gated in CI
  at a threshold agreed when the baseline is measured.
- Regression tests for each v1 bug listed in `legacy/NOTICE.md`.

**Completion criteria**
- [ ] Every v1 feature in `docs/v1-parity.md` has a working, tested 2.0 equivalent.
- [ ] At least one real data source ingests successfully; no synthetic records in analytics.
- [ ] Re-running ingestion or re-uploading a curriculum creates no duplicates.
- [ ] Extraction F1 measured on a labelled set of at least 100 postings and recorded here.
- [ ] Gap and coverage numbers verified against hand-computed fixtures.
- [ ] Each v1 bug in `legacy/NOTICE.md` has a regression test that passes.
- [ ] `docs/schema.md` documents all tables; endpoints documented in OpenAPI.
- [ ] Phase gate checklist passed.

---

## Phase 2 — Authentication and student profiles

**Objective.** Secure multi-user access with role-based permissions, and student profiles that
later phases personalise against.

**Features**
- Register, login, logout, refresh; argon2id password hashing; short-lived JWT access tokens;
  rotating refresh tokens stored hashed, sent as httpOnly Secure SameSite cookies; reuse
  detection revokes the token family.
- Roles: `student`, `faculty` (manages a program's curriculum), `admin`; permission
  dependencies on every protected route.
- Rate limiting (Redis) on auth and expensive endpoints; account lockout after repeated failures.
- Student profile: university, program, graduation year, target role, location preference.
- User skills inventory: self-declared skills with proficiency; source tracked.
- Protect Phase 1 endpoints: curriculum upload restricted to faculty/admin; ingestion triggers
  admin only.
- Account deletion endpoint that removes personal data.
- Audit log for admin and faculty actions.

**Dependencies.** Phases 0 and 1 (profiles reference programs, roles and skills).

**Deliverables.** Auth service and routes, users / refresh tokens / profiles / user skills /
audit log migrations, permission dependencies, `docs/security.md` (auth design).

**Testing requirements**
- Unit: password hashing, token creation and expiry, refresh rotation and reuse detection,
  permission checks per role.
- Integration: full register → login → refresh → logout flow; expired and tampered tokens
  rejected; every protected endpoint returns 401 without a token and 403 for the wrong role
  (a parametrised test over the route table); rate limit and lockout triggers.

**Completion criteria**
- [ ] All auth flows work end to end, including refresh rotation and reuse detection.
- [ ] Every non-public endpoint is covered by the 401/403 parametrised test.
- [ ] Profiles and user skills CRUD work with validation.
- [ ] No password, token or secret appears in logs (test asserts this).
- [ ] Account deletion removes the user's personal data.
- [ ] `docs/security.md` written.
- [ ] Phase gate checklist passed.

---

## Phase 3 — Resume intelligence and semantic job matching

**Objective.** Analyse a student's resume against the real market and match them to real jobs
with explainable scores.

**Features**
- Resume upload (PDF, DOCX): size and page limits, magic-byte check, private storage keyed by
  SHA-256, parsing in a worker with timeouts.
- Section segmentation; skill extraction with evidence spans; extracted skills merged into the
  user's skill inventory (with the user's confirmation).
- Rule-based ATS checks: contact details, standard sections, quantified bullet points, length.
- LLM feedback (Claude) grounded only in the extracted structure; all scores computed
  deterministically, never by the LLM.
- Embeddings: local sentence-transformers model (384-d) for postings and resumes; pgvector
  HNSW index.
- Matching: vector retrieval of top candidates, re-ranked by weighted required-skill overlap
  and seniority/location fit; per-match explanation of matched and missing skills.

**Dependencies.** Phase 1 (postings, taxonomy, extraction), Phase 2 (users, profiles).

**Deliverables.** Resume and matching services, embedding pipeline, endpoints
(`/resumes`, `/me/job-matches`, `/jobs/{id}/match`), labelled relevance set for matching.

**Testing requirements**
- Unit: upload validation (oversized, wrong type, renamed non-PDF), section parser, ATS rules,
  scoring formula.
- Integration: upload → parse → analysis end to end; matching returns ranked results with
  explanations; LLM client mocked, including its failure path.
- ML evaluation: matching nDCG@10 on the labelled relevance set, recorded and gated.

**Completion criteria**
- [ ] Malicious or oversized uploads are rejected; parsing never runs in the API process.
- [ ] Resume analysis works on at least 5 real (anonymised) resumes.
- [ ] Every match has an explanation built from stored data.
- [ ] Matching nDCG@10 measured and recorded here.
- [ ] LLM feedback degrades gracefully when the API is unavailable.
- [ ] Phase gate checklist passed.

---

## Phase 4 — Personalized learning roadmaps

**Objective.** Turn a student's gaps into an ordered, trackable learning plan.

**Features**
- Skill prerequisite graph: curated relations plus relations mined from skills that co-occur in
  postings, reviewed by an admin.
- Roadmap generation for a target role: missing skills from the student's inventory and
  resume versus role demand, prioritised by gap weight, ordered by prerequisites.
- Learning resources per skill (title, provider, URL, level, cost, estimated hours), including
  the curated v1 roadmap content.
- Progress tracking: item status, dates; roadmap recalculates when skills are added.
- Student-level gap report (complements the program-level gap from Phase 1).

**Dependencies.** Phase 1 (gap analysis, demand), Phase 2 (profiles, skills), Phase 3
(resume-derived skills).

**Deliverables.** Skill relations and resources schema, roadmap service, endpoints
(`/me/roadmaps`, `/roadmap-items/{id}`, `/gaps/me`), admin review for mined relations.

**Testing requirements**
- Unit: topological ordering (including cycle handling), priority calculation, recalculation
  when skills change.
- Integration: profile + resume → roadmap → mark items done → updated roadmap and gap.

**Completion criteria**
- [ ] Roadmap order always respects prerequisites (property-based or exhaustive test).
- [ ] Priorities change when market demand data changes (test proves it).
- [ ] Progress persists and updates the student's gap report.
- [ ] Phase gate checklist passed.

---

## Phase 5 — Demand forecasting and RAG career assistant

**Objective.** Forecast skill demand honestly and give students a grounded AI assistant.

**Features**
- **Forecasting:** monthly demand share per skill (and per role); models compared by
  rolling-origin backtest — seasonal naive, ETS (statsmodels), gradient boosting with lag
  features; best model per skill by sMAPE; prediction intervals; forecasts stored with model
  name, version and backtest error; "insufficient data" shown when history is too short
  (target ≥ 18 months).
- **RAG assistant:**
  - Corpus: learning resources, curriculum units, job postings, platform documentation; chunked
    with embeddings and Postgres full-text vectors.
  - Hybrid retrieval (full-text + vector, reciprocal rank fusion) with citations.
  - Tool calls for live numbers (e.g. skill demand, the student's gap and roadmap) so
    statistics come from the database, never from the model.
  - Claude via the official SDK, streamed over SSE; retrieved text treated as data, not
    instructions; per-user rate and token budgets; token usage logged.
- Roadmap priorities incorporate forecast growth.

**Dependencies.** Phase 1 (demand time series), Phase 3 (embeddings), Phase 4 (roadmaps the
assistant can reference).

**Deliverables.** Forecast training/scoring tasks, forecast endpoints, RAG indexing pipeline,
assistant endpoints (sessions, streamed messages, history), evaluation sets for both.

**Testing requirements**
- Unit: time-series feature building, backtest splitting, sMAPE, chunking, fusion ranking.
- Integration: scheduled forecast job writes forecasts; assistant answers with citations and
  correct tool-sourced numbers (LLM mocked).
- Evaluation: forecast backtest errors recorded; assistant groundedness on a set of at least 50
  questions, recorded and gated.
- Security: prompt-injection test documents in the corpus do not change assistant behaviour.

**Completion criteria**
- [ ] Forecasts are shown only where backtest error and history length meet thresholds.
- [ ] Every assistant statistic comes from a tool call (test asserts this on the eval set).
- [ ] Answers cite retrieved sources; groundedness score recorded here.
- [ ] Rate and token budgets enforced.
- [ ] Phase gate checklist passed.

---

## Phase 6 — Next.js frontend and complete integration

**Objective.** A complete, polished web application on top of the finished API, replacing the
v1 Dash UI.

**Features**
- Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Recharts.
- Typed API client generated from the OpenAPI schema.
- Auth pages and session handling with the httpOnly cookie flow.
- Student area: dashboard, profile and skills, resume upload and analysis, job matches,
  roadmap with progress, market intelligence, forecasts, career assistant (streaming chat).
- Faculty area: program curriculum upload and coverage/gap reports.
- Admin dashboard: platform stats, ingestion runs and triggers, taxonomy review queue, users
  and roles, model evaluation metrics, audit log.
- Loading, empty and error states for every view; responsive layout; accessibility (WCAG AA).
- v1 Dash UI retired once `docs/v1-parity.md` shows full parity in the new UI.

**Dependencies.** Phases 2–5 (all APIs in place).

**Deliverables.** `apps/web`, generated API client, CI job for the frontend, updated
`docs/v1-parity.md`.

**Testing requirements**
- Component tests (Vitest + React Testing Library) for forms, charts and state handling.
- Type check (`tsc`) and lint (ESLint) in CI.
- End-to-end tests (Playwright): register → profile → upload resume → see gap → roadmap →
  ask the assistant; faculty curriculum upload; admin ingestion trigger.
- Accessibility checks (axe) on main pages.

**Completion criteria**
- [ ] Every button and view is wired to a real endpoint; no placeholder data in the UI.
- [ ] Every dashboard number traces to an API response (spot-checked in E2E tests).
- [ ] E2E suites pass in CI.
- [ ] Full v1 parity confirmed; Dash retirement recorded in `docs/decisions.md`.
- [ ] Phase gate checklist passed.

---

## Phase 7 — Testing, security and deployment

**Objective.** Production readiness: hardened, measured, deployed and documented.

**Features**
- Test coverage gates (backend ≥ 80% lines), load test of key endpoints (k6), slow-query review
  and indexes.
- Security review: dependency audit (pip-audit, npm audit), container scan (Trivy), OWASP
  top-10 checklist, secrets in AWS Secrets Manager, HTTPS everywhere, proxy-header trust
  limited to the load balancer.
- AWS deployment: Terraform-provisioned EC2 host running the Compose stack, managed backups
  for Postgres, TLS, logs and basic alerting.
- CD pipeline: build and push images to ECR on `main`, deploy with migrations, health-checked
  rollout, documented rollback.
- Lock files regenerated on Linux (adds `uvloop`).
- Operations docs: runbook, backup/restore procedure, incident checklist; final architecture
  and API docs.

**Dependencies.** Phases 0–6.

**Deliverables.** `infra/terraform/`, deploy workflow, `docs/runbook.md`, `docs/security.md`
update, load-test scripts and results, public demo URL.

**Testing requirements**
- Full suite green, coverage gate met.
- Load test results recorded against agreed targets (e.g. p95 latency for read endpoints).
- Restore from backup tested at least once.
- Smoke tests run automatically after each deploy.

**Completion criteria**
- [ ] No high or critical findings open in dependency and container scans.
- [ ] Application deployed on AWS over HTTPS; smoke tests pass after deploy.
- [ ] Rollback and backup restore each performed once and documented.
- [ ] Load-test results recorded here.
- [ ] Runbook and final docs complete.
- [ ] Phase gate checklist passed.

---

## Change log

| Date | Change |
|---|---|
| 2026-11-16 | Roadmap created (Phases 0–7). Phase 0 build committed in `df10e63`; Docker verification pending. |
