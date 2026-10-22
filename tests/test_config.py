import pytest
from pydantic import ValidationError

from restaurant_management_system.config import Settings, get_settings


def test_settings_loads_jwt_secret_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "from-env")

    settings = Settings(_env_file=None)

    assert settings.jwt_secret_key == "from-env"


def test_settings_defaults_match_plan(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "x")

    settings = Settings(_env_file=None)

    assert settings.openai_model == "gpt-4.1-mini"
    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_minutes == 720
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_settings_parses_cors_origins_list(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test","http://b.test"]')

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_settings_requires_jwt_secret(monkeypatch) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    get_settings.cache_clear()

    assert get_settings() is get_settings()
