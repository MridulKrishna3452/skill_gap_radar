# Security design (Phase 2: authentication and access control)

This document describes how SkillRadar authenticates users, decides what each one may do, and
protects credentials. Code: `apps/api/app/services/auth/`, `app/api/deps.py`,
`app/api/v1/{auth,me,admin}.py`. Tests: `tests/unit/test_auth.py`,
`tests/integration/test_auth.py`, `tests/integration/test_access.py`.

## Accounts and roles

| Role | Who | Can additionally |
|---|---|---|
| `student` | anyone, through open registration | keep a profile and a skills inventory |
| `faculty` | created by an admin | upload and inspect the curriculum of programs they are assigned to |
| `admin` | created by an admin, or the first one with `python -m app.cli create-user --role admin` | manage users, roles and assignments; create universities and programs; run ingestion; read the audit log |

Open registration (`POST /auth/register`) only ever creates students. The role field cannot be
sent, and extra fields are ignored. It can be closed with `ALLOW_REGISTRATION=false`. The CLI
reads passwords from a prompt or stdin, never from an argument, so they do not reach shell
history or process listings.

The last active admin cannot be demoted, deactivated or deleted.

## Passwords

- argon2id with argon2-cffi's defaults (RFC 9106 low-memory profile: t=3, m=64 MiB, p=4).
  A hash made with older parameters is upgraded on the next successful login.
- Policy (NIST SP 800-63B style): 12–128 characters, not the email or its local part, and
  not one repeated character. There are no composition rules.
- Login failures always return the same 401 with the same message, whether the email is
  unknown, the password wrong, or the account locked or inactive. For an unknown email the
  API still verifies against a dummy hash, so response times match too.

## Tokens and sessions

| | Access token | Refresh token |
|---|---|---|
| Form | JWT, HS256, signed with `JWT_SECRET` | 256-bit random value (`secrets.token_urlsafe(32)`) |
| Lifetime | `ACCESS_TOKEN_MINUTES` (15) | `REFRESH_TOKEN_DAYS` (14); a login can be rotated for at most `REFRESH_FAMILY_MAX_DAYS` (30) |
| Transport | response body → client memory → `Authorization: Bearer` | cookie `sr_refresh`: `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` |
| Stored server-side | no | SHA-256 hash only (`refresh_tokens.token_hash`) |

**Access token checks.** The algorithm is pinned to HS256, which blocks `alg: none` and
algorithm-confusion attacks. Issuer, audience, expiry, `iat`, `sub` and `typ=access` are all
required. The user is reloaded from the database on every request, so deactivation and role
changes take effect immediately rather than when the token expires. The role claim is
informational only.

**Rotation and reuse detection.** Every refresh token works once. `POST /auth/refresh` marks
the presented token used and issues its successor in the same family (row lock, so two
concurrent refreshes cannot both succeed). If a used token is presented again, that means a
copy exists somewhere else. The API then:
1. revokes every token in the family, which ends that login on every device;
2. writes an `auth.refresh_reuse` audit entry.

The legitimate user signs in again. The attacker's copy is dead.

**Ending sessions.**
- Logout revokes the current family.
- Logout-all and a password change revoke all of the user's families.
- An admin deactivating a user, changing their role or resetting their password also revokes
  all of the user's families.

**JWT_SECRET.** Production refuses to start without a secret of at least 32 characters. In
development and tests, an empty secret is replaced by a random per-process one and a warning is
logged. Sessions then end when the API restarts.

## CSRF and CORS

Bearer-token endpoints cannot be forged cross-site, because browsers never attach the header
automatically. The two cookie-authenticated endpoints (`/auth/refresh`, `/auth/logout`) are
protected by `SameSite=Strict`, and additionally reject requests whose `Origin` is not in
`CORS_ORIGINS`. CORS lists explicit origins only (a wildcard is rejected at startup) with
credentials enabled.

## Rate limits and lockout

Fixed windows in Redis (`INCR` + `EXPIRE`, keys hold hashed identifiers, never raw emails).
Values are `<count>/<seconds>` settings:

| Limit | Default | Key | If Redis is down |
|---|---|---|---|
| `RATE_LIMIT_LOGIN` | 5 / 60 s | client IP + email | refuse (503) |
| `RATE_LIMIT_LOGIN_IP` | 20 / hour | client IP | refuse (503) |
| `RATE_LIMIT_REGISTER` | 5 / hour | client IP | refuse (503) |
| `RATE_LIMIT_REFRESH` | 30 / 60 s | client IP | refuse (503) |
| `RATE_LIMIT_EXPENSIVE` | 30 / 60 s | user (gap reports, CSV export) | allow |
| `RATE_LIMIT_PUBLIC` | 120 / 60 s | client IP (every route except health) | allow |

