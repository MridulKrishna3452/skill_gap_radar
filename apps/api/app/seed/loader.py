"""Idempotent loading of reference data: taxonomy, roles, editorial learning content, sources.

Safe to run on every deploy: rows are matched by natural key (slug, alias, source key) and
updated in place; aliases removed from the seed file are deleted.
"""

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobSource, LearningContent, Role, RoleSkill, Skill, SkillAlias
from app.services.extraction.extractor import normalize_alias
from app.services.extraction.taxonomy import alias_spec, read_seed

# Sources the platform knows about. File-import sources are registered by the import command,
# which requires the licence to be stated.
BUILTIN_SOURCES = [
    {
        "key": "adzuna",
        "name": "Adzuna Jobs API",
        "kind": "api",
        "is_synthetic": False,
        "licence": "Adzuna API terms of service (https://developer.adzuna.com). Postings link "
        "back to Adzuna; descriptions are snippets supplied by the API.",
        "homepage_url": "https://www.adzuna.com",
    },
]


@dataclass
class SeedResult:
    skills: int
    aliases: int
    roles: int
    learning_content: int
    sources: int


async def seed_reference_data(session: AsyncSession) -> SeedResult:
    skills_seed = read_seed("skills.json")["skills"]
    existing = {s.slug: s for s in (await session.scalars(select(Skill))).all()}

    by_slug: dict[str, Skill] = {}
    for raw in skills_seed:
        skill = existing.get(raw["slug"])
        if skill is None:
            skill = Skill(slug=raw["slug"])
            session.add(skill)
        skill.name = raw["name"]
        skill.category = raw["category"]
        skill.description = raw.get("description")
        skill.context_terms = [t.lower() for t in raw.get("context_terms", [])]
        skill.extractable = True
        by_slug[raw["slug"]] = skill
    await session.flush()
    for raw in skills_seed:
        parent = raw.get("parent")
        by_slug[raw["slug"]].parent_id = by_slug[parent].id if parent else None

    # Aliases: one row per normalised alias, owned by exactly one skill.
    alias_rows = {a.alias_normalized: a for a in (await session.scalars(select(SkillAlias))).all()}
    wanted: set[str] = set()
    for raw in skills_seed:
        skill = by_slug[raw["slug"]]
        for entry in raw["aliases"]:
            spec = alias_spec(entry)
            key = normalize_alias(spec.alias)
            wanted.add(key)
            row = alias_rows.get(key)
            if row is None:
                row = SkillAlias(alias_normalized=key)
                session.add(row)
            row.skill_id = skill.id
            row.alias = spec.alias
            row.requires_context = spec.requires_context
            row.case_sensitive_form = spec.case_form
            row.negative_following = list(spec.negative_following)
            row.strict = spec.strict
    seeded_ids = [s.id for s in by_slug.values()]
    stale = [k for k, row in alias_rows.items() if k not in wanted and row.skill_id in seeded_ids]
    if stale:
        await session.execute(delete(SkillAlias).where(SkillAlias.alias_normalized.in_(stale)))

    # Roles and their editorial core skills.
    roles_seed = read_seed("roles.json")["roles"]
    roles = {r.slug: r for r in (await session.scalars(select(Role))).all()}
    for raw in roles_seed:
        role = roles.get(raw["slug"])
        if role is None:
            role = Role(slug=raw["slug"])
            session.add(role)
        role.name = raw["name"]
        role.description = raw.get("description")
        role.title_patterns = [p.lower() for p in raw["title_patterns"]]
        role.match_priority = raw["match_priority"]
        await session.flush()
        await session.execute(delete(RoleSkill).where(RoleSkill.role_id == role.id))
        for pos, slug in enumerate(raw["core_skills"]):
            session.add(RoleSkill(role_id=role.id, skill_id=by_slug[slug].id, position=pos))

    # Editorial learning content (v1 roadmap text).
    learning = read_seed("learning_content.json")
    content = {c.skill_id: c for c in (await session.scalars(select(LearningContent))).all()}
    for item in learning["items"]:
        skill_id = by_slug[item["skill"]].id
        lc = content.get(skill_id)
        if lc is None:
            lc = LearningContent(skill_id=skill_id)
            session.add(lc)
        lc.difficulty = item["difficulty"]
        lc.estimated_weeks = item["estimated_weeks"]
        lc.steps = item["steps"]
        lc.content_source = learning["content_source"]

    sources = {s.key: s for s in (await session.scalars(select(JobSource))).all()}
    for raw_source in BUILTIN_SOURCES:
        source = sources.get(str(raw_source["key"]))
        if source is None:
            source = JobSource(key=raw_source["key"])
            session.add(source)
        source.name = str(raw_source["name"])
        source.kind = str(raw_source["kind"])
        source.is_synthetic = bool(raw_source["is_synthetic"])
        source.licence = str(raw_source["licence"])
        source.homepage_url = str(raw_source["homepage_url"])

    await session.flush()
    return SeedResult(
        skills=len(by_slug),
        aliases=len(wanted),
        roles=len(roles_seed),
        learning_content=len(learning["items"]),
        sources=len(BUILTIN_SOURCES),
    )
