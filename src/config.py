import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "IntentGuard"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./intentguard.db")
    GATEWAY_HOST: str = "127.0.0.1"
    GATEWAY_PORT: int = 8000
    PAYMENT_SERVICE_HOST: str = "127.0.0.1"
    PAYMENT_SERVICE_PORT: int = 8001
    PAYMENT_SERVICE_URL: str = os.getenv("PAYMENT_SERVICE_URL", "http://127.0.0.1:8001")
    DEFAULT_TIMEOUT_SECONDS: float = 3.0
    RECONCILIATION_INTERVAL_SECONDS: float = 2.0
    MAX_ATTEMPTS_PER_INTENT: int = 3

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
