"""
Application Configuration for IntentGuard Backend Service.
Loads configuration from environment variables with sensible research defaults.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Application Settings
    APP_NAME: str = "IntentGuard Safety Gateway"
    APP_VERSION: str = "1.0.0-research"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Gateway Server Network Bindings
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000

    # Persistence Configuration
    DATABASE_URL: str = Field(
        default="sqlite:///./intentguard.db",
        description="SQLAlchemy database connection URI (SQLite or PostgreSQL)"
    )

    # Mock Payment Service Connection
    PAYMENT_SERVICE_URL: str = Field(
        default="http://127.0.0.1:8001",
        description="URL of the isolated mock payment simulator"
    )

    # Transaction Protocol Parameters
    DEFAULT_TIMEOUT_SECONDS: float = 3.0
    RECONCILIATION_INTERVAL_SECONDS: float = 2.0
    MAX_ATTEMPTS_PER_INTENT: int = 3
    DEFAULT_CURRENCY: str = "INR"

    # Optional LLM Configuration
    LLM_PROVIDER: str = "offline"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "gemini-1.5-flash"


settings = Settings()
