"""Application settings, read from environment variables (and a local .env in development)."""

import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "production"]

MIN_JWT_SECRET_LENGTH = 32
RATE_LIMIT_SETTINGS = (
    "RATE_LIMIT_LOGIN",
    "RATE_LIMIT_LOGIN_IP",
    "RATE_LIMIT_REGISTER",
    "RATE_LIMIT_REFRESH",
    "RATE_LIMIT_EXPENSIVE",
    "RATE_LIMIT_PUBLIC",
)


def parse_rate(value: str) -> tuple[int, int]:
    """'5/60' -> (5 requests, 60 seconds)."""
    try:
        count, seconds = (int(part) for part in value.split("/"))
    except ValueError as exc:
        raise ValueError(f"Rate limit '{value}' must look like '<count>/<seconds>'") from exc
    if count < 1 or seconds < 1:
        raise ValueError(f"Rate limit '{value}' must be positive")
    return count, seconds


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repo-root .env (shared with docker compose), then an optional apps/api/.env override.
        # Neither file exists inside the container, where config comes from the environment.
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "SkillRadar AI"
    APP_VERSION: str = "2.0.0.dev0"
    ENV: Environment = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    API_PREFIX: str = "/api/v1"

    # Defaults match the docker compose host ports (see .env.example).
    DATABASE_URL: str = "postgresql+asyncpg://skillradar:skillradar@127.0.0.1:5433/skillradar"
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)

    REDIS_URL: str = "redis://127.0.0.1:6380/0"

    # NoDecode: accept a plain comma-separated string instead of JSON.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    JWT_SECRET: SecretStr = SecretStr("")

    # Authentication (Phase 2; design in docs/security.md).
    JWT_ISSUER: str = "skillradar-api"
    JWT_AUDIENCE: str = "skillradar"
    ACCESS_TOKEN_MINUTES: int = Field(default=15, ge=1, le=60)
    REFRESH_TOKEN_DAYS: int = Field(default=14, ge=1, le=60)
    # A refresh-token family (one login) can be rotated for at most this long.
    REFRESH_FAMILY_MAX_DAYS: int = Field(default=30, ge=1, le=180)
    # The refresh cookie is Secure unless this is turned off (only allowed outside production,
    # for plain-http local development).
    COOKIE_SECURE: bool = True
    ALLOW_REGISTRATION: bool = True
    LOGIN_MAX_FAILURES: int = Field(default=5, ge=1, le=50)
    LOCKOUT_MINUTES: int = Field(default=15, ge=1, le=1440)
    # Rate limits: "<count>/<seconds>".
    RATE_LIMIT_LOGIN: str = "5/60"
    RATE_LIMIT_LOGIN_IP: str = "20/3600"
    RATE_LIMIT_REGISTER: str = "5/3600"
    RATE_LIMIT_REFRESH: str = "30/60"
    RATE_LIMIT_EXPENSIVE: str = "30/60"
    RATE_LIMIT_PUBLIC: str = "120/60"
    # Proxies whose X-Forwarded-For header is trusted for the client IP (exact IPs).
    TRUSTED_PROXIES: Annotated[list[str], NoDecode] = []

    # Timeout for dependency checks in /health/ready, in seconds.
    HEALTHCHECK_TIMEOUT: float = Field(default=2.0, gt=0, le=10)

    # Adzuna job search API (https://developer.adzuna.com). Empty = connector disabled.
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: SecretStr = SecretStr("")
    ADZUNA_BASE_URL: str = "https://api.adzuna.com/v1/api"
    # Free-tier keys allow a limited number of calls per minute; stay well under it.
    ADZUNA_MIN_SECONDS_BETWEEN_CALLS: float = Field(default=3.0, ge=0)
    ADZUNA_MAX_PAGES_PER_RUN: int = Field(default=20, ge=1, le=200)

    # Curriculum uploads.
    CURRICULUM_MAX_BYTES: int = Field(default=15 * 1024 * 1024, ge=1024)
    CURRICULUM_MAX_PAGES: int = Field(default=300, ge=1)

    # Analytics defaults.
    ANALYTICS_DEFAULT_WINDOW_MONTHS: int = Field(default=6, ge=1, le=60)
    # Below this many postings in a window, demand-based numbers are flagged as low-sample.
    ANALYTICS_MIN_POSTINGS: int = Field(default=30, ge=1)

    @property
    def adzuna_enabled(self) -> bool:
        return bool(self.ADZUNA_APP_ID and self.ADZUNA_APP_KEY.get_secret_value())

    @field_validator("CORS_ORIGINS", "TRUSTED_PROXIES", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _no_wildcard_origin(cls, value: list[str]) -> list[str]:
        # The API uses credentialed requests (cookies), which must never be combined with "*".
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
        return value

    @model_validator(mode="after")
    def _production_requirements(self) -> "Settings":
        if self.ENV == "production":
            if len(self.JWT_SECRET.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
                raise ValueError(
                    f"JWT_SECRET must be set to at least {MIN_JWT_SECRET_LENGTH} characters "
                    "in production"
                )
            if any(o.startswith("http://") and "localhost" not in o for o in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must use https")
            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE cannot be turned off in production")
        elif len(self.JWT_SECRET.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            # Development and tests only: a random per-process secret, so the app runs without
            # configuration. Tokens do not survive a restart; the app logs a warning at startup.
            self.JWT_SECRET = SecretStr(secrets.token_urlsafe(48))
            self._generated_jwt_secret = True
        for name in RATE_LIMIT_SETTINGS:
            parse_rate(getattr(self, name))
        return self

    _generated_jwt_secret: bool = PrivateAttr(default=False)

    @property
    def jwt_secret_generated(self) -> bool:
        return self._generated_jwt_secret

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
