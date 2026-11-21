"""Password hashing (argon2id) and the password policy.

Parameters are argon2-cffi's defaults (RFC 9106 "low memory" profile: t=3, m=64 MiB, p=4). If
they change, hashes are upgraded on the next successful login (`needs_rehash`).
"""

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.errors import InvalidInputError

MIN_LENGTH = 12
MAX_LENGTH = 128  # bounds hashing cost per request
_hasher = PasswordHasher()
# Verified against when the email is unknown, so response time does not reveal which accounts
# exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,63}$")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-work check: an unknown user (hash None) still costs one verification."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if len(value) > 320 or not _EMAIL.match(value):
        raise InvalidInputError("Enter a valid email address")
    return value


def check_password_policy(password: str, email: str | None = None) -> None:
    """NIST SP 800-63B style: length, not the email, not a trivially repeated character."""
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        problems.append(f"at most {MAX_LENGTH} characters")
    if email and password.strip().lower() in {email.lower(), email.split("@")[0].lower()}:
        problems.append("not your email address")
    if password and len(set(password)) == 1:
        problems.append("not one repeated character")
    if problems:
        raise InvalidInputError("Password must be " + ", ".join(problems))
