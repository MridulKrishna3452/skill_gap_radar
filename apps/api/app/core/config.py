"""Application settings, read from environment variables (and a local .env in development)."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "production"]

MIN_JWT_SECRET_LENGTH = 32


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

    # Timeout for dependency checks in /health/ready, in seconds.
    HEALTHCHECK_TIMEOUT: float = Field(default=2.0, gt=0, le=10)

    @field_validator("CORS_ORIGINS", mode="before")
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
        return self

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
