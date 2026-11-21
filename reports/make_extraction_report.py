"""Phase 1 extraction evaluation report.

    cd apps/api
    python ../../reports/make_extraction_report.py ../../data/eval_sets/extraction_v1.jsonl

Runs the extractor (the same SkillExtractor.extract call the ingestion pipeline uses) on every
record of the ground-truth file, matches by posting id, and writes
reports/extraction_v1_eval.json and reports/extraction_v1_eval.md.

Also cross-checks the predictions against what the production pipeline stored in the database
for the same postings, when the database is reachable.

The reports contain posting ids, skill slugs and matched alias text only, never titles or
description text (Adzuna content is not republished). The ground-truth file is opened
read-only.
"""

import asyncio
import hashlib
import json
import random
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.extraction.evaluation import LabelledPosting, evaluate, load_eval_set
from app.services.extraction.extractor import SkillExtractor
from app.services.extraction.taxonomy import read_seed, specs_from_seed

OUT = Path(__file__).resolve().parent
# Skills added on 2026-11-21, and the older skills whose aliases they took over.
NEW_SKILLS = {
    "test-automation": "unit-testing",
    "manual-testing": None,
    "exploratory-testing": None,
    "regression-testing": None,
    "react-native": "react",
    "tailwind-css": "css",
    "pega": None,
    "pega-smart-dispute": None,
}
BOOTSTRAP_SAMPLES = 2000
SEED = 20261121


def alias_index() -> dict[str, list[re.Pattern[str]]]:
    out: dict[str, list[re.Pattern[str]]] = {}
    for s in read_seed("skills.json")["skills"]:
        out[s["slug"]] = [
            re.compile(
                rf"(?<![a-z0-9]){re.escape((a if isinstance(a, str) else a['alias']).lower())}"
                r"(?![a-z0-9])"
            )
            for a in s["aliases"]
        ]
    return out


def predictions(extractor: SkillExtractor, item: LabelledPosting) -> dict[str, Any]:
    return {
        s.slug: s
        for s in extractor.extract([("title", item.title), ("description", item.description)])
        if not s.implied
    }


def micro(pairs: list[tuple[set[str], set[str]]]) -> tuple[float, float, float]:
    tp = sum(len(p & g) for p, g in pairs)
    fp = sum(len(p - g) for p, g in pairs)
    fn = sum(len(g - p) for p, g in pairs)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return prec, rec, (2 * prec * rec / (prec + rec) if prec + rec else 0.0)


def bootstrap(pairs: list[tuple[set[str], set[str]]]) -> dict[str, list[float]]:
    """95 % percentile intervals, resampling postings with replacement."""
    rng = random.Random(SEED)  # noqa: S311 - statistics, not security
    samples = [micro([rng.choice(pairs) for _ in pairs]) for _ in range(BOOTSTRAP_SAMPLES)]
    out = {}
    for k, name in enumerate(("precision", "recall", "f1")):
        vals = sorted(s[k] for s in samples)
        out[name] = [
            round(vals[int(0.025 * len(vals))], 4),
            round(vals[int(0.975 * len(vals)) - 1], 4),
        ]
    return out


async def stored_predictions(ids: list[str]) -> dict[str, Any] | None:
    """Non-implied skills the production pipeline stored for these postings."""
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.session import create_engine, create_session_factory
    from app.models import JobPosting, JobSource, PostingSkill, Skill

    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    wanted = {i.split(":", 1)[1]: i for i in ids}
    try:
        async with factory() as s:
            rows = (
                await s.execute(
                    select(
                        JobSource.key,
                        JobPosting.external_id,
                        JobPosting.extractor_version,
                        Skill.slug,
                        PostingSkill.implied,
                    )
                    .join(JobSource, JobSource.id == JobPosting.source_id)
                    .outerjoin(PostingSkill, PostingSkill.posting_id == JobPosting.id)
                    .outerjoin(Skill, Skill.id == PostingSkill.skill_id)
                    .where(JobPosting.external_id.in_(list(wanted)))
                )
            ).all()
    except Exception as exc:  # database not running: the cross-check is skipped, and says so
        return {"error": type(exc).__name__}
    finally:
        await engine.dispose()
    found: dict[str, set[str]] = {}
    version_of: dict[str, str] = {}
    for key, ext, version, slug, implied in rows:
        pid = f"{key}:{ext}"
        if pid not in ids:
            continue
        found.setdefault(pid, set())
        version_of[pid] = version or "none"
        if slug and not implied:
            found[pid].add(slug)
    return {"postings": found, "versions": dict(Counter(version_of.values()))}


