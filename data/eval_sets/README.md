# Evaluation sets

Labelled data used to measure models. Every file here must hold **real** records (e.g.
postings ingested from Adzuna), with labels checked by a person. Never add generated or invented
examples.

## `extraction_v1.jsonl`: skill extraction (Phase 1)

**Done (2026-11-21):** 120 postings reviewed by the owner (MK). The file is local and git-ignored, sha256 `e1da2b1d7f5ab171c311af454be36a3bcf55ae317b2472ff285b060978d5d5a8`. Result: micro F1 0.925, details in `reports/extraction_v1_eval.md`. To reproduce, run from `apps/api`:

```bash
PYTHONPATH=. python ../../reports/make_extraction_report.py ../../data/eval_sets/extraction_v1.jsonl
```

Treat the file as read-only: it is the ground truth the reported numbers refer to.

**Gate (owner decision 2026-11-21):** F1 must be at least **0.89**. The set is private, so the gate runs locally before each phase closes, not in public CI. Record the result in ROADMAP.md and `docs/metrics.md`. From `apps/api`:

```bash
python -m app.cli eval-extraction --path ../../data/eval_sets/extraction_v1.jsonl --min-f1 0.89
```

A non-zero exit code means the gate failed.

**Approved process (owner, 2026-11-20):** Claude drafts the labels blind, from the posting text
only and without the extractor's output. The owner then reviews and corrects every posting in
the labelling page. The draft is `extraction_v1.draft.jsonl` (120 postings, git-ignored), and
each row carries `draft_by` and, where a call was borderline, `notes`. A file produced this way
records `labelled_by: "claude (draft), reviewed by <initials>"`. An F1 computed on the
unreviewed draft is provisional only.

### Review the draft

```bash
python data/eval_sets/make_labeller.py data/eval_sets/extraction_v1.draft.jsonl
```

Open `data/eval_sets/labeller.html`. Each posting opens with the draft labels selected. A yellow
box lists **review flags**: hints computed from the text and the taxonomy, which never change a
label on their own. A flag appears when:
- a selected skill's aliases occur nowhere in the text;
- a selected skill occurs only in the title;
- a skill added to the taxonomy after the draft is mentioned (see `TAXONOMY_CHANGES` in
  `make_labeller.py`);
- the draft carries a note, including notes on rules that changed after drafting.

Fix the labels, then click **Mark reviewed & next** (key `r`). Other controls:
- `n` jumps to the next unreviewed posting and `f` to the next flagged one.
- `/` focuses skill search, and Enter adds the first match.
- The coloured strip under the header shows every posting's status.
- "Highlight selected skills" marks their aliases in the text.

**Download JSONL** writes one row per non-excluded posting, in the same six fields as before.
Rows you haven't reviewed are written with `labelled_by: "claude (draft), not reviewed"`, so the
F1 is final only when no such row remains. **Load JSONL** restores labels from a downloaded
file, for example on another browser. Progress is kept in the browser under a key derived from
the input file name, so rebuilding the page after a taxonomy change keeps all work. Save the
download as `data/eval_sets/extraction_v1.jsonl`.

### 1. Export a sample

Already done (2026-11-18): 120 real Adzuna postings, seed 20261118, in
`extraction_v1.unlabelled.jsonl`. To re-create it:

```bash
cd apps/api
python -m app.cli export-eval-sample --n 120 --seed 20261118   --out ../../data/eval_sets/extraction_v1.unlabelled.jsonl
```

The `.unlabelled` name matters: CI runs the F1 gate as soon as `extraction_v1.jsonl` exists.

### Labelling page

```bash
python data/eval_sets/make_labeller.py data/eval_sets/extraction_v1.unlabelled.jsonl
```

Open `data/eval_sets/labeller.html` in a browser. Label each posting (searchable skill list,
arrow keys to move, progress autosaved in the browser), enter your initials, then click
**Download JSONL** and save it as `data/eval_sets/extraction_v1.jsonl`. The page does not show
what the extractor found, so the labels are independent of it.

### Licence check before committing the labelled file

The labelled file contains Adzuna description snippets. The unlabelled file and the labelling
page are git-ignored for that reason. Before committing `extraction_v1.jsonl` to the public
repository, check that Adzuna's terms allow republishing snippets. If they don't, keep the set
private (e.g. a CI secret or a private artifact) and commit only the report.

### 2. Label each posting (by hand)

Fill `skills` with the taxonomy **slugs** (see `GET /api/v1/skills` or
`apps/api/app/seed/data/skills.json`) of every skill the posting mentions in the title or
description, then set `labelled_by` (initials) and `labelled_at` (date).

Rules (revised by the owner on 2026-11-21; the earlier rules on company descriptions and
role titles are replaced):
- Label only skills explicitly mentioned. Never infer skills from what the job probably needs:
  "Data Engineer" alone does not imply Spark.
- A role name in the title is not a skill mention: "DevOps Engineer" is not `devops`,
  "ML Engineer" is not `machine-learning`, "Data Analyst" is not `data-analysis`. A technology
  named in the title is a mention: "Frontend Developer (React / Angular)" → `react`, `angular`.
- Mentions that only describe the company ("we are a Snowflake partner", "a leader in
  cybersecurity") are not labelled. The extractor cannot tell these sections apart, so such
  matches count as its false positives. That is intended: the F1 measures what the analytics
  need.
- Label the most specific skill mentioned: "PostgreSQL" → `postgresql`, not `sql`. Broader
  skills implied by a narrower one (PostgreSQL → SQL) are **not** labelled and not scored.
  The same goes for "React Native" → `react-native` (not `react`), "Tailwind CSS" →
  `tailwind-css` (not `css`) and "Pega Smart Dispute" → `pega-smart-dispute` (not `pega`).
- Testing: manual, exploratory and regression testing (`manual-testing`,
  `exploratory-testing`, `regression-testing`) are methodologies, not test automation.
  `test-automation` is for automation itself ("test automation", "automated tests", Selenium,
  Cypress, Playwright). `unit-testing` is unit and integration testing (pytest, JUnit, Jest,
  TDD).
- Label `sql` only when SQL itself is mentioned.
- Ambiguous words count only when they mean the skill: "react to incidents" is not `react`;
  "Go developer" is `go`; "go through code reviews" is not. "Networking" in a data-centre
  description (servers, storage, networking, power) is equipment, not `networking`.
- Words inside a product name are not separate skills: "Snowflake Data Warehouse" is
  `snowflake` only, and "Databricks Unified Data Analytics Platform" is `databricks` only.
- The meaning counts, not the alias list: "data lakehouse" is not `databricks`, a component
  library called "UIkit" is not `ios`, "Oracle ERP" and "Oracle Cloud" are not
  `oracle-database`. "Containerization" / "containerized" is `docker`, as the taxonomy defines.
- Words cut off by the snippet's "…" are not labelled.
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
