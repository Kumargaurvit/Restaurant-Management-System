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
    bcrypt_rounds: int = 12

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    # Inbound chat webhook is disabled until this secret is set.
    webhook_secret: str = ""
    messaging_provider: str = "console"
    chat_history_messages: int = 12
    chat_max_tool_rounds: int = 4

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
