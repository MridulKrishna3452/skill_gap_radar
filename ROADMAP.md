# SkillRadar AI 2.0 — Development Roadmap

**This file is the single source of truth for project progress.** Update it whenever progress
changes. A phase is complete only when every item in its *Completion criteria* is checked and
its tests pass. See [CLAUDE.md](CLAUDE.md) for the working rules.

Architecture decisions (data sources, LLM, auth, infrastructure): [docs/decisions.md](docs/decisions.md).

## Status

| Phase | Name | Status | Depends on |
|---|---|---|---|
| 0 | Infrastructure and project setup | ✅ Complete (2026-11-18) | — |
| 1 | Stabilize existing V1 functionality | ✅ Complete (2026-11-21) | 0 |
| 2 | Authentication and student profiles | 🟡 In progress (started 2026-11-21) — 6 of 7 criteria met; open: phase gate (CI, owner review and merge) | 0, 1 |
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
- [x] Ruff, mypy and unit tests pass locally (20 unit tests).
- [x] `docker compose up --build` verified locally; `/api/v1/health/ready` returns 200
      (database ok, redis ok); all services healthy, `migrate` exits 0. *(2026-11-18)*
- [x] Integration tests pass (`RUN_INTEGRATION=1 pytest`) against the Compose services:
      23 passed (20 unit + 3 integration). *(2026-11-18)*
- [x] Alembic upgrade → downgrade → upgrade verified against a real database; ends at
      `0001 (head)`; Postgres 17.12 with `vector` 0.8.7 and `pg_trgm` 1.6. *(2026-11-16)*
- [x] Worker processes `system.ping` from the running stack (task received and succeeded
      in worker logs). *(2026-11-18)*
