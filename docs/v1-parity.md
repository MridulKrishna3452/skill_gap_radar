# v1 → 2.0 feature parity

Every v1 feature (`legacy/`) and where it lives in 2.0. "Done" means implemented in the API and
covered by the tests named. Unit tests are in `apps/api/tests/unit/`, integration tests in
`apps/api/tests/integration/test_pipeline.py` (run with `RUN_INTEGRATION=1`).

Phase 1 covers the backend: data, analytics and the endpoints v1 exposed. Two groups of v1
features are scheduled for later phases by ROADMAP.md: the resume analyser (Phase 3) and the
Dash pages themselves (Phase 6, which builds the UI on these endpoints). They are listed here
so nothing is lost.

## Data and processing

| v1 feature | v1 location | 2.0 equivalent | Status | Tests |
|---|---|---|---|---|
| Job ingestion: Internshala HTML scraper | `scraper/scrapers.py` | Adzuna API connector (`services/ingestion/adzuna.py`); any licensed dataset via `python -m app.cli import-file` | Done, with a different source: scraping is not ported (decisions.md #1: no scraping) | `test_adzuna.py`, `test_adzuna_ingestion_end_to_end_and_idempotent` |
| Naukri / career-page "scrapers" | `scraper/scrapers.py` | Removed: they always generated mock jobs | Removed (bug, NOTICE.md) | `test_v1_regressions.py::test_bug1_*` |
| CSV / JSON loaders | `scraper/csv_loader.py`, `json_loader.py` | `services/ingestion/file_import.py` (CSV, JSON, JSONL, column map, licence recorded); v1's mock-file creation is not ported | Done | `test_file_import.py`, `test_synthetic_sources_are_excluded_from_analytics` |
| Ingestion bookkeeping | (none) | `ingestion_runs` with fetched / inserted / duplicates / errors; dedup by source id and content hash | Done (new) | `test_adzuna_ingestion_end_to_end_and_idempotent`, `test_cross_source_duplicate_content_is_skipped` |
| Normalizers: company, location, HTML | `scraper/cleaning.py`, `utils/helpers.py` | `services/normalize.py` (empty values become null instead of "Unknown Company" / "Remote"; acronyms keep their case) | Done | `test_normalize.py` (includes v1's test cases) |
| `standardize_skills_string` | `scraper/cleaning.py` | Replaced by the taxonomy alias table, which includes all its mappings | Done | `test_extraction.py` |
| Skill extraction (PhraseMatcher over 36 skills) | `nlp/pipeline.py` | `services/extraction/` over 110 skills / 467 aliases: context disambiguation, required vs nice-to-have, evidence spans, implied parents; runs in Celery | Done | `test_extraction.py`, `test_requirement.py`, `test_evaluation.py` |
| Curriculum PDF parsing | `curriculum/parser.py` | `services/curriculum/parser.py`: v1 regex strategy (generalised) plus a layout-aware fallback; real uploads only | Done | `test_curriculum_parser.py`, `test_curriculum_upload_parse_and_no_duplicates` |
| Sample syllabus PDF generator | `curriculum/parser.py` | Removed: the curriculum must be a real syllabus | Removed (bug, NOTICE.md) | `test_bug2_curriculum_pdf_is_never_generated_by_the_app` |
| Curriculum skill mentions | `dashboard/pages/curriculum_skills.py` | Per-unit graded coverage stored in `unit_skills` | Done | `test_coverage.py` |
| Gap analysis: coverage %, gap score, missing / covered skills | `analytics/gap_analysis.py` | `services/analytics/gap.py`: demand share × (1 − coverage) per program and role; coverage bias fixed | Done | `test_gap_math.py`, `test_gap_matches_hand_computed_values` |
| Trends: monthly counts, growth, growing / declining / emerging | `analytics/trend_analysis.py` | `services/analytics/trends.py` + `skill_demand_monthly`: monthly **share**, month-over-month change; movers only with enough postings | Done | `test_trends.py`, `test_taxonomy_and_trend_endpoints`, `test_movers_with_enough_postings` |
| Role roadmaps and learning text | `recommendation/engine.py` | `services/recommendations.py`; v1 text kept verbatim as `learning_content` (labelled `editorial:v1`); priority from demand share. v1's generic placeholder steps for skills without curated text are not reproduced | Done | `test_recommendations.py`, `test_recommendation_priority_uses_demand_share` |
| Universities table | `database/connection.py` | `universities`, `programs` (curricula are per program) | Done | `test_curriculum_upload_parse_and_no_duplicates` |
| Resume analyser (PDF → skills → match % → roadmap) | `nlp/resume_analyzer.py`, `POST /resume` | Phase 3 (resume intelligence), with upload hardening and worker-side parsing | Phase 3 | — |

## REST API (v1 `api/main.py`)

| v1 endpoint | 2.0 endpoint(s) under `/api/v1` | Status | Tests |
|---|---|---|---|
| `GET /jobs?limit=` | `GET /jobs` (pagination; filters q, source, location, company, skill, requirement, role, dates, include_synthetic), `GET /jobs/{id}` (skills with evidence) | Done | `test_jobs_endpoint_pagination_and_filters` |
| `GET /skills` (aggregated demand) | `GET /skills/demand` (share in window, by role); taxonomy `GET /skills`, `GET /skills/{slug}` | Done | `test_taxonomy_and_trend_endpoints`, `test_demand_changes_with_data` |
| `GET /curriculum` | `GET /programs/{id}/curriculum` (courses → units → skills); upload `POST /programs/{id}/curriculum`; status `GET /curriculum/documents/{id}` | Done | `test_curriculum_upload_parse_and_no_duplicates`, `test_curriculum_rejects_bad_uploads` |
| `GET /gap` | `GET /gap?program_id=&role=` (stored as a report), `GET /gap/reports/{id}`, `GET /gap/by-role` | Done | `test_gap_matches_hand_computed_values`, `test_gap_by_role` |
| `GET /recommendations?goal=` | `GET /recommendations?role=&program_id=`; roles listed by `GET /roles` | Done | `test_gap_matches_hand_computed_values`, `test_recommendation_priority_uses_demand_share` |
| `POST /resume` | Phase 3 (`/resumes`) | Phase 3 | — |
| (none) | `GET /sources`, `POST/GET /ingestion/runs`, `GET /trends/skills/{slug}`, `GET /trends/movers`, `GET /jobs/facets`, `GET /jobs/export` | New | `test_ingestion_endpoints`, `test_ingestion_trigger_queues_a_run`, `test_export_and_facets` |

## Dash pages (UI: Phase 6)

The pages themselves are rebuilt in Phase 6. The data each one showed is already available
from the API, computed from stored data:

| v1 page | What it showed | Data source in 2.0 |
|---|---|---|
| Home | Total jobs, curriculum topics, coverage %, gap score; role radar (**hardcoded values**) | `GET /jobs/facets` (totals), `GET /gap`, `GET /gap/by-role` (computed per-role demand vs coverage: replaces the hardcoded radar) |
| Industry skills | Top 15 skills, job distribution pie, word cloud, jobs table, CSV export | `GET /skills/demand`, `GET /jobs/facets`, `GET /jobs`, `GET /jobs/export` |
| Curriculum skills | Skill mentions in curriculum, institutions, modules | `GET /programs/{id}/curriculum`, `GET /universities`, `GET /programs` |
| Gap analysis | Sankey, coverage matrix | `GET /gap` |
| Trend analysis | Monthly trend lines, growing / declining / emerging cards | `GET /trends/skills/{slug}`, `GET /trends/movers` |
| Recommendations | Role selector, roadmap cards | `GET /roles`, `GET /recommendations` |
| Resume analyser | Upload, match %, roadmap | Phase 3 |

## v1 bugs (legacy/NOTICE.md) and their regression tests

| Bug | Fix | Regression test |
|---|---|---|
| Synthetic job data from mock scrapers and loaders | Mock generators removed; sources carry `is_synthetic`, analytics exclude them | `test_v1_regressions.py::test_bug1_no_mock_job_generators_in_app_code`, `::test_bug1_every_source_declares_whether_it_is_synthetic`; `test_synthetic_sources_are_excluded_from_analytics` |
| Curriculum was a PDF the code generated | Only uploaded PDFs are parsed; no PDF generation in the app | `test_v1_regressions.py::test_bug2_curriculum_pdf_is_never_generated_by_the_app`; `test_no_units_fails_instead_of_inventing_topics` |
| Home radar used hardcoded values | `GET /gap/by-role` computes them; no literal metric lists in analytics code | `test_v1_regressions.py::test_bug3_no_hardcoded_dashboard_values_in_api`; `test_gap_by_role`; `test_demand_changes_with_data` |
| Coverage % over the top 20 sorted by gap | Top-N chosen by demand; demand-weighted coverage over all skills | `test_gap_math.py::test_regression_v1_coverage_bias` |
| `run.py` used Dash's removed `run_server` | 2.0 entry point is `uvicorn app.main:app` (no Dash) | `test_v1_regressions.py::test_bug5_entry_point_works_without_dash` |
