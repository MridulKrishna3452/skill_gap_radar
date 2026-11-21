"""Evaluation and calibration mechanics on a tiny hand-made set (not the real eval set)."""

import json
from pathlib import Path

import pytest

from app.services.extraction.evaluation import (
    MIN_RULE_SUPPORT,
    LabelledPosting,
    calibrate,
    evaluate,
    load_eval_set,
)
from app.services.extraction.extractor import SkillExtractor, load_calibration
from app.services.extraction.taxonomy import specs_from_seed


@pytest.fixture(scope="module")
def extractor() -> SkillExtractor:
    return SkillExtractor(specs_from_seed())


def test_precision_recall_f1(extractor: SkillExtractor) -> None:
    items = [
        # predicted {python, sql}; gold {python, docker} -> tp 1, fp 1, fn 1
        LabelledPosting("1", "", "Python and SQL", {"python", "docker"}),
        # predicted {kafka}; gold {kafka} -> tp 1
        LabelledPosting("2", "", "Kafka", {"kafka"}),
    ]
    r = evaluate(extractor, items)
    assert (r.tp, r.fp, r.fn) == (2, 1, 1)
    assert r.precision == pytest.approx(2 / 3)
    assert r.recall == pytest.approx(2 / 3)
    assert r.f1 == pytest.approx(2 / 3)
    assert r.per_skill["docker"] == {"fn": 1}

    # Per skill, hand-computed: python 1/1/1, sql (FP only) 0/0/0, docker (FN only) 0/0/0,
    # kafka 1/1/1.
    s = r.skill_scores()
    assert s["python"] == {
        "tp": 1,
        "fp": 0,
        "fn": 0,
        "support": 1,
        "predicted": 1,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }
    assert (s["sql"]["support"], s["sql"]["precision"], s["sql"]["f1"]) == (0, 0.0, 0.0)
    assert (s["docker"]["predicted"], s["docker"]["recall"]) == (0, 0.0)
    # Macro over all 4 labelled-or-predicted skills: (1 + 0 + 0 + 1) / 4.
    assert r.macro() == {"skills": 4, "precision": 0.5, "recall": 0.5, "f1": 0.5}
    # Macro over the 3 labelled skills (python, docker, kafka): (1 + 0 + 1) / 3.
    assert r.macro(labelled_only=True) == {
        "skills": 3,
        "precision": 0.6667,
        "recall": 0.6667,
        "f1": 0.6667,
    }


def test_implied_skills_are_not_scored(extractor: SkillExtractor) -> None:
    r = evaluate(extractor, [LabelledPosting("1", "", "PostgreSQL", {"postgresql"})])
    assert (r.tp, r.fp, r.fn) == (1, 0, 0)  # implied SQL is not a false positive


def test_calibration_uses_smoothed_precision_with_enough_support(extractor: SkillExtractor) -> None:
    items = [LabelledPosting(str(i), "", "Python", {"python"}) for i in range(MIN_RULE_SUPPORT)]
    items.append(LabelledPosting("x", "", "Python", set()))  # one false positive
    report = evaluate(extractor, items)
    new = calibrate(report, load_calibration(), "tiny")
    n = MIN_RULE_SUPPORT + 1
    assert new["rules"]["exact_alias:description"] == round((MIN_RULE_SUPPORT + 1) / (n + 2), 4)
    assert new["status"] == "calibrated"
    # Rules without enough support keep their prior value.
    assert new["rules"]["context_term"] == load_calibration()["rules"]["context_term"]


def test_load_rejects_unknown_slugs(tmp_path: Path) -> None:
    f = tmp_path / "set.jsonl"
    f.write_text(json.dumps({"id": "1", "title": "", "description": "", "skills": ["nope"]}))
    with pytest.raises(ValueError, match="unknown skill slugs"):
        load_eval_set(f, {"python"})


def test_load_rejects_duplicate_postings(tmp_path: Path) -> None:
    row = json.dumps({"id": "1", "title": "", "description": "", "skills": ["python"]})
    f = tmp_path / "set.jsonl"
    f.write_text(f"{row}\n{row}\n")
    with pytest.raises(ValueError, match="duplicate posting id 1"):
        load_eval_set(f, {"python"})


def test_shipped_calibration_is_honest_about_its_status() -> None:
    cal = load_calibration()
    assert cal["status"] in ("prior", "calibrated")
    if cal["status"] == "prior":
        assert cal["measured_on"] is None
    assert all(0 < v <= 1 for v in cal["rules"].values())
