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