A limit returns 429 with `Retry-After`. Auth limits fail closed, so brute force cannot ride
on a Redis outage. Read limits fail open, so an outage does not take the read API down.

**Lockout.** After `LOGIN_MAX_FAILURES` (5) consecutive wrong passwords, the account is locked
for `LOCKOUT_MINUTES` (15) and an `auth.lockout` audit entry is written. The trade-off is that
anyone who knows an email can lock that account out. This is kept in check by the short lock,
the per-IP limits and the fact that lockout never reveals whether an account exists. The
counter is committed even though the login request fails.

**Client IP.** The peer address, unless the peer is listed in `TRUSTED_PROXIES`. Only then is
`X-Forwarded-For` read, and the right-most address that is not a trusted proxy is used, so a
client cannot spoof its IP by prepending entries.

## Who may call what

Enforced by dependencies in `app/api/deps.py`. The table is checked by
`tests/integration/test_access.py`, which fails if any route is missing from it. For every
protected route it asserts: no token → 401, a disallowed role → 403, an allowed role →
neither. "Program manager" means an admin, or faculty assigned to that program.

| Access | Routes |
|---|---|
| Public (per-IP limit) | `GET` jobs, jobs/{id}, jobs/facets, skills, skills/{slug}, skills/demand, roles, trends, recommendations, universities, programs, programs/{id}, programs/{id}/curriculum; `POST` auth/register, auth/login; health (no limit) |
| Refresh cookie | `POST` auth/refresh, auth/logout |
| Any signed-in user | `GET` /me, `DELETE` /me, `POST` auth/logout-all, auth/password; `GET` gap, gap/by-role, gap/reports/{id}, jobs/export (also per-user limit) |
| Student | /me/profile (`GET`, `PUT`, `PATCH`), /me/skills (`GET`, `POST`, `PATCH`, `DELETE`) |
| Program manager | `POST` programs/{id}/curriculum; `GET` programs/{id}/curriculum/documents, curriculum/documents/{id} |
| Admin | /admin/*; `POST` universities, programs; sources; ingestion runs |

An unknown curriculum document id returns 403 to non-admins, the same as a forbidden one,
so ids cannot be probed.

## Personal data and account deletion

The profile holds only what later phases need (university, program, graduation year, target
role, location preference, remote preference, display name) and a self-declared skills list.
There is no phone number, date of birth or gender.

`DELETE /me` (password required) removes the user. Through `ON DELETE CASCADE` it also removes
their refresh tokens, profile, skills and faculty assignments. Audit entries the user made stay,
with `actor_user_id` set to null, and a `user.delete` entry records the deletion without the
email. `test_account_deletion_removes_personal_data` checks every table for rows referencing the
user, and the whole audit log for the email.

## Audit log

`audit_log` records privileged and security-relevant actions: `user.create`, `user.update`
(role, active flag, password reset), `user.delete`, `faculty.assign`, `faculty.unassign`,
`university.create`, `program.create`, `curriculum.upload`, `ingestion.trigger`,
`auth.password_change`, `auth.lockout`, `auth.refresh_reuse`. Each entry carries the request
id, so it links to the request's log lines. Entries hold ids and non-personal details only.
An entry is written in the same transaction as the action it records. Admins read it at
`GET /admin/audit-log`.

## Logging

- Request logs contain the method, path (never the query string), status and duration.
- Every formatted log line, including tracebacks, passes through a redactor
  (`app/core/logging.py`) that masks bearer tokens, JWTs, the refresh cookie, and
  `password` / `token` / `secret` / `app_key` values.
- `test_no_password_token_or_secret_in_logs` runs register, a failed login, a login, a refresh
  and a request with a secret-looking query string. It then asserts that neither the raw log
  records nor the printed output contain the passwords, the tokens or the JWT secret.

## Errors

Errors use the standard shape. A 401 carries `WWW-Authenticate: Bearer`, and a 429 carries
`Retry-After`. Validation errors never echo the submitted input, so passwords are not
reflected back.

## Known limitations and deferred work

- **Email verification and password reset by email** need an email provider, which the stack
  does not have yet. Until then, an admin can reset a password (`PATCH /admin/users/{id}`).
- **Concurrent refreshes from two browser tabs** using the same cookie: the second request
  counts as reuse and ends the session. The Phase 6 frontend must serialise refreshes, for
  example with a single in-flight refresh promise.
- **No multi-factor authentication** yet.
- **Fixed-window rate limits** allow up to twice the limit across a window boundary. That is
  acceptable at these sizes.
- **Proxy-header trust** must be configured (`TRUSTED_PROXIES`) when the API runs behind a
  load balancer (Phase 7).
