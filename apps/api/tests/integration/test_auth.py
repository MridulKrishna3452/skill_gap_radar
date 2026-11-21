"""Phase 2 end to end: registration, login, refresh rotation and reuse detection, lockout,
rate limits, profiles and skills, administration, account deletion, and log hygiene."""

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import AuditLog, Program, RefreshToken, University, User
from tests.integration.conftest import PASSWORD, RecordingQueue

pytestmark = pytest.mark.integration
Factory = async_sessionmaker[AsyncSession]
A = "/api/v1"
STRONG = "a long and unguessable passphrase"


async def register(api: AsyncClient, email: str = "new@example.test") -> Response:
    return await api.post(f"{A}/auth/register", json={"email": email, "password": STRONG})


async def login(api: AsyncClient, email: str, password: str = STRONG) -> Response:
    return await api.post(f"{A}/auth/login", json={"email": email, "password": password})


def bearer(r: Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def audit_actions(factory: Factory) -> list[str]:
    async with factory() as s:
        return list((await s.scalars(select(AuditLog.action).order_by(AuditLog.id))).all())


@pytest.fixture
async def client_for(
    factory: Factory, queue: RecordingQueue, test_settings: Settings
) -> AsyncIterator[Any]:
    """Build an extra client with changed settings (e.g. low rate limits)."""
    from app.main import create_app

    stack: list[Any] = []

    async def make(**overrides: Any) -> AsyncClient:
        app = create_app(test_settings.model_copy(update=overrides))
        ctx = app.router.lifespan_context(app)
        await ctx.__aenter__()
        app.state.task_queue = queue
        await app.state.redis.flushdb()
        client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
        stack.append((ctx, client))
        return client

    yield make
    for ctx, client in stack:
        await client.aclose()
        await ctx.__aexit__(None, None, None)


# ---- register / login / refresh / logout -------------------------------------------------


async def test_full_session_flow(api: AsyncClient) -> None:
    r = await register(api, "Flow@Example.test")
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "student" and r.json()["email"] == "flow@example.test"

    r = await login(api, "flow@example.test")
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900
    cookie = r.headers["set-cookie"].lower()
    for attr in ("httponly", "secure", "samesite=strict", "path=/api/v1/auth"):
        assert attr in cookie
    first_refresh = api.cookies.get("sr_refresh", path="/api/v1/auth")
    assert first_refresh

    me = await api.get(f"{A}/me", headers=bearer(r))
    assert me.status_code == 200 and me.json()["email"] == "flow@example.test"

    r2 = await api.post(f"{A}/auth/refresh")
    assert r2.status_code == 200, r2.text
    assert api.cookies.get("sr_refresh", path="/api/v1/auth") != first_refresh
    assert (await api.get(f"{A}/me", headers=bearer(r2))).status_code == 200

    assert (await api.post(f"{A}/auth/logout")).status_code == 204
    assert (await api.post(f"{A}/auth/refresh")).status_code == 401


async def test_refresh_token_reuse_revokes_the_family(api: AsyncClient, factory: Factory) -> None:
    await register(api)
    await login(api, "new@example.test")
    stolen = api.cookies.get("sr_refresh", path="/api/v1/auth")
    assert (await api.post(f"{A}/auth/refresh")).status_code == 200  # legitimate rotation
    current = api.cookies.get("sr_refresh", path="/api/v1/auth")

    api.cookies.clear()
    api.cookies.set("sr_refresh", stolen)
    replay = await api.post(f"{A}/auth/refresh")
    assert replay.status_code == 401
    # The legitimate successor is revoked too: the whole login is ended.
    api.cookies.clear()
    api.cookies.set("sr_refresh", current)
    after = await api.post(f"{A}/auth/refresh")
    assert after.status_code == 401
    assert "auth.refresh_reuse" in await audit_actions(factory)
    async with factory() as s:
        live = await s.scalar(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
        )
    assert live == 0


async def test_expired_and_overage_refresh_tokens_are_rejected(
    api: AsyncClient, factory: Factory
) -> None:
    await register(api)
    await login(api, "new@example.test")
    async with factory() as s:
        await s.execute(update(RefreshToken).values(expires_at=datetime.now(tz=UTC)))
        await s.commit()
    assert (await api.post(f"{A}/auth/refresh")).status_code == 401

    api.cookies.clear()
    await login(api, "new@example.test")
    async with factory() as s:
        # Still within its own expiry, but the login (family) is older than the maximum.
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.revoked_at.is_(None), RefreshToken.used_at.is_(None))
            .values(family_started_at=datetime.now(tz=UTC) - timedelta(days=31))
        )
        await s.commit()
    assert (await api.post(f"{A}/auth/refresh")).status_code == 401


