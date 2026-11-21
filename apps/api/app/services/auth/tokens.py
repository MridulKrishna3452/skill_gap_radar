"""Access tokens (short-lived JWT, HS256) and opaque refresh-token values.

Access tokens are sent as `Authorization: Bearer`. The role claim is informational: the API
reloads the user on every request, so deactivation and role changes apply immediately.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import Settings
from app.core.errors import UnauthorizedError

ALGORITHM = "HS256"
ACCESS_TYPE = "access"


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_in: int  # seconds


def create_access_token(
    user_id: uuid.UUID, role: str, settings: Settings, *, now: datetime | None = None
) -> AccessToken:
    now = now or datetime.now(tz=UTC)
    ttl = timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "typ": ACCESS_TYPE,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(claims, settings.JWT_SECRET.get_secret_value(), algorithm=ALGORITHM)
    return AccessToken(token, int(ttl.total_seconds()))


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    """Return the user id, or raise UnauthorizedError for any invalid token."""
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET.get_secret_value(),
            algorithms=[ALGORITHM],  # never trust the header's alg (blocks "none" and RS/HS mixups)
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "typ", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid access token") from exc
    if claims.get("typ") != ACCESS_TYPE:
        raise UnauthorizedError("Invalid access token")
    try:
        return uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise UnauthorizedError("Invalid access token") from exc


def new_refresh_value() -> str:
    """256 bits of randomness, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_refresh_value(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
