from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Restaurant Management System"
    environment: str = "development"
    timezone: str = "Asia/Kolkata"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/restaurant"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