async def test_refresh_rejects_foreign_origins(api: AsyncClient) -> None:
    await register(api)
    await login(api, "new@example.test")
    r = await api.post(f"{A}/auth/refresh", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    ok = await api.post(f"{A}/auth/refresh", headers={"Origin": "http://localhost:3000"})
    assert ok.status_code == 200


async def test_access_token_checks(api: AsyncClient, factory: Factory, make_user: Any) -> None:
    acct = await make_user("student")
    assert (await api.get(f"{A}/me", headers=acct.headers)).status_code == 200
    assert (await api.get(f"{A}/me")).status_code == 401
    bad = {"Authorization": acct.headers["Authorization"][:-3] + "abc"}
    r = await api.get(f"{A}/me", headers=bad)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    # Deactivation applies immediately, even to an unexpired token.
    async with factory() as s:
        await s.execute(update(User).where(User.id == acct.id).values(is_active=False))
        await s.commit()
    assert (await api.get(f"{A}/me", headers=acct.headers)).status_code == 401


async def test_registration_rules(api: AsyncClient, client_for: Any) -> None:
    assert (await register(api, "dup@example.test")).status_code == 201
    assert (await register(api, "DUP@example.test")).status_code == 409
    weak = await api.post(f"{A}/auth/register", json={"email": "w@example.test", "password": "x"})
    assert weak.status_code == 422 and "12 characters" in weak.json()["error"]["message"]
    # Extra fields are ignored: open registration can never create an admin.
    r = await api.post(
        f"{A}/auth/register",
        json={"email": "sneaky@example.test", "password": STRONG, "role": "admin"},
    )
    assert r.status_code == 201 and r.json()["role"] == "student"
    closed = await client_for(ALLOW_REGISTRATION=False)
    assert (await register(closed, "late@example.test")).status_code == 403


# ---- lockout and rate limits ---------------------------------------------------------------


async def test_failed_logins_lock_the_account(api: AsyncClient, factory: Factory) -> None:
    await register(api, "lock@example.test")
    unknown = await login(api, "nobody@example.test")
    wrong = await login(api, "lock@example.test", "a wrong password value")
    # Same answer whether or not the account exists.
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
    for _ in range(4):
        await login(api, "lock@example.test", "a wrong password value")
    # Locked now (5 failures): even the right password is refused.
    assert (await login(api, "lock@example.test")).status_code == 401
    assert "auth.lockout" in await audit_actions(factory)
    async with factory() as s:
        await s.execute(
            update(User).values(locked_until=datetime.now(tz=UTC) - timedelta(seconds=1))
        )
        await s.commit()
    assert (await login(api, "lock@example.test")).status_code == 200


async def test_rate_limits(client_for: Any, make_user: Any) -> None:
    c = await client_for(RATE_LIMIT_LOGIN="3/60")
    codes = [(await login(c, "x@example.test", "wrong password!!")).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    last = await login(c, "x@example.test", "wrong password!!")
    assert int(last.headers["retry-after"]) >= 1
    assert last.json()["error"]["code"] == "rate_limited"

    c = await client_for(RATE_LIMIT_REGISTER="2/3600")
    codes = [(await register(c, f"r{i}@example.test")).status_code for i in range(3)]
    assert codes == [201, 201, 429]

    c = await client_for(RATE_LIMIT_PUBLIC="2/60")
    codes = [(await c.get(f"{A}/skills")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert (await c.get(f"{A}/health/live")).status_code == 200  # health is never limited

    user = await make_user("student")
    c = await client_for(RATE_LIMIT_EXPENSIVE="1/60")
    codes = [(await c.get(f"{A}/jobs/export", headers=user.headers)).status_code for _ in range(2)]
    assert codes == [200, 429]


# ---- password change and logout-all ------------------------------------------------------


async def test_password_change_ends_every_session(api: AsyncClient) -> None:
    await register(api, "pw@example.test")
    r = await login(api, "pw@example.test")
    headers = bearer(r)
    wrong = await api.post(
        f"{A}/auth/password",
        headers=headers,
        json={"current_password": "not my password", "new_password": "another long passphrase"},
    )
    assert wrong.status_code == 403
    ok = await api.post(
        f"{A}/auth/password",
        headers=headers,
        json={"current_password": STRONG, "new_password": "another long passphrase"},
    )
    assert ok.status_code == 204
    api.cookies.clear()
    assert (await login(api, "pw@example.test")).status_code == 401
    assert (await login(api, "pw@example.test", "another long passphrase")).status_code == 200


async def test_logout_all(api: AsyncClient, factory: Factory) -> None:
    await register(api, "all@example.test")
    r = await login(api, "all@example.test")
    await login(api, "all@example.test")  # a second session
    assert (await api.post(f"{A}/auth/logout-all", headers=bearer(r))).status_code == 204
    async with factory() as s:
        live = await s.scalar(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
        )
    assert live == 0


# ---- profile and skills -----------------------------------------------------------------


async def _university_with_program(factory: Factory, name: str = "Uni") -> tuple[int, int]:
    async with factory() as s:
        uni = University(name=name, country="in")
        s.add(uni)
        await s.flush()
        prog = Program(university_id=uni.id, name="B.Tech CSE", degree="B.Tech")
        s.add(prog)
        await s.commit()
        return uni.id, prog.id


async def test_profile_crud_and_validation(
    api: AsyncClient, factory: Factory, make_user: Any
) -> None:
    student = await make_user("student")
    h = student.headers
    uni_id, prog_id = await _university_with_program(factory)
    other_uni, other_prog = await _university_with_program(factory, "Other")

    assert (await api.get(f"{A}/me/profile", headers=h)).status_code == 404
    r = await api.put(
        f"{A}/me/profile",
        headers=h,
        json={
            "display_name": "  Asha  ",
            "program_id": prog_id,
            "graduation_year": 2027,
            "target_role": "data-engineer",
            "location_preference": "bengaluru",
            "open_to_remote": True,
        },
    )
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["display_name"] == "Asha"
    assert p["university"]["id"] == uni_id  # filled in from the program
    assert p["target_role"]["slug"] == "data-engineer"
    assert p["open_to_remote"] is True

    r = await api.patch(f"{A}/me/profile", headers=h, json={"graduation_year": 2028})
    assert (
        r.json()["graduation_year"] == 2028 and r.json()["target_role"]["slug"] == "data-engineer"
    )

    for bad in (
        {"university_id": other_uni, "program_id": prog_id},
        {"target_role": "astronaut"},
        {"graduation_year": 1990},
        {"program_id": 999_999},
        {"unknown_field": 1},
    ):
        assert (await api.patch(f"{A}/me/profile", headers=h, json=bad)).status_code == 422, bad

    me = (await api.get(f"{A}/me", headers=h)).json()
    assert me["profile"]["graduation_year"] == 2028
    faculty = await make_user("faculty")
    assert (await api.get(f"{A}/me/profile", headers=faculty.headers)).status_code == 403
    assert other_prog  # second program exists only to test the mismatch


async def test_skills_inventory(api: AsyncClient, make_user: Any) -> None:
    h = (await make_user("student")).headers
    r = await api.post(f"{A}/me/skills", headers=h, json={"skill": "python", "proficiency": 4})
    assert r.status_code == 201 and r.json()["skill"]["slug"] == "python"
    assert r.json()["source"] == "self_declared"
    dup = await api.post(f"{A}/me/skills", headers=h, json={"skill": "python", "proficiency": 2})
    assert dup.status_code == 409
    for bad in ({"skill": "basket-weaving", "proficiency": 3}, {"skill": "sql", "proficiency": 6}):
        assert (await api.post(f"{A}/me/skills", headers=h, json=bad)).status_code == 422
    await api.post(f"{A}/me/skills", headers=h, json={"skill": "sql", "proficiency": 2})
    r = await api.patch(f"{A}/me/skills/sql", headers=h, json={"proficiency": 5})
    assert r.json()["proficiency"] == 5
    listed = (await api.get(f"{A}/me/skills", headers=h)).json()
    assert [s["skill"]["slug"] for s in listed] == ["sql", "python"]  # by proficiency
    assert (await api.delete(f"{A}/me/skills/sql", headers=h)).status_code == 204
    assert (await api.delete(f"{A}/me/skills/sql", headers=h)).status_code == 404


# ---- administration ----------------------------------------------------------------------


async def test_admin_manages_faculty_and_curriculum_access(
    api: AsyncClient, factory: Factory, make_user: Any
) -> None:
    from tests.pdfs import V1_STYLE, make_pdf

    admin = await make_user("admin")
    _, prog_id = await _university_with_program(factory)
    _, other_prog = await _university_with_program(factory, "Other")
    r = await api.post(
        f"{A}/admin/users",
        headers=admin.headers,
        json={"email": "prof@example.test", "password": STRONG, "role": "faculty"},
    )
    assert r.status_code == 201
    faculty_id = r.json()["id"]
    assigned = await api.put(
        f"{A}/admin/users/{faculty_id}/programs/{prog_id}", headers=admin.headers
    )
    assert assigned.status_code == 204

    prof = bearer(await login(api, "prof@example.test"))
    pdf = {"file": ("s.pdf", make_pdf(V1_STYLE), "application/pdf")}
    up = await api.post(f"{A}/programs/{prog_id}/curriculum", headers=prof, files=pdf)
    assert up.status_code == 202, up.text
    other = await api.post(f"{A}/programs/{other_prog}/curriculum", headers=prof, files=pdf)
    assert other.status_code == 403
    doc_id = up.json()["document"]["id"]
    assert (await api.get(f"{A}/curriculum/documents/{doc_id}", headers=prof)).status_code == 200

    # Role change signs the user out and removes program assignments.
    r = await api.patch(
        f"{A}/admin/users/{faculty_id}", headers=admin.headers, json={"role": "student"}
    )
    assert r.status_code == 200 and r.json()["program_ids"] == []
    assert (await api.post(f"{A}/auth/refresh")).status_code == 401

    actions = await audit_actions(factory)
    for expected in ("user.create", "faculty.assign", "curriculum.upload", "user.update"):
        assert expected in actions
    log = (await api.get(f"{A}/admin/audit-log?action=user.update", headers=admin.headers)).json()
    assert log["total"] == 1 and log["items"][0]["details"]["role"] == {
        "from": "faculty",
        "to": "student",
    }


async def test_last_admin_is_protected(api: AsyncClient, make_user: Any) -> None:
    admin = await make_user("admin")
    r = await api.patch(
        f"{A}/admin/users/{admin.id}", headers=admin.headers, json={"role": "student"}
    )
    assert r.status_code == 409
    r = await api.request("DELETE", f"{A}/me", headers=admin.headers, json={"password": PASSWORD})
    assert r.status_code == 409
    second = await make_user("admin")
    r = await api.patch(
        f"{A}/admin/users/{admin.id}", headers=second.headers, json={"is_active": False}
    )
    assert r.status_code == 200


# ---- account deletion --------------------------------------------------------------------


USER_TABLES = (
    ("users", "id"),
    ("refresh_tokens", "user_id"),
    ("student_profiles", "user_id"),
    ("user_skills", "user_id"),
    ("faculty_program_assignments", "user_id"),
    ("audit_log", "actor_user_id"),
)


async def test_account_deletion_removes_personal_data(api: AsyncClient, factory: Factory) -> None:
    await register(api, "gone@example.test")
    r = await login(api, "gone@example.test")
    h = bearer(r)
    await api.put(
        f"{A}/me/profile", headers=h, json={"display_name": "Gone", "graduation_year": 2027}
    )
    await api.post(f"{A}/me/skills", headers=h, json={"skill": "python", "proficiency": 3})
    await api.post(
        f"{A}/auth/password",
        headers=h,
        json={"current_password": STRONG, "new_password": "another long passphrase"},
    )  # leaves an audit entry naming this user as actor
    h = bearer(await login(api, "gone@example.test", "another long passphrase"))
    me = (await api.get(f"{A}/me", headers=h)).json()

    wrong = await api.request("DELETE", f"{A}/me", headers=h, json={"password": "not it at all"})
    assert wrong.status_code == 403
    ok = await api.request(
        "DELETE", f"{A}/me", headers=h, json={"password": "another long passphrase"}
    )
    assert ok.status_code == 204

    async with factory() as s:
        for table, column in USER_TABLES:
            n = await s.scalar(
                # Table and column names come from the USER_TABLES constant above.
                text(f"SELECT count(*) FROM {table} WHERE {column} = :id"),  # noqa: S608
                {"id": me["id"]},
            )
            assert n == 0, table
        dumped = " ".join(
            str(row) for row in (await s.execute(text("SELECT * FROM audit_log"))).all()
        )
    assert "gone@example.test" not in dumped  # no email anywhere in the audit log
    assert "user.delete" in await audit_actions(factory)
    assert (await api.get(f"{A}/me", headers=h)).status_code == 401
    assert (await login(api, "gone@example.test", "another long passphrase")).status_code == 401


# ---- log hygiene ----------------------------------------------------------------------------


async def test_no_password_token_or_secret_in_logs(
    api: AsyncClient, test_settings: Settings, caplog: pytest.LogCaptureFixture, capsys: Any
) -> None:
    caplog.set_level(logging.DEBUG)
    await register(api, "logs@example.test")
    await login(api, "logs@example.test", "a wrong password value")
    r = await login(api, "logs@example.test")
    access = r.json()["access_token"]
    refresh = api.cookies.get("sr_refresh", path="/api/v1/auth")
    await api.get(f"{A}/me", headers={"Authorization": f"Bearer {access}"})
    await api.post(f"{A}/auth/refresh")
    await api.get(f"{A}/jobs?q=password={STRONG}")  # a secret-looking query string

    secrets = [
        STRONG,
        "a wrong password value",
        access,
        refresh or "-",
        test_settings.JWT_SECRET.get_secret_value(),
    ]
    records = "\n".join(
        rec.getMessage() + (str(rec.exc_info) if rec.exc_info else "") for rec in caplog.records
    )
    printed = capsys.readouterr()
    for secret in secrets:
        assert secret not in records
        assert secret not in printed.out and secret not in printed.err
    assert caplog.records  # the flow did log (access lines etc.)
