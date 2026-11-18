# Database schema

PostgreSQL 17 with the `vector` and `pg_trgm` extensions. The schema changes only through
Alembic migrations in `apps/api/alembic/versions/`; each has a working downgrade (CI runs
upgrade → downgrade → upgrade). ORM models live in `apps/api/app/models/`.

| Migration | Content |
|---|---|
| `0001` | Extensions `vector`, `pg_trgm` |
| `0002` | Phase 1 core schema (all tables below) and a trigram index on `job_postings.title` |

Constraint and index names follow the convention in `app/db/base.py`
(`pk_<table>`, `fk_<table>_<col>_<ref>`, `uq_<table>_<col>`, `ck_<table>_<name>`, `ix_...`).

## Taxonomy

### `skills`
Curated tech skills (seeded from `app/seed/data/skills.json`) and optional ESCO reference skills.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| slug | varchar(80) unique | stable identifier used by the API and eval sets |
| name | varchar(120) | display name |
| category | varchar(60) | language, framework, database, cloud, devops, data, ml_ai, … , `esco` |
| description | text null | |
| parent_id | FK skills null | broader skill; a mention of the child implies the parent (PostgreSQL → SQL) |
| esco_uri | varchar(255) unique null | set only by `import-esco` on an exact label match |
| extractable | bool | false for reference-only ESCO concepts; the extractor ignores them |
| context_terms | varchar[] | words that support an ambiguous alias of this skill |
| created_at | timestamptz | |

### `skill_aliases`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| skill_id | FK skills (cascade) | indexed |
| alias | varchar(120) | as written in the seed |
| alias_normalized | varchar(120) unique | lower-case, whitespace-collapsed; an alias belongs to one skill |
| requires_context | bool | ambiguous alias ("go", "react", "lambda") |
| case_sensitive_form | varchar(120) null | exact-case form that counts as evidence ("Go") |
| negative_following | varchar[] | next words that reject a match ("go **to**") |
| strict | bool | single-letter aliases ("R", "C") need exact case and context |

### `roles`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| slug | varchar(80) unique | |
| name | varchar(120) unique | |
| description | text null | |
| title_patterns | varchar[] | lower-case phrases matched as whole words against posting titles |
| match_priority | int | highest wins when several roles match |

### `role_skills`
Editorial core skills per role (v1 `role_requirements`). Unique (`role_id`, `skill_id`).
Columns: id, role_id FK (cascade), skill_id FK (cascade), position.

### `learning_content`
Curated learning text per skill (v1 roadmap text). Columns: id, skill_id FK unique (cascade),
difficulty, estimated_weeks (float), steps (text[]), content_source (e.g. `editorial:v1`,
shown to users).

## Job market

### `job_sources`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| key | varchar(60) unique | `adzuna`, or the key given to `import-file` |
| name | varchar(120) | |
| kind | varchar(20) | check: `api` or `file` |
| is_synthetic | bool not null | synthetic sources are excluded from all analytics |
| licence | text null | terms the data is used under; required for new real file sources |
| homepage_url | varchar(500) null | |
| created_at | timestamptz | |

### `ingestion_runs`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| source_id | FK job_sources | indexed |
| status | varchar(20) | check: queued, running, succeeded, partial, failed |
| params | jsonb | validated fetch parameters (never credentials) |
| started_at, finished_at | timestamptz null | |
| fetched, inserted, duplicates, errors | int | `inserted` is recounted from committed rows |
| error_samples | jsonb | up to 20 short messages, no secrets |
| created_at | timestamptz | |

### `companies`
Columns: id, name (normalised display name), normalized_name unique (case/punctuation-free key).

