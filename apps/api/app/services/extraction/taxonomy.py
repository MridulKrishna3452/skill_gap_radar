"""Load taxonomy specs for the extractor, from the database or from the seed file."""

import json
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Skill
from app.services.extraction.extractor import AliasSpec, SkillExtractor, SkillSpec


def read_seed(name: str) -> dict[str, Any]:
    text = resources.files("app.seed").joinpath("data", name).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def alias_spec(raw: str | dict[str, Any]) -> AliasSpec:
    if isinstance(raw, str):
        return AliasSpec(alias=raw)
    return AliasSpec(
        alias=raw["alias"],
        requires_context=bool(raw.get("requires_context", False)),
        case_form=raw.get("case_form"),
        negative_following=tuple(w.lower() for w in raw.get("negative_following", [])),
        strict=bool(raw.get("strict", False)),
    )


def specs_from_seed() -> list[SkillSpec]:
    """Specs straight from skills.json, ids assigned by position. Used by tests and evaluation
    when no database is available."""
    raw = read_seed("skills.json")["skills"]
    ids = {s["slug"]: i + 1 for i, s in enumerate(raw)}
    return [
        SkillSpec(
            id=ids[s["slug"]],
            slug=s["slug"],
            name=s["name"],
            parent_id=ids[s["parent"]] if s.get("parent") else None,
            context_terms=tuple(t.lower() for t in s.get("context_terms", [])),
            aliases=tuple(alias_spec(a) for a in s["aliases"]),
        )
        for s in raw
    ]


async def load_specs(session: AsyncSession) -> list[SkillSpec]:
    rows = (
        await session.scalars(
            select(Skill).where(Skill.extractable.is_(True)).options(selectinload(Skill.aliases))
        )
    ).all()
    return [
        SkillSpec(
            id=s.id,
            slug=s.slug,
            name=s.name,
            parent_id=s.parent_id,
            context_terms=tuple(s.context_terms),
            aliases=tuple(
                AliasSpec(
                    alias=a.alias,
                    requires_context=a.requires_context,
                    case_form=a.case_sensitive_form,
                    negative_following=tuple(a.negative_following),
                    strict=a.strict,
                )
                for a in sorted(s.aliases, key=lambda a: a.alias_normalized)
            ),
        )
        for s in sorted(rows, key=lambda s: s.id)
    ]


_cache: dict[tuple[SkillSpec, ...], SkillExtractor] = {}


async def get_extractor(session: AsyncSession) -> SkillExtractor:
    """One compiled extractor per distinct taxonomy, reused across calls in a process."""
    specs = tuple(await load_specs(session))
    extractor = _cache.get(specs)
    if extractor is None:
        _cache.clear()
        extractor = _cache[specs] = SkillExtractor(specs)
    return extractor
