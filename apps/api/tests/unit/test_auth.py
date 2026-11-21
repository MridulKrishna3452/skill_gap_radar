"""Auth building blocks: passwords, access tokens, client IP, rate parsing, log redaction."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr
from starlette.requests import Request

from app.core.config import Settings, parse_rate
from app.core.errors import InvalidInputError, UnauthorizedError
from app.core.logging import redact
from app.services.auth import passwords
from app.services.auth.ratelimit import client_ip
from app.services.auth.tokens import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_refresh_value,
    new_refresh_value,
)

SETTINGS = Settings(ENV="test", JWT_SECRET=SecretStr("unit-test-secret-" + "y" * 40))
USER = uuid.uuid4()


# ---- passwords --------------------------------------------------------------------------


def test_hash_and_verify() -> None:
    h = passwords.hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert passwords.verify_password(h, "correct horse battery staple")
    assert not passwords.verify_password(h, "wrong password here")
    assert not passwords.needs_rehash(h)


def test_unknown_user_never_verifies() -> None:
    assert not passwords.verify_password(None, "anything at all")
    assert not passwords.verify_password("not-a-hash", "anything at all")


@pytest.mark.parametrize(
    ("password", "fragment"),
    [
        ("short", "at least 12"),
        ("x" * 129, "at most 128"),
        ("aaaaaaaaaaaaaaaa", "repeated"),
        ("student@example.edu", "email"),
    ],
)
def test_password_policy_rejects(password: str, fragment: str) -> None:
    with pytest.raises(InvalidInputError, match=fragment):
        passwords.check_password_policy(password, "student@example.edu")


def test_password_policy_accepts_a_long_passphrase() -> None:
    passwords.check_password_policy("a perfectly fine passphrase", "student@example.edu")


@pytest.mark.parametrize("email", ["no-at-sign", "a@b", "two@@example.com", "x@" + "y" * 300])
def test_invalid_emails(email: str) -> None:
    with pytest.raises(InvalidInputError):
        passwords.normalize_email(email)


def test_email_is_normalised() -> None:
    assert passwords.normalize_email("  Student@Example.EDU ") == "student@example.edu"


# ---- access tokens ------------------------------------------------------------------------


def test_token_round_trip() -> None:
    t = create_access_token(USER, "student", SETTINGS)
    assert t.expires_in == SETTINGS.ACCESS_TOKEN_MINUTES * 60
    assert decode_access_token(t.token, SETTINGS) == USER


def test_expired_token_is_rejected() -> None:
    old = datetime.now(tz=UTC) - timedelta(hours=2)
    t = create_access_token(USER, "student", SETTINGS, now=old)
    with pytest.raises(UnauthorizedError, match="expired"):
        decode_access_token(t.token, SETTINGS)


def test_tampered_token_is_rejected() -> None:
    t = create_access_token(USER, "student", SETTINGS).token
    header, payload, sig = t.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["role"] = "admin"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    with pytest.raises(UnauthorizedError):
        decode_access_token(f"{header}.{forged}.{sig}", SETTINGS)


def _claims(**over: object) -> dict[str, object]:
    now = int(datetime.now(tz=UTC).timestamp())
    base: dict[str, object] = {
        "sub": str(USER),
        "role": "student",
        "typ": "access",
        "iss": SETTINGS.JWT_ISSUER,
        "aud": SETTINGS.JWT_AUDIENCE,
        "iat": now,
        "exp": now + 600,
    }
    return {k: v for k, v in (base | over).items() if v is not None}


@pytest.mark.parametrize(
    "claims",
    [
        _claims(aud="someone-else"),
        _claims(iss="someone-else"),
        _claims(typ="refresh"),
        _claims(sub="not-a-uuid"),
        _claims(exp=None),
        _claims(sub=None),
    ],
)
def test_invalid_claims_are_rejected(claims: dict[str, object]) -> None:
    token = jwt.encode(claims, SETTINGS.JWT_SECRET.get_secret_value(), algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedError):
        decode_access_token(token, SETTINGS)


def test_unsigned_and_foreign_tokens_are_rejected() -> None:
    unsigned = jwt.encode(_claims(), key="", algorithm="none")
    with pytest.raises(UnauthorizedError):
        decode_access_token(unsigned, SETTINGS)
    foreign = jwt.encode(_claims(), "another-secret-" + "z" * 40, algorithm=ALGORITHM)
    with pytest.raises(UnauthorizedError):
        decode_access_token(foreign, SETTINGS)
    with pytest.raises(UnauthorizedError):
        decode_access_token("not a jwt", SETTINGS)


def test_refresh_values_are_random_and_stored_hashed() -> None:
    a, b = new_refresh_value(), new_refresh_value()
    assert a != b and len(a) >= 43
    assert hash_refresh_value(a) != a and len(hash_refresh_value(a)) == 64


# ---- settings, client IP, redaction -------------------------------------------------------


def test_dev_settings_generate_a_secret_but_production_requires_one() -> None:
    s = Settings(ENV="development", JWT_SECRET=SecretStr(""))
    assert s.jwt_secret_generated and len(s.JWT_SECRET.get_secret_value()) >= 32
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(ENV="production", JWT_SECRET=SecretStr(""), CORS_ORIGINS="https://a.example")


def test_parse_rate() -> None:
    assert parse_rate("5/60") == (5, 60)
    for bad in ("5", "a/b", "0/60", "5/0"):
        with pytest.raises(ValueError):
            parse_rate(bad)


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_client_ip_trusts_forwarded_for_only_from_trusted_proxies() -> None:
    plain = Settings(ENV="test")
    assert client_ip(_request("203.0.113.9", "1.2.3.4"), plain) == "203.0.113.9"
    proxied = Settings(ENV="test", TRUSTED_PROXIES="10.0.0.1")
    assert client_ip(_request("10.0.0.1", "1.2.3.4"), proxied) == "1.2.3.4"
    # A client cannot spoof its address by prepending entries: the right-most untrusted wins.
    assert client_ip(_request("10.0.0.1", "6.6.6.6, 1.2.3.4"), proxied) == "1.2.3.4"
    assert client_ip(_request("10.0.0.1", "garbage"), proxied) == "10.0.0.1"


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


# A JWT-shaped string built at runtime (no token literal in the repository for secret scanners
# to flag): {"alg":"HS256"}.{"sub":"1"}.signature
_FAKE_JWT = ".".join(_b64(p) for p in ('{"alg":"HS256"}', '{"sub":"1"}', "signature"))


@pytest.mark.parametrize(
    "line",
    [
        "Authorization: Bearer abc.def-ghi",
        f"token {_FAKE_JWT}",
        "Cookie: sr_refresh=Zx9abc; other=1",
        '{"password": "hunter2hunter2"}',
        "https://api.adzuna.com/v1/api/jobs/in/search/1?app_id=1&app_key=SECRETVALUE",
        "current_password=abcdefghijkl",
    ],
)
def test_redaction(line: str) -> None:
    out = redact(line)
    for secret in ("abc.def-ghi", _b64("signature"), "Zx9abc", "hunter2hunter2", "SECRETVALUE"):
        assert secret not in out
    assert "abcdefghijkl" not in out
    assert "REDACTED" in out


def test_redaction_keeps_ordinary_text() -> None:
    assert redact("password policy updated for 3 users") == "password policy updated for 3 users"
