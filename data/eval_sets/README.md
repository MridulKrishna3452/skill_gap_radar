# Evaluation sets

Hand-labelled data used to measure models. Every file here must hold **real** records (e.g.
postings ingested from Adzuna), labelled by a person. Never add generated or invented examples.

## `extraction_v1.jsonl`: skill extraction (Phase 1)

Not created yet: it needs real postings in the database first (Adzuna key or a licensed
dataset). Target: at least 100 postings.

### 1. Export a sample

```bash
cd apps/api
python -m app.cli export-eval-sample --n 120 --out ../../data/eval_sets/extraction_v1.jsonl
```

Each line has `id`, `title`, `description`, an empty `skills` list and empty `labelled_by` /
`labelled_at` fields.

### 2. Label each posting (by hand)

Fill `skills` with the taxonomy **slugs** (see `GET /api/v1/skills` or
`apps/api/app/seed/data/skills.json`) of every skill the posting mentions in the title or
description, then set `labelled_by` (initials) and `labelled_at` (date).

Rules:
- Label what the text says, not what the job probably needs. "Data Engineer" alone does not
  imply Spark.
- Label the most specific skill mentioned: "PostgreSQL" → `postgresql`, not `sql`. Broader
  skills implied by a narrower one (PostgreSQL → SQL) are **not** labelled and not scored.
- Label `sql` only when SQL itself is mentioned.
- Ambiguous words count only when they mean the skill: "react to incidents" is not `react`;
  "Go developer" is `go`; "go through code reviews" is not.
- Skills outside the taxonomy are ignored (note them in a `notes` field if useful; they are
  candidates for taxonomy additions).
- Remove a posting from the file if its text is empty or not a job ad, and say so in the commit.

### 3. Measure

```bash
python -m app.cli eval-extraction --path ../../data/eval_sets/extraction_v1.jsonl --errors \
  --report ../../data/eval_sets/extraction_v1.report.json
```

This prints micro precision / recall / F1, per-skill and per-rule counts, and every false
positive and negative. Record the F1 in ROADMAP.md (Phase 1), agree the CI gate threshold, and
set `EXTRACTION_MIN_F1` in the CI workflow.

### 4. Calibrate confidence (optional, after measuring)

```bash
python -m app.cli eval-extraction --path ../../data/eval_sets/extraction_v1.jsonl --calibrate
```

Rewrites `apps/api/app/services/extraction/calibration.json`: each rule's confidence becomes
its measured precision (Laplace-smoothed), for rules with at least 10 predictions. Commit the
file, then run `python -m app.cli reextract` so stored postings use the new values. Because the
same set is used for calibration and measurement, keep a held-out part of the set (or a second
file) if you want an unbiased F1 after calibrating.
