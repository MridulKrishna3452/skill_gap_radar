"""Assign a posting to a role from its title (deterministic phrase rules from roles.json)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobPosting, Role


@dataclass(frozen=True)
class RoleRule:
    role_id: int
    priority: int
    patterns: tuple[re.Pattern[str], ...]


def compile_rules(roles: Sequence[tuple[int, int, Sequence[str]]]) -> list[RoleRule]:
    """roles: (role_id, match_priority, title_patterns). Highest priority is tried first."""
    rules = [
        RoleRule(
            role_id,
            priority,
            tuple(
                re.compile(rf"(?<![a-z0-9]){re.escape(p.lower())}(?![a-z0-9])") for p in patterns
            ),
        )
        for role_id, priority, patterns in roles
    ]
    return sorted(rules, key=lambda r: -r.priority)


def classify_title(title: str, rules: Sequence[RoleRule]) -> int | None:
    lower = title.lower()
    for rule in rules:
        if any(p.search(lower) for p in rule.patterns):
            return rule.role_id
    return None


async def load_rules(session: AsyncSession) -> list[RoleRule]:
    roles = (await session.scalars(select(Role))).all()
    return compile_rules([(r.id, r.match_priority, r.title_patterns) for r in roles])


async def reclassify_postings(session: AsyncSession) -> dict[str, int]:
    """Re-apply the current role rules to every stored posting (after roles.json changes).
    Roles are otherwise assigned only at ingestion."""
    rules = await load_rules(session)
    rows = (
        await session.execute(select(JobPosting.id, JobPosting.title, JobPosting.role_id))
    ).all()
    changed = 0
    for posting_id, title, current in rows:
        new = classify_title(title, rules)
        if new != current:
            await session.execute(
                update(JobPosting).where(JobPosting.id == posting_id).values(role_id=new)
            )
            changed += 1
    return {"postings": len(rows), "changed": changed}
