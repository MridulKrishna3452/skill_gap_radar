# Project metrics ledger

Measured numbers for SkillRadar AI 2.0, recorded phase by phase, for reporting the project (for
example on a resume). **Every number here was measured, with the date and the source.** None is
estimated or rounded up. When a number changes, add a new dated row instead of overwriting the
old one, so the history stays visible. Caveats next to a number belong with it whenever the
number is quoted.

Sources used below:
- **DB**: SQL on the development database.
- **API**: a live call to the running API.
- **tests**: `pytest` with `RUN_INTEGRATION=1`.
- **code**: counting lines and files in the repository.
- **report**: `reports/extraction_v1_eval.md`.

---

## Phase 0: Infrastructure and project setup (✅ complete 2026-11-18)

| Metric | Value | Source / date |
|---|---|---|
| Docker Compose services | 5 (Postgres + pgvector, Redis, migrate, FastAPI API, Celery worker) | `docker-compose.yml`, 2026-11-18 |
| CI jobs | 3 (lint + types + tests, secret scan, Docker image build) | `.github/workflows/ci.yml` |
| Tests at phase close | 23 | change log, 2026-11-18 |
| CI run that closed the phase | green on `main` @ `12f10ff` (run 44274767002) | GitHub Actions, 2026-11-18 |

## Phase 1: v1 functionality on real data (✅ complete 2026-11-21)

### Phase close