- [x] CI run green on GitHub: workflow run 44274767002 on `main` @ `12f10ff` (merge of PR #1),
      all three jobs passed: lint/types/tests, Docker build, secret scan. *(2026-11-18)*

**Notes.**
- Initial commit `df10e63`. Local verification completed 2026-11-18; container logs show no
  errors (only Postgres's standard notice that socket connections inside the container are
  trusted; network connections require the password).
- Fixes found during verification: the Compose host ports clashed with a Postgres (5432) and
  Redis (6379) installed natively on the dev machine, so host ports are now configurable and
  default to 5433 / 6380. Host URLs use `127.0.0.1` because on Windows `localhost` resolves to
  IPv6 `::1` first, adding ~2 s per connection and tripping the readiness timeout. Settings
  also read the repo-root `.env` when run from `apps/api`.
- The first push of `main` (run 44245923876, `c7b2f3b`) failed the gitleaks secret scan; the
  run logs need a GitHub login, so the cause was not inspected. The PR run and the `main` run
  after the merge both passed the scan.
- Phase gate: criteria all checked; local checks re-run 2026-11-18; CI green. Phase 0 complete.

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
  *Agreed 2026-11-21: F1 ≥ 0.89, gated locally (the set is private); measured 0.925.*
- Regression tests for each v1 bug listed in `legacy/NOTICE.md`.

**Completion criteria**
- [x] Every v1 feature in `docs/v1-parity.md` has a working, tested 2.0 equivalent.
      *Met for the Phase 1 scope: every data, analytics and API feature is done and tested
      (test names in the parity doc). Two v1 features are scheduled later by this roadmap: the
      resume analyser (Phase 3) and the Dash pages (Phase 6; their data is served by Phase 1
      endpoints). Owner confirmed this reading on 2026-11-20.*
- [x] At least one real data source ingests successfully; no synthetic records in analytics.
      *Adzuna (India), 2026-11-18: 10 runs via `POST /ingestion/runs` (9 role searches, last 90
      days, 5 pages each, plus one 2-page test) stored 2,151 real postings, 99 duplicates
      skipped, all extracted. Two runs were `partial` because Adzuna returned HTTP 503 on one
      page after 3 attempts each. No synthetic sources exist; synthetic exclusion is tested in
      `test_synthetic_sources_are_excluded_from_analytics`.*
- [x] Re-running ingestion or re-uploading a curriculum creates no duplicates.
      *`test_adzuna_ingestion_end_to_end_and_idempotent` (re-run: 0 inserted, 60 duplicates),
      `test_cross_source_duplicate_content_is_skipped`,
      `test_curriculum_upload_parse_and_no_duplicates`. (2026-11-18)*
- [x] Extraction F1 measured on a labelled set of at least 100 postings and recorded here.
      *Measured 2026-11-21 on `extraction_v1.jsonl`: 120 real Adzuna postings, 210 labels over 65
      skills, 44 records with no labels, sha256 `e1da2b1d…78d5d5a8`, reviewed by the owner (MK).
      The file is git-ignored because it contains Adzuna text. All 120 records were evaluated
      and none skipped; records with no labels count every prediction as a false positive.
      Extractor `2.1+449ecffeb7`. **Micro precision 0.908, recall 0.943, F1 0.925** (TP 198,
      FP 20, FN 12; 95 % bootstrap interval for F1 0.893 to 0.953). Macro F1 0.812 over the 73
      skills labelled or predicted, and 0.912 over the 65 labelled skills. The production
      pipeline's stored predictions for the same 120 postings are identical. Full report:
      `reports/extraction_v1_eval.md`. **Caveats:** (1) 118 of 120 records are unchanged from
      the Claude draft, so this mostly measures the extractor against Claude-drafted, owner-
      checked labels, not independent human labels. (2) The labels use none of the 8 skills
      added on 2026-11-21, and 17 of the 32 errors come from that mismatch (e.g. the extractor
      says `test-automation` where the label says `unit-testing`). This is the score as
      labelled, and the labels were not changed.*
- [x] Gap and coverage numbers verified against hand-computed fixtures.
      *`test_gap_math.py`, `test_coverage.py`, `test_trends.py`; end to end through the API in
      `test_gap_matches_hand_computed_values` and `test_gap_by_role`. (2026-11-18)*
- [x] Each v1 bug in `legacy/NOTICE.md` has a regression test that passes.
      *Mapped in `docs/v1-parity.md`: `test_v1_regressions.py` (bugs 1, 2, 3, 5) and
      `test_gap_math.py::test_regression_v1_coverage_bias` (bug 4). (2026-11-18)*
- [x] `docs/schema.md` documents all tables; endpoints documented in OpenAPI.
      *All 18 tables in `docs/schema.md`; 25 paths in `/api/v1/openapi.json`, each with a
      summary and typed response model. (2026-11-18)*
- [x] Phase gate checklist passed.
      *Passed 2026-11-21 on `main` @ `7bcfd98` (merge of PR #2, reviewed and merged by the owner).
      (1) All seven criteria above are checked. (2) ruff, ruff format and mypy (strict) are clean,
      and `alembic check` shows no drift. (3) 204 tests pass with `RUN_INTEGRATION=1` (182 unit,
      22 integration). (4) CI is green on the closing commit: PR run 44910055396 and `main` push
      run 44912030930, with all 3 jobs (lint/types/tests, secret scan, Docker build) successful.
      (5) Compose stack healthy, `/api/v1/health/ready` → 200. (6) This file is updated.
      **F1 gate** (threshold 0.89, run locally; the labelled set is private): on `7bcfd98`, at
      2026-11-21 14:06 UTC, `python -m app.cli eval-extraction --path
      ../../data/eval_sets/extraction_v1.jsonl --min-f1 0.89` gave **F1 0.9252** (P 0.9083,
      R 0.9429; 120 postings, none skipped; extractor `2.1+449ecffeb7`; ground truth sha256
      `e1da2b1d…78d5d5a8`), exit code 0. **Privacy check:** across the whole history of
      `origin/main`, no tracked dataset, draft, labelling page, PDF or `.env`; none of the 3
      credential values in `.env`; and no 60-character fragment of any of the 2,151 stored
      posting descriptions.*

**Post-merge verification (2026-11-18, `main` @ `12f10ff`).**
- *Migrations and schema:* dev DB at `0002 (head)`; up/down/up round trip on the test database;
  offline SQL creates 18 tables + `alembic_version`; every DB column appears in
  `docs/schema.md`. **Issue found and fixed:** `alembic check` reported drift (the trigram
  index existed only in the migration, so the next autogenerate would have dropped it). It is
  now declared on the model; `alembic check` passes and runs in CI.
- *Adzuna on real data:* 2,151 postings; run counts reconcile (fetched = inserted +
  duplicates for every run; sum of inserted = rows); no synthetic sources; no HTML left;
  stored monthly demand equals a direct recount (424 rows, 0 mismatches); live re-fetch of a
  real page gave 50 duplicates, 0 inserts. **Data issue (not fixed, documented):** 9 postings
  have `posted_at` up to 4 h 32 min after we ingested them; consistent with Adzuna India
  sending IST times marked as UTC (≤ 5 h 30 min shift). Unconfirmed, so timestamps are stored
  as received.
- *Extraction on real data:* **Issue found and fixed:** Adzuna snippets end in "…", so cut-off
  words were matched as other skills ("CI/C…" → C, "R…" → R, "Java…" could be JavaScript).
  Matches cut off by an ellipsis are now dropped when the alias is the start of another
  skill's alias. Extractor bumped to 2.1 (code version now part of the version string) and all
  2,151 postings re-extracted. Other doubtful matches seen in a spot check (Oracle the company
  read as Oracle Database; "Transformers" as a model architecture) are left for the labelled
  set to quantify.
- *Test isolation fixed:* integration test settings read a developer's `.env`, so a configured
  Adzuna key changed a test's outcome. Test settings now blank Adzuna credentials.
- *F1:* draft labels and provisional F1 done 2026-11-20 (see the criterion above); owner review
  outstanding.
- *Real syllabus (2026-11-20):* Pondicherry University, B.Tech Computer Science and Engineering
  (affiliated colleges), curriculum 2023-24 revised 01-10-2024, a public PDF from
  `pondiuni.edu.in` (212 pages, 1,040,114 bytes, SHA-256 `e0337788…d2bb83`; not committed,
  it is the university's document). Uploaded through `POST /programs/{id}/curriculum`, parsed
  by the worker. **Two parser bugs found and fixed:** (1) two-digit course codes (`CSH01`,
  `CSM03`) were not recognised, so 10 honours/minor courses were merged into the preceding
  capstone project; (2) "Text Books" / "References" / "Online/NPTEL" lists were read as the
  last unit's content, so book titles counted as coverage ("Computer Networking: A Top-Down
  Approach" under Web Technology). After the fixes, all 79 courses with units are parsed, 5
  units each (395 units); the other 20 headings are 18 labs and 2 capstone projects, which
  have no units in the PDF. Re-uploading the same file returns HTTP 200 and creates nothing.
  **Coverage audit:** all 200 unit–skill matches were read against their evidence. Clear false
  positives fixed in the taxonomy: "ruby" lasers, "Bootstrap Loader", "electronic/engineering
  system design" (ruby, bootstrap and "system design" now need context; 30 postings were
  affected, provisional F1 unchanged). Left and documented: "File system design" (OS course)
  still read as System Design; "Web Services" in "Google Web Services" read as REST; "Red Hat"
  the company read as Linux. 196 matches remain. **Results** (window Jun–Nov 2026, 2,109
  postings): weighted coverage 0.344, top-20 coverage 0.395 (12 of 20 covered), gap index
  0.656. Largest gaps: DevOps, React, ETL, CI/CD, Angular, Generative AI. By role, gap index
  ranges 0.42 (ML engineer) to 0.77 (DevOps engineer); 5 roles flagged `low_sample`.

**Notes.**
- Started 2026-11-18 on the owner's instruction while Phase 0's last item (a green CI run on
  GitHub) was still open; that item and this phase's CI run can be closed together.
- Design choices (taxonomy changes from v1, disambiguation rules, coverage grades, gap and
  priority formulas, analysis window, low-sample flags): `docs/decisions.md`, "Phase 1 design
  choices".
- Data caveats: shares are relative to the postings fetched, and those were chosen by search
  terms, so they describe this sample, not the whole Indian job market. Adzuna gives description
  snippets: 788 of 2,151 postings (37 %) mention no taxonomy skill. November 2026 is a partial
  month. 179 postings match no role.
- Owner inputs needed to finish: (1) ~~Adzuna key~~ done 2026-11-18; (2) ~~a real
  syllabus PDF~~ done 2026-11-20 (public Pondicherry University syllabus, owner-approved);
  (3) ~~labelling process~~ approved 2026-11-20; remaining: **review the drafted labels**,
  after which the F1 is recorded here and the CI gate threshold agreed.
- Confidence values are uncalibrated priors until step (3) (`calibration.json` says
  `status: prior`).

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
- [x] All auth flows work end to end, including refresh rotation and reuse detection.
      *`test_full_session_flow`, `test_refresh_token_reuse_revokes_the_family`,
      `test_expired_and_overage_refresh_tokens_are_rejected`, `test_password_change_ends_every_session`,
      `test_logout_all`, `test_failed_logins_lock_the_account`, `test_rate_limits`. Also checked
      against the running Docker stack on 2026-11-21: login, `/me` 200 and anonymous 401, admin
      route 200, refresh 200, and replaying the rotated cookie gave 401 with an
      `auth.refresh_reuse` audit entry. The smoke-test accounts were deleted afterwards.*
- [x] Every non-public endpoint is covered by the 401/403 parametrised test.
      *`tests/integration/test_access.py`: an access rule for all 50 operations, read from the
      OpenAPI schema (fails on any unlisted route). The 30 protected operations get no token → 401,
      wrong role → 403, right role → allowed. Checked by mutation: removing the admin guard from
      ingestion makes the test fail.*
- [x] Profiles and user skills CRUD work with validation.
      *`test_profile_crud_and_validation` (program/university mismatch, unknown role, year
      range, unknown field, unknown program → 422; non-students 403), `test_skills_inventory`
      (duplicate 409, unknown slug and proficiency out of range 422, update, delete, 404).*
- [x] No password, token or secret appears in logs (test asserts this).
      *`test_no_password_token_or_secret_in_logs` checks raw records and printed output;
      `test_redaction` covers the redactor. Docker API logs from the smoke test contained no JWT
      or refresh-cookie value.*
- [x] Account deletion removes the user's personal data.
      *`test_account_deletion_removes_personal_data`: no row referencing the user in any of the
      6 account tables, and no email anywhere in the audit log.*
- [x] `docs/security.md` written.
- [ ] Phase gate checklist passed.
      *2026-11-21 local results: ruff, format, mypy (strict) and `alembic check` are clean; 256
      tests pass with `RUN_INTEGRATION=1` (215 unit, 41 integration); migration 0003 applied;
      Compose rebuilt and healthy; local F1 gate 0.9252 ≥ 0.89 (exit code 0, extractor
      unchanged). **Open:** CI on the Phase 2 PR, then owner review and merge.*

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
| 2026-11-18 | Phase 0 verified locally: Compose stack healthy, migrations round trip, 23 tests pass, worker ping. Fixed host-port clash and Windows `localhost` delay. Only the CI run remains. |
| 2026-11-18 | Phase 1 started on owner instruction. Built: migration `0002` (18 tables), taxonomy seed (110 skills / 467 aliases / 14 roles), Adzuna + file ingestion with run tracking and dedup, extraction v2, curriculum parser + graded coverage, demand series, gap (+ by role), trends, recommendations, 25 API paths, Celery tasks, CLI, `docs/schema.md`, `docs/v1-parity.md`. 169 tests pass (148 unit, 21 integration). 4 of 8 criteria met; remaining ones need the Adzuna key, a real syllabus, labelled postings and a CI run. |
| 2026-11-18 | First real data: Adzuna key configured (in `.env` only), 2,151 real postings ingested and extracted. 5 of 8 Phase 1 criteria met. |
| 2026-11-18 | PR #1 merged; CI green on `main` → **Phase 0 complete**. Post-merge verification of Phase 1: fixed model/migration index drift, truncated-word false matches (extractor 2.1, all postings re-extracted) and test isolation; documented Adzuna timestamp offset. 175 tests pass. F1 and real-syllabus checks still open. |
| 2026-11-20 | Owner approved: parity reading (criterion ticked), a public syllabus, and a labelling process (Claude drafts blind, owner reviews). Real syllabus (Pondicherry University B.Tech CSE 2023-24) uploaded and parsed: fixed two parser bugs (two-digit course codes, reference lists read as content) and three ambiguous aliases (ruby, bootstrap, "system design"); all postings re-extracted, curriculum re-graded. Draft labels for 120 postings: provisional F1 0.955. 185 tests pass. 6 of 8 criteria met; open: owner label review → final F1 + CI threshold → phase gate. |
| 2026-11-21 | Owner review feedback applied. Taxonomy 110 → 118 skills (test automation split from unit testing; manual, exploratory and regression testing; React Native; Tailwind CSS; Pega; Pega Smart Dispute), no slug removed. Role `software-development-manager` added (36 previously unclassified postings), `reclassify-roles` command. Labelling rules revised (company descriptions and role names in titles not labelled). Labelling page: review flags, explicit review marks, navigation, highlighting, JSONL restore; export keeps the same schema and records unreviewed rows; evaluator rejects duplicate ids. All postings re-extracted. Provisional F1 on the unreviewed draft 0.921 (stale draft labels; flagged for review). |
| 2026-11-21 | Owner delivered the reviewed ground truth (`extraction_v1.jsonl`, 120 postings, git-ignored). Evaluated with no records skipped: micro P 0.908 / R 0.943 / **F1 0.925** (95 % CI 0.893 to 0.953), macro F1 0.812 (all skills) / 0.912 (labelled skills). Pipeline cross-check: identical predictions for all 120. 17 of 32 errors come from labels that predate the 2026-11-21 skills. Report: `reports/extraction_v1_eval.md`. Evaluator gained per-skill and macro metrics. F1 criterion ticked; 7 of 8 criteria met. The 8th, the phase gate, is open: CI threshold agreement and a green CI run. |
| 2026-11-21 | Owner decisions: F1 gate threshold 0.89, run locally before each phase closes (labelled set stays private); optional changes deferred. Local gate passed (F1 0.9252). Phase 1 PR opened for review; Phase 1 is not complete until it is reviewed, merged and CI is green. |
| 2026-11-21 | PR #2 merged (`7bcfd98`). Post-merge verification: CI green on PR and `main` (runs 44910055396, 44912030930); local F1 gate passed (0.9252 ≥ 0.89); 204 tests and all static checks pass; stack healthy; no private data or secrets in history. **Phase 1 complete.** Phase 2 needs the owner's approval to start. |
| 2026-11-21 | **Phase 2 started** on the owner's instruction, with the proposal's recommended defaults (docs/decisions.md). Built: migration `0003` (6 tables); argon2id passwords, JWT access tokens and rotating refresh cookies with reuse detection; lockout and Redis rate limits; roles plus faculty program assignments; access rules on all 50 operations (21 new); profiles, skills inventory, account deletion, audit log, log redaction; a `create-user` CLI and `docs/security.md`. 256 tests pass. 6 of 7 criteria met; the phase gate awaits CI and review. |
