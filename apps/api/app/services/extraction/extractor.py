"""Skill extraction v2: PhraseMatcher over the taxonomy with context disambiguation.

Pipeline per text field:
1. A spaCy PhraseMatcher (case-insensitive) finds every alias; overlapping matches keep the
   longest span ("apache spark" beats "spark", "c++" beats "c").
2. Unambiguous aliases are accepted. Ambiguous ones ("go", "react", "lambda", "R") are
   accepted only with supporting evidence, and rejected outright when followed by a negative
   cue ("go to", "react quickly", "excel in"):
   - context_term: one of the skill's context words within WINDOW tokens;
   - skill_list: the mention sits in a delimited list next to another accepted skill;
   - case_and_neighbor: exact-case form ("Go", "React") with another skill nearby.
   Strict aliases (single letters) need the exact case AND context or a skill list.
3. Each accepted mention keeps an evidence span (character offsets in its field), the rule
   that accepted it, and a requirement label (required / nice-to-have / unspecified).
4. Broader skills are added as implied (PostgreSQL -> SQL).

Confidence per rule comes from calibration.json (see that file for its status).
"""

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from importlib import resources
from typing import Any

import spacy
from spacy.matcher import PhraseMatcher
from spacy.tokens import Doc, Span
from spacy.util import filter_spans

from app.services.extraction.requirement import Requirement, RequirementLocator, strongest

# Bump on any change to matching logic, so stored postings are re-extracted.
EXTRACTOR_VERSION = "2.1"
WINDOW = 15
NEIGHBOR_WINDOW = 8
_LIST_BEFORE = frozenset({",", "/", "(", "|", ";", "•", "&", "-", "*", ":", "·", "–"})
_LIST_AFTER = frozenset({",", "/", ")", "|", ";", ".", "&"})


@dataclass(frozen=True)
class AliasSpec:
    alias: str
    requires_context: bool = False
    case_form: str | None = None
    negative_following: tuple[str, ...] = ()
    strict: bool = False


@dataclass(frozen=True)
class SkillSpec:
    id: int
    slug: str
    name: str
    parent_id: int | None = None
    context_terms: tuple[str, ...] = ()
    aliases: tuple[AliasSpec, ...] = ()


@dataclass
class Evidence:
    field: str
    start: int
    end: int
    text: str
    rule: str
    requirement: Requirement

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "rule": self.rule,
            "requirement": self.requirement,
        }


@dataclass
class ExtractedSkill:
    skill_id: int
    slug: str
    confidence: float
    requirement: Requirement
    implied: bool = False
    evidence: list[Evidence] = field(default_factory=list)


def load_calibration() -> dict[str, Any]:
    text = resources.files("app.services.extraction").joinpath("calibration.json").read_text()
    data: dict[str, Any] = json.loads(text)
    return data


def normalize_alias(alias: str) -> str:
    return " ".join(alias.lower().split())