def main() -> None:
    path = Path(sys.argv[1])
    data = path.read_bytes()
    specs = specs_from_seed()
    extractor = SkillExtractor(specs)
    items = load_eval_set(path, {s.slug for s in specs})
    report = evaluate(extractor, items)
    aliases = alias_index()

    pred = {i.id: predictions(extractor, i) for i in items}
    pairs = [(set(pred[i.id]), i.skills) for i in items]
    if micro(pairs)[2] != report.f1:  # the bootstrap must count exactly like the report
        raise RuntimeError("bootstrap counting differs from evaluate()")

    # Errors, with a factual category each.
    errors: list[dict[str, Any]] = []
    for it in items:
        p = pred[it.id]
        title = it.title.lower()
        desc = it.description.lower()
        for slug in sorted(set(p) - it.skills):
            ev = p[slug].evidence
            fields = {e.field for e in ev}
            if slug in NEW_SKILLS and NEW_SKILLS[slug] in it.skills:
                cat = "label_uses_older_skill"
            elif slug in NEW_SKILLS:
                cat = "new_skill_not_in_labels"
            elif not it.skills:
                cat = "fp_on_empty_label_record"
            elif fields == {"title"}:
                cat = "title_only_prediction"
            else:
                cat = "other"
            errors.append(
                {
                    "id": it.id,
                    "type": "fp",
                    "skill": slug,
                    "category": cat,
                    "empty_label_record": not it.skills,
                    "matched": sorted({e.text for e in ev})[:3],
                    "fields": sorted(fields),
                }
            )
        for slug in sorted(it.skills - set(p)):
            if any(NEW_SKILLS.get(n) == slug for n in p if n not in it.skills):
                cat = "label_uses_older_skill"
            elif any(r.search(title) or r.search(desc) for r in aliases.get(slug, [])):
                cat = "alias_in_text_but_rejected"
            else:
                cat = "no_alias_in_text"
            errors.append({"id": it.id, "type": "fn", "skill": slug, "category": cat})

    scores = report.skill_scores()
    weakest = sorted(
        ({"skill": k, **v} for k, v in scores.items()),
        key=lambda s: (s["f1"], -(s["fp"] + s["fn"]), s["skill"]),
    )
    weakest = [s for s in weakest if s["fp"] + s["fn"] > 0]

    empty = [i for i in items if not i.skills]
    empty_with_pred = [i.id for i in empty if pred[i.id]]

    # How far the reviewed labels moved from the draft they started from (independence check).
    draft_path = path.with_name("extraction_v1.draft.jsonl")
    draft_agreement: dict[str, Any] | None = None
    if draft_path.exists():
        draft = {
            json.loads(x)["id"]: set(json.loads(x)["skills"])
            for x in draft_path.read_text("utf-8").splitlines()
            if x.strip()
        }
        common = [i for i in items if i.id in draft]
        draft_agreement = {
            "postings_compared": len(common),
            "identical": sum(1 for i in common if i.skills == draft[i.id]),
            "labels_added": sum(len(i.skills - draft[i.id]) for i in common),
            "labels_removed": sum(len(draft[i.id] - i.skills) for i in common),
        }

    stored = asyncio.run(stored_predictions([i.id for i in items]))
    crosscheck: dict[str, Any]
    if stored is None or "error" in stored:
        crosscheck = {"status": "skipped", "reason": (stored or {}).get("error", "no database")}
    else:
        found = stored["postings"]
        same = [i.id for i in items if i.id in found and found[i.id] == set(pred[i.id])]
        crosscheck = {
            "status": "done",
            "postings_found_in_db": len(found),
            "identical_predictions": len(same),
            "differences": [
                {
                    "id": i.id,
                    "db_only": sorted(found[i.id] - set(pred[i.id])),
                    "eval_only": sorted(set(pred[i.id]) - found[i.id]),
                }
                for i in items
                if i.id in found and found[i.id] != set(pred[i.id])
            ],
            "db_extractor_versions": stored["versions"],
        }

    result = {
        "generated_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "ground_truth": {
            "file": path.name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "records": len(items),
            "unique_ids": len({i.id for i in items}),
            "annotations": sum(len(i.skills) for i in items),
            "unique_labels": len({s for i in items for s in i.skills}),
            "empty_label_records": len(empty),
            "labelled_by": dict(
                Counter(
                    json.loads(x)["labelled_by"]
                    for x in data.decode("utf-8").splitlines()
                    if x.strip()
                )
            ),
            "agreement_with_draft": draft_agreement,
            "new_skills_used_in_labels": sorted(
                {s for i in items for s in i.skills} & set(NEW_SKILLS)
            ),
        },
        "records_evaluated": report.postings,
        "records_skipped": len(items) - report.postings,
        "extractor": extractor.version,
        "micro": {
            "precision": round(report.precision, 4),
            "recall": round(report.recall, 4),
            "f1": round(report.f1, 4),
            "tp": report.tp,
            "fp": report.fp,
            "fn": report.fn,
            "ci95_bootstrap": bootstrap(pairs),
        },
        "macro_all_skills": report.macro(),
        "macro_labelled_skills": report.macro(labelled_only=True),
        "per_rule": report.per_rule,
        "per_skill": scores,
        "weakest_skills": weakest[:15],
        "error_categories": dict(Counter(f"{e['type']}:{e['category']}" for e in errors)),
        "empty_label_records": {
            "count": len(empty),
            "with_predictions": len(empty_with_pred),
            "without_predictions": len(empty) - len(empty_with_pred),
            "fp_from_them": sum(1 for e in errors if e.get("empty_label_record")),
            "predicted_skills": dict(
                Counter(e["skill"] for e in errors if e.get("empty_label_record"))
            ),
            "ids_with_predictions": empty_with_pred,
        },
        "pipeline_crosscheck": crosscheck,
        "errors": errors,
    }
    (OUT / "extraction_v1_eval.json").write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    (OUT / "extraction_v1_eval.md").write_text(render_md(result), "utf-8")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "records_evaluated",
                    "records_skipped",
                    "micro",
                    "macro_all_skills",
                    "macro_labelled_skills",
                    "error_categories",
                    "pipeline_crosscheck",
                )
            },
            indent=2,
            default=str,
        )[:4000]
    )


