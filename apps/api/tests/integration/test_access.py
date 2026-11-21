"""Access control over the whole route table.

ACCESS lists every API operation and who may call it. The test fails if a route is added
without an entry, so no endpoint can ship unprotected by accident. For each protected route
it checks: no token -> 401, a disallowed role -> 403, an allowed role -> neither.
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import FacultyProgramAssignment, Program, University
from app.services.curriculum.service import create_document
from tests.pdfs import V1_STYLE, make_pdf

pytestmark = pytest.mark.integration
Factory = async_sessionmaker[AsyncSession]

PUBLIC, USER, STUDENT, ADMIN, MANAGER, COOKIE = (
    "public",
    "user",
    "student",
    "admin",
    "manager",
    "cookie",
)
ACCESS: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/health/live"): PUBLIC,
    ("GET", "/api/v1/health/ready"): PUBLIC,
    # auth
    ("POST", "/api/v1/auth/register"): PUBLIC,
    ("POST", "/api/v1/auth/login"): PUBLIC,
    ("POST", "/api/v1/auth/refresh"): COOKIE,
    ("POST", "/api/v1/auth/logout"): COOKIE,
    ("POST", "/api/v1/auth/logout-all"): USER,
    ("POST", "/api/v1/auth/password"): USER,
    # current user
    ("GET", "/api/v1/me"): USER,
    ("DELETE", "/api/v1/me"): USER,
    ("GET", "/api/v1/me/profile"): STUDENT,
    ("PUT", "/api/v1/me/profile"): STUDENT,
    ("PATCH", "/api/v1/me/profile"): STUDENT,
    ("GET", "/api/v1/me/skills"): STUDENT,
    ("POST", "/api/v1/me/skills"): STUDENT,
    ("PATCH", "/api/v1/me/skills/{slug}"): STUDENT,
    ("DELETE", "/api/v1/me/skills/{slug}"): STUDENT,
    # administration
    ("GET", "/api/v1/admin/users"): ADMIN,
    ("POST", "/api/v1/admin/users"): ADMIN,
    ("PATCH", "/api/v1/admin/users/{user_id}"): ADMIN,
    ("PUT", "/api/v1/admin/users/{user_id}/programs/{program_id}"): ADMIN,
    ("DELETE", "/api/v1/admin/users/{user_id}/programs/{program_id}"): ADMIN,
    ("GET", "/api/v1/admin/audit-log"): ADMIN,
    # market data (Phase 1)
    ("GET", "/api/v1/jobs"): PUBLIC,
    ("GET", "/api/v1/jobs/export"): USER,
    ("GET", "/api/v1/jobs/facets"): PUBLIC,
    ("GET", "/api/v1/jobs/{job_id}"): PUBLIC,
    ("GET", "/api/v1/skills"): PUBLIC,
    ("GET", "/api/v1/skills/demand"): PUBLIC,
    ("GET", "/api/v1/skills/{slug}"): PUBLIC,
    ("GET", "/api/v1/roles"): PUBLIC,
    ("GET", "/api/v1/trends/skills/{slug}"): PUBLIC,
    ("GET", "/api/v1/trends/movers"): PUBLIC,
    ("GET", "/api/v1/recommendations"): PUBLIC,
    # curriculum
    ("POST", "/api/v1/universities"): ADMIN,
    ("GET", "/api/v1/universities"): PUBLIC,
    ("POST", "/api/v1/programs"): ADMIN,
    ("GET", "/api/v1/programs"): PUBLIC,
    ("GET", "/api/v1/programs/{program_id}"): PUBLIC,
    ("POST", "/api/v1/programs/{program_id}/curriculum"): MANAGER,
    ("GET", "/api/v1/programs/{program_id}/curriculum"): PUBLIC,
    ("GET", "/api/v1/programs/{program_id}/curriculum/documents"): MANAGER,
    ("GET", "/api/v1/curriculum/documents/{document_id}"): MANAGER,
    # gap reports are stored per call
    ("GET", "/api/v1/gap"): USER,
    ("GET", "/api/v1/gap/by-role"): USER,
    ("GET", "/api/v1/gap/reports/{report_id}"): USER,
    # ingestion
    ("GET", "/api/v1/sources"): ADMIN,
    ("POST", "/api/v1/ingestion/runs"): ADMIN,
    ("GET", "/api/v1/ingestion/runs"): ADMIN,
    ("GET", "/api/v1/ingestion/runs/{run_id}"): ADMIN,
}
ALLOWED = {
    USER: ("student", "faculty", "admin"),
    STUDENT: ("student",),
    ADMIN: ("admin",),
    MANAGER: ("admin", "assigned_faculty"),
}
DENIED = {
    USER: (),
    STUDENT: ("faculty", "admin"),
    ADMIN: ("student", "faculty"),
    MANAGER: ("student", "faculty"),  # "faculty" = not assigned to the program
}


def routes(app: Any) -> set[tuple[str, str]]:
    """Every operation the app serves, from its OpenAPI schema (FastAPI includes routers
    lazily, so app.routes does not list them)."""
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def test_every_route_has_an_access_rule() -> None:
    from app.main import create_app

    found = routes(create_app())
    assert found - ACCESS.keys() == set(), "routes without an access rule"
    assert ACCESS.keys() - found == set(), "access rules for routes that no longer exist"


async def _fixtures(factory: Factory, make_user: Any) -> dict[str, Any]:
    async with factory() as s:
        uni = University(name="Access U", country="in")
        s.add(uni)
        await s.flush()
        prog = Program(university_id=uni.id, name="B.Tech", degree="B.Tech")
        s.add(prog)
        await s.flush()
        from app.core.config import get_settings

        doc, _ = await create_document(s, prog.id, "s.pdf", make_pdf(V1_STYLE), get_settings())
        await s.commit()
        ids = {"program_id": prog.id, "document_id": doc.id}
    accounts = {role: await make_user(role) for role in ("student", "faculty", "admin")}
    assigned = await make_user("faculty")
    async with factory() as s:
        s.add(FacultyProgramAssignment(user_id=assigned.id, program_id=ids["program_id"]))
        await s.commit()
    accounts["assigned_faculty"] = assigned
    return {"ids": ids, "accounts": accounts}


def _url(path: str, ids: dict[str, Any], target_user: str) -> str:
    values = {
        "slug": "python",
        "job_id": "1",
        "report_id": "1",
        "run_id": "1",
        "user_id": target_user,
        "program_id": str(ids["program_id"]),
        "document_id": str(ids["document_id"]),
    }
    for key, value in values.items():
        path = path.replace("{" + key + "}", value)
    return path


async def test_protected_routes_enforce_roles(
    api: AsyncClient, factory: Factory, make_user: Any
) -> None:
    fx = await _fixtures(factory, make_user)
    target = str(fx["accounts"]["student"].id)
    checked = 0
    for (method, path), level in sorted(ACCESS.items()):
        if level in (PUBLIC, COOKIE):
            continue
        url = _url(path, fx["ids"], target)
        # A body that is invalid on purpose: authorisation must be decided before validation,
        # and a 422 still proves the caller got past the access check.
        kwargs: dict[str, Any] = (
            {"json": {}} if method in ("POST", "PUT", "PATCH", "DELETE") else {}
        )
        anon = await api.request(method, url, **kwargs)
        assert anon.status_code == 401, (method, path, anon.status_code)
        for role in DENIED[level]:
            r = await api.request(method, url, headers=fx["accounts"][role].headers, **kwargs)
            assert r.status_code == 403, (method, path, role, r.status_code, r.text)
        for role in ALLOWED[level]:
            r = await api.request(method, url, headers=fx["accounts"][role].headers, **kwargs)
            assert r.status_code not in (401, 403), (method, path, role, r.status_code, r.text)
        checked += 1
    assert checked == sum(1 for v in ACCESS.values() if v not in (PUBLIC, COOKIE))


async def test_public_routes_need_no_token(api: AsyncClient, factory: Factory) -> None:
    for (method, path), level in ACCESS.items():
        if level != PUBLIC or method != "GET" or "{" in path:
            continue
        api.headers.pop("Authorization", None)
        r = await api.get(path, params={"role": "data-engineer"} if "recommend" in path else None)
        assert r.status_code not in (401, 403), (path, r.status_code)