class SkillExtractor:
    def __init__(
        self, skills: Sequence[SkillSpec], calibration: dict[str, Any] | None = None
    ) -> None:
        self.skills = {s.id: s for s in skills}
        self.rule_confidence: dict[str, float] = (calibration or load_calibration())["rules"]
        self.nlp = spacy.blank("en")
        self.matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")
        self._lookup: dict[str, tuple[SkillSpec, AliasSpec]] = {}
        for skill in skills:
            for alias in skill.aliases:
                key = f"{skill.id}|{normalize_alias(alias.alias)}"
                self._lookup[key] = (skill, alias)
                self.matcher.add(key, [self.nlp.make_doc(alias.alias)])
        # Aliases that are the start of another skill's alias ("java" / "javascript",
        # "c" / "c++", "r" / "react"). Cut off by a truncation ellipsis ("Java…"), they may be
        # that other skill, so such matches are dropped (Adzuna snippets end in "…").
        owners: dict[str, set[int]] = {}
        for skill in skills:
            for alias in skill.aliases:
                owners.setdefault(normalize_alias(alias.alias), set()).add(skill.id)
        self._truncation_ambiguous = {
            a
            for a, ids in owners.items()
            if any(o != a and o.startswith(a) and not (owners[o] <= ids) for o in owners)
        }

    @cached_property
    def version(self) -> str:
        """Changes whenever the taxonomy or the calibration changes, so stale rows can be
        re-extracted."""
        h = hashlib.sha256()
        for key in sorted(self._lookup):
            skill, alias = self._lookup[key]
            h.update(repr((key, skill.parent_id, skill.context_terms, alias)).encode())
        h.update(json.dumps(self.rule_confidence, sort_keys=True).encode())
        return f"{EXTRACTOR_VERSION}+{h.hexdigest()[:10]}"

    # ---- matching -------------------------------------------------------------------------

    def _context_hit(self, doc: Doc, span: Span, terms: Iterable[str]) -> bool:
        lo, hi = max(0, span.start - WINDOW), min(len(doc), span.end + WINDOW)
        words = [t.lower_ for t in doc[lo : span.start]] + [t.lower_ for t in doc[span.end : hi]]
        joined = f" {' '.join(words)} "
        for term in terms:
            if f" {term} " in joined:
                return True
            # Multi-token terms ("next.js", "pl/sql") are tokenised like the text.
            tokens = " ".join(t.lower_ for t in self.nlp.make_doc(term))
            if f" {tokens} " in joined:
                return True
        return False

    @staticmethod
    def _in_list(doc: Doc, span: Span) -> bool:
        before = doc[span.start - 1].lower_ if span.start > 0 else "\n"
        after = doc[span.end].lower_ if span.end < len(doc) else "\n"
        return (
            before in _LIST_BEFORE
            or after in _LIST_AFTER
            or before.strip() == ""
            or after.strip() == ""
        )

    def _disambiguate(
        self,
        doc: Doc,
        span: Span,
        skill: SkillSpec,
        alias: AliasSpec,
        anchors: list[int],
    ) -> str | None:
        """Return the rule that accepts an ambiguous mention, or None to reject it."""
        nxt = doc[span.end].lower_ if span.end < len(doc) else ""
        if nxt in alias.negative_following:
            return None
        case_exact = alias.case_form is not None and span.text == alias.case_form
        neighbor = any(abs(a - span.start) <= NEIGHBOR_WINDOW for a in anchors if a != span.start)
        context = self._context_hit(doc, span, skill.context_terms)
        in_list = self._in_list(doc, span) and neighbor
        if alias.strict:
            if not case_exact:
                return None
            if context:
                return "context_term"
            return "skill_list" if in_list else None
        if context:
            return "context_term"
        if in_list:
            return "skill_list"
        if case_exact and neighbor:
            return "case_and_neighbor"
        return None

    def _field_mentions(
        self, field_name: str, text: str, with_requirement: bool
    ) -> list[tuple[SkillSpec, Evidence]]:
        if not text.strip():
            return []
        doc = self.nlp(text)
        spans = filter_spans(
            [Span(doc, start, end, label=mid) for mid, start, end in self.matcher(doc)]
        )
        resolved = [(span, *self._lookup[span.label_]) for span in spans]
        anchors = [span.start for span, _, alias in resolved if not alias.requires_context]
        locator = RequirementLocator(text) if with_requirement else None

        out: list[tuple[SkillSpec, Evidence]] = []
        for span, skill, alias in resolved:
            truncated = text[span.end_char :].startswith(("…", "..."))
            if truncated and normalize_alias(alias.alias) in self._truncation_ambiguous:
                continue
            if alias.requires_context:
                rule = self._disambiguate(doc, span, skill, alias, anchors)
                if rule is None:
                    continue
            else:
                rule = "exact_alias"
            if field_name == "title":
                requirement: Requirement = "required"
            elif locator is not None:
                requirement = locator.label_at(span.start_char)
            else:
                requirement = "unspecified"
            out.append(
                (
                    skill,
                    Evidence(
                        field_name, span.start_char, span.end_char, span.text, rule, requirement
                    ),
                )
            )
        return out

    def confidence_for(self, ev: Evidence) -> float:
        if ev.rule == "exact_alias":
            key = (
                f"exact_alias:{ev.field}"
                if ev.field in ("title", "description")
                else ("exact_alias:other")
            )
            return self.rule_confidence[key]
        return self.rule_confidence[ev.rule]

    # ---- public API -----------------------------------------------------------------------

    def extract(
        self, fields: Sequence[tuple[str, str]], *, with_requirement: bool = True
    ) -> list[ExtractedSkill]:
        """Extract skills from named text fields, e.g. [("title", ...), ("description", ...)]."""
        found: dict[int, ExtractedSkill] = {}
        for field_name, text in fields:
            for skill, ev in self._field_mentions(field_name, text or "", with_requirement):
                conf = self.confidence_for(ev)
                item = found.get(skill.id)
                if item is None:
                    item = found[skill.id] = ExtractedSkill(
                        skill.id, skill.slug, conf, "unspecified"
                    )
                item.evidence.append(ev)
                item.confidence = max(item.confidence, conf)
        for item in found.values():
            item.requirement = strongest([e.requirement for e in item.evidence])

        # Broader skills implied by narrower ones.
        for item in list(found.values()):
            parent_id = self.skills[item.skill_id].parent_id
            seen: set[int] = set()
            while parent_id is not None and parent_id not in seen:
                seen.add(parent_id)
                parent = self.skills.get(parent_id)
                if parent is None:
                    break
                existing = found.get(parent_id)
                if existing is None:
                    found[parent_id] = ExtractedSkill(
                        parent.id,
                        parent.slug,
                        item.confidence,
                        item.requirement,
                        implied=True,
                        evidence=[
                            Evidence(
                                e.field,
                                e.start,
                                e.end,
                                e.text,
                                f"implied_by:{item.slug}",
                                e.requirement,
                            )
                            for e in item.evidence[:3]
                        ],
                    )
                elif existing.implied:
                    existing.confidence = max(existing.confidence, item.confidence)
                    existing.requirement = strongest([existing.requirement, item.requirement])
                parent_id = parent.parent_id
        return sorted(found.values(), key=lambda s: (-s.confidence, s.slug))