def render_md(r: dict[str, Any]) -> str:
    m, ma, ml = r["micro"], r["macro_all_skills"], r["macro_labelled_skills"]
    g = r["ground_truth"]
    lines = [
        "# Extraction evaluation: extraction_v1",
        "",
        f"Generated {r['generated_at']} by `reports/make_extraction_report.py`. Numbers are"
        " computed, not edited by hand. Detailed data: `extraction_v1_eval.json`.",
        "",
        "## Inputs",
        "",
        f"- Ground truth: `{g['file']}` (not in the repository), sha256 `{g['sha256']}`.",
        f"  {g['records']} records, {g['unique_ids']} unique ids, {g['annotations']} labels over"
        f" {g['unique_labels']} skills, {g['empty_label_records']} records with no labels.",
        f"- Labelled by: {', '.join(f'{k} ({v})' for k, v in g['labelled_by'].items())}.",
        *(
            [
                f"- Independence: {g['agreement_with_draft']['identical']} of"
                f" {g['agreement_with_draft']['postings_compared']} reviewed records are identical"
                f" to the Claude-drafted labels ({g['agreement_with_draft']['labels_added']} labels"
                f" added, {g['agreement_with_draft']['labels_removed']} removed in review). The"
                " drafter also wrote the taxonomy aliases, so this F1 largely measures agreement"
                " between two Claude-authored views of the text, checked by one reviewer."
            ]
            if g["agreement_with_draft"]
            else []
        ),
        f"- Skills added to the taxonomy on 2026-11-21 used in the labels:"
        f" {', '.join(g['new_skills_used_in_labels']) or 'none'}.",
        f"- Extractor: `{r['extractor']}`.",
        f"- Records evaluated: **{r['records_evaluated']}**; skipped: **{r['records_skipped']}**."
        " Records with no labels are evaluated (any prediction on them is a false positive).",
        "",
        "## Results",
        "",
        "| Averaging | Precision | Recall | F1 | Notes |",
        "|---|---|---|---|---|",
        f"| Micro | {m['precision']:.4f} | {m['recall']:.4f} | **{m['f1']:.4f}** |"
        f" TP {m['tp']}, FP {m['fp']}, FN {m['fn']} |",
        f"| Micro, 95 % CI | {m['ci95_bootstrap']['precision'][0]:.3f} to "
        f"{m['ci95_bootstrap']['precision'][1]:.3f} | {m['ci95_bootstrap']['recall'][0]:.3f} to "
        f"{m['ci95_bootstrap']['recall'][1]:.3f} | {m['ci95_bootstrap']['f1'][0]:.3f} to "
        f"{m['ci95_bootstrap']['f1'][1]:.3f} | bootstrap over postings, {BOOTSTRAP_SAMPLES}"
        " samples |",
        f"| Macro, all skills | {ma['precision']:.4f} | {ma['recall']:.4f} | {ma['f1']:.4f} |"
        f" {ma['skills']} skills labelled or predicted |",
        f"| Macro, labelled skills | {ml['precision']:.4f} | {ml['recall']:.4f} |"
        f" {ml['f1']:.4f} | {ml['skills']} skills with ≥ 1 label |",
        "",
        "Per-skill ratios with a zero denominator count as 0 in macro averages.",
        "",
        "## Errors by category",
        "",
        "| Category | Count | Meaning |",
        "|---|---|---|",
    ]
    meaning = {
        "fp:fp_on_empty_label_record": "prediction on a record labelled with no skills",
        "fp:label_uses_older_skill": "extractor uses a 2026-11-21 skill; the label uses the"
        " older skill that held these aliases (unit-testing, react, css)",
        "fp:new_skill_not_in_labels": "extractor finds a 2026-11-21 skill the labels never use",
        "fp:title_only_prediction": "match only in the title",
        "fp:other": "other false positives",
        "fn:label_uses_older_skill": "label is the older skill the extractor now splits",
        "fn:alias_in_text_but_rejected": "an alias occurs, but the extractor rejected it"
        " (context, truncation, case)",
        "fn:no_alias_in_text": "label rests on meaning, not on any alias in the text",
    }
    for k, v in sorted(r["error_categories"].items()):
        lines.append(f"| `{k}` | {v} | {meaning.get(k, '')} |")
    lines += [
        "",
        "## Weakest skills (by F1, then error count)",
        "",
        "| Skill | Support | Predicted | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in r["weakest_skills"]:
        lines.append(
            f"| `{s['skill']}` | {s['support']} | {s['predicted']} | {s['tp']} | {s['fp']} |"
            f" {s['fn']} | {s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} |"
        )
    lines += [
        "",
        "Most skills have fewer than 5 labels, so per-skill scores are indicative only.",
        "",
        "## Records with no labels",
        "",
    ]
    e = r["empty_label_records"]
    lines += [
        f"{e['count']} records have empty skill lists. They were evaluated, not skipped."
        f" The extractor predicts nothing on {e['without_predictions']} of them (true"
        f" negatives) and {e['fp_from_them']} skill(s) on {e['with_predictions']}:"
        f" {', '.join(f'`{k}` x{v}' for k, v in sorted(e['predicted_skills'].items())) or '—'}.",
        "",
        "## Pipeline cross-check",
        "",
    ]
    c = r["pipeline_crosscheck"]
    if c["status"] == "done":
        lines.append(
            f"The production pipeline's stored predictions were compared for"
            f" {c['postings_found_in_db']} of the records: {c['identical_predictions']} identical."
            f" Stored extractor versions: {c['db_extractor_versions']}. The version string differs"
            f" from this report's (`{r['extractor']}`) because the hash includes numeric skill ids,"
            " which differ between the seed file and the database for the skills added on"
            " 2026-11-21. The predictions themselves are identical, as shown above."
        )
    else:
        lines.append(f"Skipped: {c['reason']}.")
    lines += [
        "",
        "## Per-skill results",
        "",
        "| Skill | Support | Predicted | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|",
    ]
    for k, s in sorted(r["per_skill"].items()):
        lines.append(
            f"| `{k}` | {s['support']} | {s['predicted']} | {s['precision']:.2f} |"
            f" {s['recall']:.2f} | {s['f1']:.2f} |"
        )
    lines += [
        "",
        "## Every false positive and false negative",
        "",
        "| Posting | Type | Skill | Category | Matched text |",
        "|---|---|---|---|---|",
    ]
    for x in r["errors"]:
        lines.append(
            f"| {x['id']} | {x['type'].upper()} | `{x['skill']}` | {x['category']} |"
            f" {', '.join(x.get('matched', [])) or ''} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
