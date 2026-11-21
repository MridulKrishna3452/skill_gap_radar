# Architecture decisions

Approved 2026-11-16 (recommended defaults from the v1 audit).

| # | Decision | Choice |
|---|---|---|
| 1 | Job data | Adzuna API for live postings (India and other markets) plus a public historical dataset, after its licence and date range are checked. No scraping of sites whose terms forbid it. Forecasts show "insufficient data" until enough history exists. |
| 2 | Synthetic data | v1 mock scrapers removed from production code. Synthetic data only in test fixtures, and any synthetic source is flagged `is_synthetic` and excluded from analytics. |
| 3 | UI | Plotly Dash retired once the Next.js frontend reaches parity. |
| 4 | Skill taxonomy | ESCO plus a curated tech subset; v1 alias dictionary seeds the alias table. |
| 5 | LLM | Claude via the official `anthropic` SDK, default `claude-opus-5-5`; `claude-haiku-5-5` is optional for bulk work. Scores and metrics are never produced by the LLM. |
| 6 | Embeddings | Local sentence-transformers model (384-dimensional), stored in pgvector. |
| 7 | Auth | In-house JWT: short-lived access tokens, rotating refresh tokens in httpOnly cookies, argon2id hashes. |
| 8 | Roles | `student`, `faculty` (manages a program's curriculum), `admin`. |
| 9 | Task queue | Celery with Redis as broker. |
| 10 | AWS | Single EC2 host running Docker Compose, provisioned with Terraform. Can move to ECS Fargate + RDS + ElastiCache later. |
| 11 | Curriculum data | Real syllabus PDFs supplied by the project owner (e.g. own university, AICTE model curriculum). |
| 12 | Repository | Monorepo under git. Kept in place for now; moving it out of OneDrive is recommended. |
| 13 | Forecasting | statsmodels added for ETS baselines alongside scikit-learn models. |

## Phase plan

The phase plan, its status and completion criteria live in [ROADMAP.md](../ROADMAP.md)
(Phases 0–7), which supersedes the 14-step plan (P0–P13) proposed in the initial audit.
How the audit's steps map onto the roadmap:

| Roadmap phase | Audit steps folded in |
|---|---|
| 0 Infrastructure and project setup | P0 |
| 1 Stabilize existing V1 functionality | P2 ingestion, P3 extraction, P5 curriculum, P6 gap analysis, market APIs from P4 |
| 2 Authentication and student profiles | P1 |
| 3 Resume intelligence and semantic job matching | P7, P8 |
| 4 Personalized learning roadmaps | P9 |
| 5 Demand forecasting and RAG career assistant | P10, P11 |
| 6 Next.js frontend and complete integration | frontend from P4, P12 admin dashboard |
| 7 Testing, security and deployment | P13 |

## P0 conventions

- One error shape for every response: `{"error": {"code", "message", "request_id", "details"?}}`.
  Unexpected errors return a generic 500; details go to logs only, keyed by request ID.
- Every response carries `X-Request-ID` and baseline security headers; HSTS in production.
- No side effects at import time: DB engine and Redis are created in the app lifespan.
- Settings validate themselves: wildcard CORS is rejected, production requires a strong
  `JWT_SECRET` and https origins.
- Health: `/api/v1/health/live` (process only) and `/api/v1/health/ready` (Postgres + Redis,
  503 if either is down).
- Migrations are the only way the schema changes; CI runs upgrade, downgrade, upgrade.

## Phase 1 design choices

Made while building Phase 1 (2026-11-18). Each is documented in code next to where it applies.

- **Taxonomy.** 110 curated tech skills, 467 aliases, seeded from v1's alias dictionary. v1
  aliases that were too broad became child skills with a parent (PostgreSQL → SQL, Helm →
  Kubernetes, PySpark → Spark); a mention of a child counts as implied evidence for the parent.
  Some v1 mappings were corrected rather than kept: `bash` / shell scripting is its own skill
  (v1 counted it as Linux); `py`, `tf` as Terraform, `hcl`, `yarn`, `pig`, `iam`, `adf`,
  `rails`, `containers` and bare `algorithms` were dropped or made context-dependent because
  they produce false matches. ESCO is linked by exact label match only (`import-esco`); no ESCO
  URI is ever typed by hand.
- **Ambiguous aliases** ("go", "react", "lambda", "spark", "excel", "R", "C", …) need
  supporting context (a context word nearby, a delimited skill list, or the exact case form
  next to another skill) and are rejected by negative cues ("go to", "react quickly").
- **Confidence** is a per-rule value in `calibration.json`. Until the labelled set exists the
  values are priors, and the file says so (`status: prior`).
- **Requirement level** comes from section headers and sentence cues; when a sentence has both
  required and nice-to-have cues, nice-to-have wins.
- **Coverage grades** (0–1): unit title 1.0, course title 0.8, content 0.5 / 0.6 / 0.7 for 1 /
  2 / 3+ mentions, outcomes only 0.4. Program coverage = the best unit. A heuristic, documented
  as one.
- **Gap**: per skill `demand_share × (1 − coverage)`; summary = demand-weighted coverage over all
  demanded skills, plus mean coverage of the top-N skills **by demand** (fixes v1's bias).
- **Window**: the last 6 whole months ending at the latest month with data (or `as_of`).
  Results with fewer than 30 postings are flagged `low_sample`; trend movers are not computed
  then, and recommendation priority is `insufficient_data`.
- **Recommendation priority** from the role's demand share: high ≥ 30 %, medium ≥ 10 %, else
  low. Replaces v1's fixed mention-count cut-offs.
- **Curriculum versions**: a program has one current curriculum. Re-uploading identical bytes is
  a no-op; a new file replaces the courses when it parses; the old document is marked
  `superseded`. PDFs are stored in Postgres so API and worker need no shared volume.
- **Adzuna descriptions are snippets** (a few hundred characters), so extraction on Adzuna
  postings sees part of each ad. Recorded on the source's licence note and here; the eval set
  should be drawn from the same data so the measured F1 reflects it.
- **Truncated snippets** (added after the first real-data check). A match that runs straight
  into "…" / "..." is dropped when its alias is the start of another skill's alias
  ("Java…" might be JavaScript, "C…" might be C++ or CI/CD). Complete words such as "AWS…" are
  kept.
- **Extractor version** = `EXTRACTOR_VERSION` (bumped by hand on any change to matching logic)
  + a hash of the taxonomy and calibration. Any change re-queues stored postings via
  `python -m app.cli reextract`.
- **Adzuna timestamps** are stored as received. Some India postings are dated up to ~4.5 h after
  we fetched them, which suggests IST times labelled as UTC; this is unconfirmed, so no
  correction is applied. Impact: at most a 5.5 h shift, which only matters at month
  boundaries.
- **Labelling process for the F1 set** (owner-approved 2026-11-20). Claude drafts labels blind
  (from the text only, never from the extractor's output), and the owner reviews every posting.
  This is faster than labelling from scratch. The risk is that the reviewer anchors on the draft,
  and that the draft's author also wrote the taxonomy aliases, so agreement with the extractor
  may be optimistic. The output records both names, and an F1 on the unreviewed draft is
  reported as provisional only.
- **Syllabus sections after the last unit** ("Text Books", "References", "Online/NPTEL
  courses", "Suggested readings") end the unit. Book titles are not taught content, and they
  inflated coverage on the first real syllabus. These labels end a unit only when followed by
  a colon or alone on a heading-styled line, so "Text mining" stays content.
- **Course codes with two digits** (`CSH01`, `CSM03`) start a course. Outcome labels that look
  like codes (`CO 12`, `PO1`, `PSO2`) are excluded.
- **Taxonomy: ambiguous aliases found on the first real syllabus.** "ruby" (lasers), "bootstrap"
  (the loader) and "system design" (electronic / engineering / file system design) now need
  supporting context, like "go" and "react". This affected 30 stored postings and left the
  provisional F1 unchanged. Known and left: "File system design" next to "caching" /
  "architecture" still counts as System Design, because rejecting it needs a "preceding word"
  rule and a schema change.
- **Taxonomy and role additions after review (2026-11-21, owner request).** Eight skills added
  and none removed or renamed by slug:
  - `unit-testing` (renamed "Unit & Integration Testing") was split. Its automation aliases
    (test automation, automation testing, Selenium, Cypress, Playwright) moved to a new
    `test-automation`, with new aliases automated testing/tests, QA automation, Appium and TestNG.
    `manual-testing`, `exploratory-testing` and `regression-testing` are new, so methodologies
    are no longer read as automation. Tools stay aliases of `test-automation`; they can be split
    into their own skills if their demand is worth tracking separately.
  - `react-native` (parent `react`) and `tailwind-css` (parent `css`) took over the aliases they
    previously shared with their parents. Analytics still count the parent as implied, but
    labels and the F1 use the specific skill.
  - `pega` and `pega-smart-dispute` (parent `pega`) are new, for the Pega roles found in the data.

  One role was added: `software-development-manager`. It covers 36 postings that previously
  had no role, and no posting changed from another role. The other requested role names
  already map to existing families: Senior/Software QA Engineer → `qa-engineer`, Senior MongoDB
  Cloud Engineer → `cloud-engineer`, Software Developer → `software-engineer`. Seniority is not
  a role: splitting families by seniority would leave most of them below the 30-posting
  minimum, and 480 postings (22 %) have a senior/lead/staff title. A separate seniority field
  is the better design. Roles are assigned at ingestion, so `python -m app.cli
  reclassify-roles` re-applies `roles.json` to stored postings.
- **Labelling rules revised by the owner (2026-11-21).** Company-description mentions and role
  names in titles are no longer labelled (data/eval_sets/README.md). The extractor still counts
  both: under the new rule, 66 of 306 DevOps and 59 of 192 machine-learning mentions come only
  from role names in titles. Whether the extractor should ignore role names in titles is open;
  it changes demand shares, so it is the owner's decision.
- **Extraction evaluation (2026-11-21).** The ground truth is scored as delivered: no record is
  skipped or edited, and records with no labels stay in, so every prediction on them is a
  false positive. Micro averages are the headline because they weight every (posting, skill)
  decision equally. Macro averages are reported over all labelled-or-predicted skills and over
  labelled skills only; a zero denominator counts as 0. A 95 % bootstrap interval over postings
  (2,000 resamples, fixed seed) shows how much 120 postings can tell. Reports contain ids,
  slugs and matched alias text only, never posting text. Known issue: the extractor version
  hash includes numeric skill ids, so a seed-built and a database-built extractor with the
  same taxonomy get different version strings. Predictions are unaffected (identical for all
  120 postings). Hashing by slug would fix it, but would also re-extract every posting once.
