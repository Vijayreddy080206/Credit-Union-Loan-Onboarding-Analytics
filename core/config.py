"""
Application settings via pydantic-settings.

Design note: pydantic-settings reads from environment variables AND .env files.
Every config value is typed and validated at startup, so a missing required
env var causes an immediate crash with a clear error — not a silent None bug
discovered hours later in production.
"""
from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "honest-consultant"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://appuser:changeme@postgres:5432/creditunion"

    # LLM
    LLM_PROVIDER: str = "mock"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-haiku-20241022"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_TEXT_MODEL: str = "openai/gpt-oss-120b"
    GROQ_VISION_MODEL: str = "openai/gpt-oss-20b"
    LLM_CONFIDENCE_THRESHOLD: float = 0.80
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_MAX_RETRIES: int = 3

    # CRM
    CRM_PROVIDER: str = "mock"
    MOCK_CRM_URL: str = "http://mock-crm:9000"
    HUBSPOT_API_KEY: str = ""

    # n8n
    N8N_WEBHOOK_BASE_URL: str = "http://n8n:5678/webhook"
    N8N_API_KEY: str = ""

    # Notifications
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    NOTIFICATIONS_FROM_EMAIL: str = "no-reply@creditunion.example.com"
    SLACK_WEBHOOK_URL: str = ""

    # Pipeline thresholds (rules engine)
    MIN_AGE_YEARS: int = 18
    MIN_MONTHLY_INCOME_USD: float = 1500.0
    MAX_LOAN_TO_INCOME_RATIO: float = 5.0
    ID_EXPIRY_BUFFER_DAYS: int = 30

    # Audit
    AUDIT_LOG_LEVEL: str = "INFO"

    @computed_field  # type: ignore[misc]
    @property
    def sync_database_url(self) -> str:
        """Psycopg2-based DSN for Alembic (asyncpg is not compatible)."""
        return self.DATABASE_URL.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — reads .env once at startup."""
    return Settings()


settings = get_settings()
