"""Extraction evaluation against a hand-labelled set, and confidence calibration.

Eval set format (JSONL, one posting per line):

    {"id": "adzuna:123", "title": "...", "description": "...",
     "skills": ["python", "sql"], "labelled_by": "initials", "labelled_at": "2026-11-20"}

`skills` are the taxonomy slugs the posting explicitly asks for or mentions as a skill
(labelling guide: data/eval_sets/README.md). Implied parent skills are not labelled and are
not scored. Metrics are micro-averaged over (posting, skill) pairs.

Calibration sets each rule's confidence to its measured precision on the set, Laplace-smoothed
((tp + 1) / (n + 2)), for rules with at least MIN_RULE_SUPPORT predictions; other rules keep
their prior value.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.extraction.extractor import ExtractedSkill, SkillExtractor

MIN_RULE_SUPPORT = 10


@dataclass
class LabelledPosting:
    id: str
    title: str
    description: str
    skills: set[str]


@dataclass
class EvalReport:
    postings: int
    tp: int
    fp: int
    fn: int
    per_skill: dict[str, dict[str, int]]
    per_rule: dict[str, dict[str, int]]
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def skill_scores(self) -> dict[str, dict[str, Any]]:
        """Per skill: counts, support (ground-truth labels) and precision / recall / F1.
        A ratio with a zero denominator is 0.0 (no predictions, or no labels)."""
        out: dict[str, dict[str, Any]] = {}
        for slug, c in self.per_skill.items():
            tp, fp, fn = c.get("tp", 0), c.get("fp", 0), c.get("fn", 0)
            p = tp / (tp + fp) if tp + fp else 0.0
            r = tp / (tp + fn) if tp + fn else 0.0
            f = 2 * p * r / (p + r) if p + r else 0.0
            out[slug] = {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "support": tp + fn,
                "predicted": tp + fp,
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f, 4),
            }
        return out

    def macro(self, *, labelled_only: bool = False) -> dict[str, Any]:
        """Unweighted mean over skills: every skill that was labelled or predicted, or (with
        labelled_only) only skills with at least one ground-truth label."""
        scores = [s for s in self.skill_scores().values() if not labelled_only or s["support"] > 0]
        n = len(scores)

        def mean(key: str) -> float:
            return round(sum(s[key] for s in scores) / n, 4) if n else 0.0

        return {
            "skills": n,
            "precision": mean("precision"),
            "recall": mean("recall"),
            "f1": mean("f1"),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "postings": self.postings,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "macro": self.macro(),
            "macro_labelled_skills": self.macro(labelled_only=True),
            "per_rule": self.per_rule,
            "per_skill": self.skill_scores(),
        }


def load_eval_set(path: Path, known_slugs: set[str]) -> list[LabelledPosting]:
    items: list[LabelledPosting] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            if str(raw["id"]) in seen:
                raise ValueError(f"{path.name} line {n}: duplicate posting id {raw['id']}")
            seen.add(str(raw["id"]))
            unknown = set(raw["skills"]) - known_slugs
            if unknown:
                raise ValueError(f"{path.name} line {n}: unknown skill slugs {sorted(unknown)}")
            items.append(
                LabelledPosting(
                    str(raw["id"]), raw["title"], raw["description"], set(raw["skills"])
                )
            )
    return items


def _deciding_rule(skill: ExtractedSkill, extractor: SkillExtractor) -> str:
    """The rule that produced the skill's confidence (its strongest evidence)."""
    best = max(skill.evidence, key=extractor.confidence_for)
    if best.rule == "exact_alias":
        return f"exact_alias:{best.field}"
    return best.rule


def evaluate(extractor: SkillExtractor, items: Iterable[LabelledPosting]) -> EvalReport:
    tp = fp = fn = 0
    per_skill: dict[str, Counter[str]] = defaultdict(Counter)
    per_rule: dict[str, Counter[str]] = defaultdict(Counter)
    errors: list[dict[str, Any]] = []
    count = 0
    for item in items:
        count += 1
        predicted = {
            s.slug: s
            for s in extractor.extract([("title", item.title), ("description", item.description)])
            if not s.implied
        }
        for slug, skill in predicted.items():
            rule = _deciding_rule(skill, extractor)
            if slug in item.skills:
                tp += 1
                per_skill[slug]["tp"] += 1
                per_rule[rule]["tp"] += 1
            else:
                fp += 1
                per_skill[slug]["fp"] += 1
                per_rule[rule]["fp"] += 1
                errors.append(
                    {
                        "id": item.id,
                        "type": "fp",
                        "skill": slug,
                        "evidence": [e.text for e in skill.evidence[:3]],
                    }
                )
        for slug in item.skills - predicted.keys():
            fn += 1
            per_skill[slug]["fn"] += 1
            errors.append({"id": item.id, "type": "fn", "skill": slug})
    return EvalReport(
        postings=count,
        tp=tp,
        fp=fp,
        fn=fn,
        per_skill={k: dict(v) for k, v in sorted(per_skill.items())},
        per_rule={k: dict(v) for k, v in sorted(per_rule.items())},
        errors=errors,
    )


def calibrate(report: EvalReport, current: dict[str, Any], eval_set_name: str) -> dict[str, Any]:
    rules = dict(current["rules"])
    calibrated_rules = []
    for rule, c in report.per_rule.items():
        n = c.get("tp", 0) + c.get("fp", 0)
        if rule in rules and n >= MIN_RULE_SUPPORT:
            rules[rule] = round((c.get("tp", 0) + 1) / (n + 2), 4)
            calibrated_rules.append(rule)
    return {
        "_comment": current.get("_comment", ""),
        "status": "calibrated" if calibrated_rules else "prior",
        "measured_on": {
            "eval_set": eval_set_name,
            "postings": report.postings,
            "calibrated_rules": sorted(calibrated_rules),
            "min_rule_support": MIN_RULE_SUPPORT,
            "at": datetime.now(tz=UTC).date().isoformat(),
        },
        "rules": rules,
    }
