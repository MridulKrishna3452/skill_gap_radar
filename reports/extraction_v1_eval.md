# Extraction evaluation: extraction_v1

Generated 2026-11-21T13:09:56+00:00 by `reports/make_extraction_report.py`. Numbers are computed, not edited by hand. Detailed data: `extraction_v1_eval.json`.

## Inputs

- Ground truth: `extraction_v1.jsonl` (not in the repository), sha256 `e1da2b1d7f5ab171c311af454be36a3bcf55ae317b2472ff285b060978d5d5a8`.
  120 records, 120 unique ids, 210 labels over 65 skills, 44 records with no labels.
- Labelled by: claude (draft), reviewed by MK (120).
- Independence: 118 of 120 reviewed records are identical to the Claude-drafted labels (0 labels added, 2 removed in review). The drafter also wrote the taxonomy aliases, so this F1 largely measures agreement between two Claude-authored views of the text, checked by one reviewer.
- Skills added to the taxonomy on 2026-11-21 used in the labels: none.
- Extractor: `2.1+449ecffeb7`.
- Records evaluated: **120**; skipped: **0**. Records with no labels are evaluated (any prediction on them is a false positive).

## Results

| Averaging | Precision | Recall | F1 | Notes |
|---|---|---|---|---|
| Micro | 0.9083 | 0.9429 | **0.9252** | TP 198, FP 20, FN 12 |
| Micro, 95 % CI | 0.861 to 0.950 | 0.911 to 0.971 | 0.893 to 0.953 | bootstrap over postings, 2000 samples |
| Macro, all skills | 0.8254 | 0.8212 | 0.8119 | 73 skills labelled or predicted |
| Macro, labelled skills | 0.9270 | 0.9223 | 0.9119 | 65 skills with ≥ 1 label |

Per-skill ratios with a zero denominator count as 0 in macro averages.

## Errors by category

| Category | Count | Meaning |
|---|---|---|
| `fn:alias_in_text_but_rejected` | 2 | an alias occurs, but the extractor rejected it (context, truncation, case) |
| `fn:label_uses_older_skill` | 4 | label is the older skill the extractor now splits |
| `fn:no_alias_in_text` | 6 | label rests on meaning, not on any alias in the text |
| `fp:label_uses_older_skill` | 8 | extractor uses a 2026-11-21 skill; the label uses the older skill that held these aliases (unit-testing, react, css) |
| `fp:new_skill_not_in_labels` | 5 | extractor finds a 2026-11-21 skill the labels never use |
| `fp:other` | 7 | other false positives |

## Weakest skills (by F1, then error count)

| Skill | Support | Predicted | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `test-automation` | 0 | 5 | 0 | 5 | 0 | 0.00 | 0.00 | 0.00 |
| `react-native` | 0 | 2 | 0 | 2 | 0 | 0.00 | 0.00 | 0.00 |
| `regression-testing` | 0 | 2 | 0 | 2 | 0 | 0.00 | 0.00 | 0.00 |
| `agile` | 0 | 1 | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 |
| `deep-learning` | 1 | 0 | 0 | 0 | 1 | 0.00 | 0.00 | 0.00 |
| `excel` | 1 | 0 | 0 | 0 | 1 | 0.00 | 0.00 | 0.00 |
| `exploratory-testing` | 0 | 1 | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 |
| `manual-testing` | 0 | 1 | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 |
| `pega-smart-dispute` | 0 | 1 | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 |
| `r` | 1 | 0 | 0 | 0 | 1 | 0.00 | 0.00 | 0.00 |
| `tailwind-css` | 0 | 1 | 0 | 1 | 0 | 0.00 | 0.00 | 0.00 |
| `unit-testing` | 5 | 1 | 1 | 0 | 4 | 1.00 | 0.20 | 0.33 |
| `networking` | 4 | 1 | 1 | 0 | 3 | 1.00 | 0.25 | 0.40 |
| `data-analysis` | 2 | 5 | 2 | 3 | 0 | 0.40 | 1.00 | 0.57 |
| `data-warehousing` | 1 | 2 | 1 | 1 | 0 | 0.50 | 1.00 | 0.67 |

Most skills have fewer than 5 labels, so per-skill scores are indicative only.

## Records with no labels

