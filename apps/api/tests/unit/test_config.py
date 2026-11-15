import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.workers.tasks import ping


def test_cors_origins_accepts_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://app.example.com")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.CORS_ORIGINS == ["http://localhost:3000", "https://app.example.com"]


def test_wildcard_cors_rejected() -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        Settings(CORS_ORIGINS=["*"])


def test_production_requires_strong_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(ENV="production", JWT_SECRET="short", CORS_ORIGINS=["https://app.example.com"])


def test_production_rejects_plain_http_origin() -> None:
    with pytest.raises(ValidationError, match="https"):
        Settings(ENV="production", JWT_SECRET="x" * 40, CORS_ORIGINS=["http://app.example.com"])


def test_production_settings_valid_with_secret_and_https() -> None:
    settings = Settings(
        ENV="production", JWT_SECRET="x" * 40, CORS_ORIGINS=["https://app.example.com"]
    )
    assert settings.is_production
    assert "x" * 40 not in repr(settings)  # SecretStr never prints its value


def test_ping_task_runs() -> None:
    assert ping()["status"] == "ok"
