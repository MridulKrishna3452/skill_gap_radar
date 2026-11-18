"""Link the curated taxonomy to ESCO, from the official ESCO skills CSV (skills_en.csv).

Download the CSV from https://esco.ec.europa.eu/en/use-esco/download (ESCO is published by
the European Commission; check the licence terms shown there). Columns used: conceptUri,
preferredLabel, altLabels (newline-separated), description.

A curated skill gets an ESCO URI only when exactly one ESCO concept has a preferred or
alternative label equal (case-insensitive) to the skill's name or one of its aliases.
Nothing is guessed. With include_unlinked, the remaining ESCO concepts are added as
reference skills (extractable = false), so the extractor still uses only the curated set.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Skill
from app.services.extraction.extractor import normalize_alias


@dataclass
class EscoResult:
    concepts: int
    linked: int
    ambiguous: int
    added_reference: int


def read_esco(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"conceptUri", "preferredLabel"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"Not an ESCO skills CSV: needs columns {sorted(required)}")
        return list(reader)


async def import_esco(
    session: AsyncSession, path: Path, *, include_unlinked: bool = False
) -> EscoResult:
    rows = read_esco(path)
    by_label: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        labels = [row["preferredLabel"], *(row.get("altLabels") or "").splitlines()]
        for label in labels:
            if label.strip():
                by_label[normalize_alias(label)].add(row["conceptUri"])

    skills = (
        await session.scalars(
            select(Skill).where(Skill.extractable.is_(True)).options(selectinload(Skill.aliases))
        )
    ).all()
    linked = ambiguous = 0
    used: set[str] = set()
    for skill in skills:
        keys = {normalize_alias(skill.name), *(a.alias_normalized for a in skill.aliases)}
        uris = set().union(*(by_label.get(k, set()) for k in keys))
        if len(uris) == 1:
            skill.esco_uri = uris.pop()
            used.add(skill.esco_uri)
            linked += 1
        elif len(uris) > 1:
            ambiguous += 1
    added = 0
    if include_unlinked:
        existing = set((await session.scalars(select(Skill.esco_uri))).all())
        for row in rows:
            uri = row["conceptUri"]
            if uri in used or uri in existing:
                continue
            session.add(
                Skill(
                    slug=f"esco-{uri.rstrip('/').rsplit('/', 1)[-1]}"[:80],
                    name=row["preferredLabel"][:120],
                    category="esco",
                    description=(row.get("description") or None),
                    esco_uri=uri,
                    extractable=False,
                )
            )
            added += 1
    await session.flush()
    return EscoResult(len(rows), linked, ambiguous, added)
