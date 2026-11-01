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

    # Messaging. "log" records outbound messages without sending; a real WhatsApp provider
    # plugs in behind messaging.provider.MessageProvider.
    whatsapp_provider: str = "log"
    whatsapp_webhook_secret: str = ""
    owner_contact: str = ""

    # Background jobs (booking reminders, automatic retention campaigns).
    scheduler_enabled: bool = True

    # WhatsApp chatbot: how much history the model sees and how many tool rounds it may use.
    chat_history_messages: int = 12
    chat_max_tool_rounds: int = 4
    # Most messages one guest may send the bot per hour (it costs money per message). 0 = no limit.
    chat_max_messages_per_hour: int = 30

    # Logging: "text" for people, "json" for log tools.
    log_level: str = "INFO"
    log_format: str = "text"

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