44 records have empty skill lists. They were evaluated, not skipped. The extractor predicts nothing on 42 of them (true negatives) and 4 skill(s) on 2: `exploratory-testing` x1, `manual-testing` x1, `pega-smart-dispute` x1, `regression-testing` x1.

## Pipeline cross-check

The production pipeline's stored predictions were compared for 120 of the records: 120 identical. Stored extractor versions: {'2.1+b778332400': 120}. The version string differs from this report's (`2.1+449ecffeb7`) because the hash includes numeric skill ids, which differ between the seed file and the database for the skills added on 2026-11-21. The predictions themselves are identical, as shown above.

## Per-skill results

| Skill | Support | Predicted | Precision | Recall | F1 |
|---|---|---|---|---|---|
| `agile` | 0 | 1 | 0.00 | 0.00 | 0.00 |
| `airflow` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `angular` | 4 | 4 | 1.00 | 1.00 | 1.00 |
| `ansible` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `aws` | 6 | 5 | 1.00 | 0.83 | 0.91 |
| `azure` | 7 | 7 | 1.00 | 1.00 | 1.00 |
| `ci-cd` | 7 | 7 | 1.00 | 1.00 | 1.00 |
| `computer-vision` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `csharp` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `css` | 6 | 6 | 1.00 | 1.00 | 1.00 |
| `cybersecurity` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `data-analysis` | 2 | 5 | 0.40 | 1.00 | 0.57 |
| `data-visualization` | 2 | 2 | 1.00 | 1.00 | 1.00 |
| `data-warehousing` | 1 | 2 | 0.50 | 1.00 | 0.67 |
| `databricks` | 6 | 7 | 0.86 | 1.00 | 0.92 |
| `deep-learning` | 1 | 0 | 0.00 | 0.00 | 0.00 |
| `devops` | 20 | 20 | 1.00 | 1.00 | 1.00 |
| `docker` | 5 | 5 | 1.00 | 1.00 | 1.00 |
| `dotnet` | 3 | 3 | 1.00 | 1.00 | 1.00 |
| `etl` | 15 | 15 | 1.00 | 1.00 | 1.00 |
| `excel` | 1 | 0 | 0.00 | 0.00 | 0.00 |
| `exploratory-testing` | 0 | 1 | 0.00 | 0.00 | 0.00 |
| `fastapi` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `flutter` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `gcp` | 4 | 4 | 1.00 | 1.00 | 1.00 |
| `generative-ai` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `git` | 3 | 3 | 1.00 | 1.00 | 1.00 |
| `github-actions` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `go` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `grafana` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `hadoop` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `html` | 6 | 6 | 1.00 | 1.00 | 1.00 |
| `infrastructure-as-code` | 3 | 3 | 1.00 | 1.00 | 1.00 |
| `ios` | 1 | 2 | 0.50 | 1.00 | 0.67 |
| `java` | 5 | 5 | 1.00 | 1.00 | 1.00 |
| `javascript` | 6 | 6 | 1.00 | 1.00 | 1.00 |
| `jenkins` | 4 | 4 | 1.00 | 1.00 | 1.00 |
| `kafka` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `kubernetes` | 4 | 4 | 1.00 | 1.00 | 1.00 |
| `linux` | 2 | 2 | 1.00 | 1.00 | 1.00 |
| `llms` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `machine-learning` | 4 | 4 | 1.00 | 1.00 | 1.00 |
| `manual-testing` | 0 | 1 | 0.00 | 0.00 | 0.00 |
| `mongodb` | 3 | 3 | 1.00 | 1.00 | 1.00 |
| `networking` | 4 | 1 | 1.00 | 0.25 | 0.40 |
| `nextjs` | 2 | 2 | 1.00 | 1.00 | 1.00 |
| `nodejs` | 3 | 3 | 1.00 | 1.00 | 1.00 |
| `oop` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `pega-smart-dispute` | 0 | 1 | 0.00 | 0.00 | 0.00 |
| `php` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `pyspark` | 3 | 3 | 1.00 | 1.00 | 1.00 |
| `python` | 8 | 8 | 1.00 | 1.00 | 1.00 |
| `pytorch` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `r` | 1 | 0 | 0.00 | 0.00 | 0.00 |
| `react` | 8 | 8 | 1.00 | 1.00 | 1.00 |
| `react-native` | 0 | 2 | 0.00 | 0.00 | 0.00 |
| `regression-testing` | 0 | 2 | 0.00 | 0.00 | 0.00 |
| `rest-api` | 3 | 2 | 1.00 | 0.67 | 0.80 |
| `scala` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `snowflake` | 3 | 3 | 1.00 | 1.00 | 1.00 |
| `spark` | 2 | 2 | 1.00 | 1.00 | 1.00 |
| `spring-boot` | 2 | 2 | 1.00 | 1.00 | 1.00 |
| `sql` | 5 | 5 | 1.00 | 1.00 | 1.00 |
| `sql-server` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `statistics` | 2 | 2 | 1.00 | 1.00 | 1.00 |
| `system-design` | 3 | 3 | 1.00 | 1.00 | 1.00 |
| `t-sql` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `tailwind-css` | 0 | 1 | 0.00 | 0.00 | 0.00 |
| `tensorflow` | 1 | 1 | 1.00 | 1.00 | 1.00 |
| `terraform` | 2 | 2 | 1.00 | 1.00 | 1.00 |
| `test-automation` | 0 | 5 | 0.00 | 0.00 | 0.00 |
| `typescript` | 2 | 2 | 1.00 | 1.00 | 1.00 |
| `unit-testing` | 5 | 1 | 1.00 | 0.20 | 0.33 |