| Metric | Value | Source / date |
|---|---|---|
| Closing commit | `7bcfd98` (merge of PR #2) | GitHub, 2026-11-21 |
| CI on closing commit | green: 3 of 3 jobs on PR run 44910055396 and `main` run 44912030930 | GitHub Actions, 2026-11-21 |
| Completion criteria | 8 of 8 met | ROADMAP.md |
| Local F1 gate | `cd apps/api && python -m app.cli eval-extraction --path ../../data/eval_sets/extraction_v1.jsonl --min-f1 0.89` (the labelled set is private, so this is run locally before each phase closes) | data/eval_sets/README.md |

### Data pipeline (real data, Adzuna India API)

| Metric | Value | Source / date |
|---|---|---|
| Real job postings stored | **2,151** | DB, 2026-11-21 |
| Ingestion runs | 11 (2,300 postings fetched) | DB `ingestion_runs` |
| Duplicates caught by dedup | **149** (6.5 % of fetched); 0 duplicate rows stored | DB; `fetched = inserted + duplicates` for every run |
| Re-fetch idempotency | re-fetching a live page: 50 of 50 recognised as duplicates, 0 inserted | run 11, 2026-11-18 |
| Companies, locations | 1,210 companies, 62 locations | DB |
| Postings with salary data | 623 (29 %) | DB |
| Posting date range | 2019-05-17 to 2026-11-18 (26 months with data) | DB |
| Monthly demand time-series rows | 1,532 | DB `skill_demand_monthly` |
| Demand table vs direct recount | 0 mismatches (424 rows checked) | verification, 2026-11-18 |

### Skill extraction (NLP)

| Metric | Value | Source / date |
|---|---|---|
| Skills taxonomy | **118 skills, 486 aliases** (v1 had 36 skills) | `skills.json`, 2026-11-21 |
| Job roles | 15 | `roles.json`, 2026-11-21 |
| Skill mentions extracted | **4,229** direct (+238 implied parents) | DB `posting_skills` |
| Postings with at least one skill | 1,389 of 2,151 (64.6 %) | DB. Caveat: Adzuna supplies ~500-character snippets, not full ads |
| Distinct skills observed in postings | 112 of 118 | DB |
| Postings assigned a role | 2,008 of 2,151 (93.4 %) | DB |
| **Extraction F1 (micro)** | **0.925**: precision 0.908, recall 0.943 (95 % CI 0.893 to 0.953) | report, 2026-11-21 |
| Macro F1 | 0.912 over 65 labelled skills; 0.812 over all 73 labelled or predicted skills | report |
| Evaluation set | 120 real postings, 210 labels, 65 skills, 0 skipped | report |
| Pipeline consistency | stored predictions identical to the evaluator's for 120 of 120 postings | report |
| F1 quality gate | threshold 0.89 (owner-agreed); **passed** with 0.9252 | local `eval-extraction --min-f1 0.89`, 2026-11-21 13:39 UTC (PR branch) |
| F1 quality gate on merged `main` | **passed** with 0.9252 (P 0.9083, R 0.9429), exit code 0 | local run on `7bcfd98`, 2026-11-21 14:06 UTC |

Caveat for the F1: the labels were drafted by Claude and reviewed by the owner (118 of 120
unchanged). It is not an independent human benchmark. 17 of 32 errors come from labels that
predate 8 skills added the same day.

### Curriculum analysis (real syllabus)

| Metric | Value | Source / date |
|---|---|---|
| Syllabus parsed | Pondicherry University B.Tech CSE 2023-24, 212-page PDF | 2026-11-20 |
| Courses / units extracted | **79 courses, 395 units** (all courses that have units; the other 20 headings are 18 labs and 2 projects, which have none) | DB |
| Unit-to-skill matches | 196, each audited by hand against its evidence | DB, 2026-11-20 |
| Parser bugs found on the real PDF and fixed | 2 (two-digit course codes, reference lists read as content) | `docs/decisions.md` |
| Gap analysis result | weighted coverage **0.340**, gap index **0.660**, top-20 coverage 0.395 (12 of 20 skills) vs 2,109 postings | API `/gap`, 2026-11-21 |
| Gap by role | 15 roles; 10 with ≥ 30 postings; gap index from 0.30 (Software Development Manager) to 0.76 (DevOps Engineer) | API `/gap/by-role`, 2026-11-21 |

### Engineering

| Metric | Value | Source / date |
|---|---|---|
| Database tables | 18 (2 Alembic migrations, each with a tested downgrade) | DB, `alembic/versions` |
| REST API | 25 paths, 29 operations, paginated and filtered | API `/api/v1/openapi.json`, 2026-11-21 |
| Background tasks | 6 Celery tasks | `app/workers/tasks.py` |
| Operator CLI commands | 12 | `app/cli.py` |
| Automated tests | **204** (182 unit, 22 integration) | tests, 2026-11-21 |
| Application code | 6,173 lines of Python in 57 modules; 2,128 lines of tests | code, 2026-11-21 |
| v1 bugs fixed, each with a regression test | 5 | `docs/v1-parity.md` |
| Defects found in post-merge verification and fixed | 9: schema drift, truncated-word matches, extractor versioning, test isolation, 2 parser bugs, 3 ambiguous aliases | ROADMAP Phase 1 |
| Static checks | ruff, ruff format, mypy (strict) and `alembic check` all clean | 2026-11-21 |

---

## Phase 2: Authentication and student profiles (🟡 in progress; 6 of 7 criteria met)

| Metric | Value | Source / date |
|---|---|---|
| New database tables | 6 (24 in total), migration `0003` with a downgrade | DB, `alembic/versions`, 2026-11-21 |
| API size | 50 operations on 39 paths (was 29 on 25); 21 new | API `/api/v1/openapi.json`, 2026-11-21 |
| Operations under access control | 30 protected (8 any user, 7 student, 12 admin, 3 program manager), 18 public, 2 refresh-cookie | `tests/integration/test_access.py` |
| Access-control test coverage | 50 of 50 operations have a rule; every protected one is checked for 401 / 403 / allowed | `test_access.py`; mutation check confirms it catches a missing guard |
| Roles | 3 (student, faculty, admin) and faculty→program assignments | `app/models/users.py` |
| Password hashing | argon2id (t=3, 64 MiB, p=4), 12–128 character policy | `docs/security.md` |
| Tokens | 15-minute JWT access tokens; 14-day rotating refresh cookies with reuse detection; 30-day maximum per login | `docs/security.md` |
| Abuse controls | 6 Redis rate limits; lockout after 5 failures for 15 minutes | `docs/security.md`, `test_rate_limits`, `test_failed_logins_lock_the_account` |
| Audited action types | 12 | `app/services/audit.py` |
| Automated tests | **256** (215 unit, 41 integration); 52 new auth/access tests (33 unit, 16 auth integration, 3 access) | tests, 2026-11-21 |
| Application code | 8,123 lines of Python in 69 modules; 3,084 lines of tests | code, 2026-11-21 |
| CLI commands | 13 (adds `create-user`) | `app/cli.py` |
| F1 gate re-run (local) | 0.9252 ≥ 0.89, passed (extraction unchanged) | `eval-extraction --min-f1 0.89`, 2026-11-21 15:21 UTC |

## Phases 3–7

Not started. Each phase adds its own section here when it starts, and its metrics are recorded as
they are verified.