### `job_postings`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| source_id | FK job_sources | unique with external_id |
| external_id | varchar(255) | source's id (or a stable hash for files without one) |
| content_hash | varchar(64) unique | SHA-256 of normalised title/company/location/description; cross-source dedup |
| ingestion_run_id | FK ingestion_runs null (set null) | |
| title | varchar(500) | HTML removed; GIN trigram index |
| company_id | FK companies null | indexed |
| location_raw | varchar(500) null | as received |
| location | varchar(255) null | normalised (v1 rules), indexed |
| country | varchar(2) null | |
| description | text | HTML removed, line breaks kept |
| salary_min, salary_max | numeric(14,2) null | |
| salary_currency | varchar(3) null | |
| salary_is_estimated | bool null | Adzuna `salary_is_predicted` |
| employment_type, category, experience_text | varchar null | |
| url | varchar(2000) null | |
| posted_at | timestamptz | indexed; required (never defaulted to "now") |
| ingested_at | timestamptz | |
| role_id | FK roles null (set null) | assigned from the title; indexed |
| extraction_status | varchar(20) | check: pending, done, failed |
| extractor_version | varchar(40) null | changes with the taxonomy/calibration; stale rows can be re-extracted |
| extracted_at | timestamptz null | |

### `posting_skills`
| Column | Type | Notes |
|---|---|---|
| posting_id | FK job_postings (cascade), PK | |
| skill_id | FK skills, PK | indexed |
| requirement | varchar(20) | check: required, nice_to_have, unspecified |
| confidence | float | check 0–1; per-rule value from `calibration.json` |
| implied | bool | only a narrower skill was mentioned |
| evidence | jsonb | `[{field, start, end, text, rule, requirement}]`, character offsets |

## Curriculum

### `universities`
Columns: id, name unique, country (2 letters, null), created_at.

### `programs`
Columns: id, university_id FK (cascade, indexed), name, degree null, created_at.
Unique (`university_id`, `name`).

### `curriculum_documents`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| program_id | FK programs (cascade) | indexed; unique with sha256 (re-upload = same row) |
| filename | varchar(255) | |
| sha256 | varchar(64) | |
| size_bytes | int | |
| content | bytea | the PDF (deferred load) |
| status | varchar(20) | check: queued, parsing, parsed, failed, superseded |
| parser_strategy | varchar(30) null | `regex` or `layout` |
| page_count, units_parsed | int null | |
| error | text null | parse failure reason |
| uploaded_at, parsed_at | timestamptz | |

### `courses`
Columns: id, program_id FK (cascade, indexed), document_id FK (cascade, indexed), position,
code null, title. Unique (`program_id`, `position`). A program's courses are replaced as a whole
when a new document parses.

### `course_units`
Columns: id, course_id FK (cascade), position, title, content, learning_outcomes null.
Unique (`course_id`, `position`).

### `unit_skills`
| Column | Type | Notes |
|---|---|---|
| unit_id | FK course_units (cascade), PK | |
| skill_id | FK skills, PK | indexed |
| coverage | float | check 0 < x ≤ 1; graded (see `services/curriculum/coverage.py`) |
| evidence | jsonb | `[{field, start, end, text, rule}]` |

## Analytics (derived; rebuilt from the tables above)

### `skill_demand_monthly`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| skill_id | FK skills (cascade) | indexed |
| month | date | first day of month (UTC), indexed |
| role_id | FK roles null (cascade) | NULL = all postings |
| postings_with_skill | int | |
| required_postings | int | postings where the skill is required |
| total_postings | int | counted postings in that month (and role) |
| share | float | postings_with_skill / total_postings, check 0–1 |
| computed_at | timestamptz | |

Unique (`skill_id`, `month`, `role_id`) with NULLS NOT DISTINCT. Only non-synthetic postings
with `extraction_status = 'done'` are counted. Rebuilt by `analytics.refresh_demand` after every
ingestion or extraction run.

### `gap_reports`
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| program_id | FK programs (cascade) | indexed |
| role_id | FK roles null (cascade) | |
| window_start, window_end | date | window_end is exclusive |
| postings_considered | int | |
| weighted_coverage, top_n_coverage | float null | null when there was no demand data |
| payload | jsonb | full API response (per-skill rows and parameters) |
| computed_at | timestamptz | |

One row per `GET /gap` call, so earlier results stay reproducible.