## Every false positive and false negative

| Posting | Type | Skill | Category | Matched text |
|---|---|---|---|---|
| adzuna:5961418105 | FN | `networking` | no_alias_in_text |  |
| adzuna:5954483928 | FP | `data-analysis` | other | Data Analytics |
| adzuna:5902914061 | FN | `networking` | no_alias_in_text |  |
| adzuna:5959429307 | FP | `pega-smart-dispute` | new_skill_not_in_labels | Pega Smart Dispute |
| adzuna:5944177246 | FP | `exploratory-testing` | new_skill_not_in_labels | exploratory testing |
| adzuna:5944177246 | FP | `manual-testing` | new_skill_not_in_labels | manual testing |
| adzuna:5944177246 | FP | `regression-testing` | new_skill_not_in_labels | regression testing |
| adzuna:5946349353 | FP | `test-automation` | label_uses_older_skill | automation testing |
| adzuna:5946349353 | FN | `unit-testing` | label_uses_older_skill |  |
| adzuna:5879362894 | FN | `networking` | no_alias_in_text |  |
| adzuna:5923201958 | FP | `react-native` | label_uses_older_skill | React Native |
| adzuna:5923201958 | FP | `tailwind-css` | label_uses_older_skill | Tailwind CSS |
| adzuna:5961897574 | FN | `excel` | alias_in_text_but_rejected |  |
| adzuna:5949483559 | FP | `test-automation` | label_uses_older_skill | automated tests |
| adzuna:5949483559 | FN | `unit-testing` | label_uses_older_skill |  |
| adzuna:5926966081 | FP | `agile` | other | agile |
| adzuna:5849302904 | FP | `test-automation` | label_uses_older_skill | automated tests |
| adzuna:5849302904 | FN | `unit-testing` | label_uses_older_skill |  |
| adzuna:5911414922 | FN | `rest-api` | no_alias_in_text |  |
| adzuna:5905904588 | FP | `data-warehousing` | other | Data Warehouse |
| adzuna:5906871921 | FP | `test-automation` | label_uses_older_skill | QA Automation, test automation |
| adzuna:5906871921 | FN | `unit-testing` | label_uses_older_skill |  |
| adzuna:5930115525 | FP | `ios` | other | UIkit |
| adzuna:5967007439 | FP | `regression-testing` | new_skill_not_in_labels | Regression Testing |
| adzuna:5967007439 | FP | `test-automation` | label_uses_older_skill | Selenium |
| adzuna:5905895062 | FP | `data-analysis` | other | Data Analytics |
| adzuna:5908341337 | FP | `databricks` | other | lakehouse |
| adzuna:5887915437 | FN | `r` | alias_in_text_but_rejected |  |
| adzuna:5923259529 | FP | `react-native` | label_uses_older_skill | React Native |
| adzuna:5946784801 | FP | `data-analysis` | other | data analysis |
| adzuna:5946784801 | FN | `deep-learning` | no_alias_in_text |  |
| adzuna:5957258378 | FN | `aws` | no_alias_in_text |  |
