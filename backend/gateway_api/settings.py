from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from intentguard.config import ProtocolConfig

# Repository root (backend/gateway_api/settings.py -> ../..), so the root .env and
# experiments/results are found whether the gateway is started from the root or from backend/.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # A .env in the working directory overrides the one at the repository root.
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8",
                                      extra="ignore")

    DATABASE_URL: str = "sqlite:///./intentguard_gateway.db"
    # "http" talks to provider_api over the network; "inprocess" embeds the simulator (zero setup).
    PAYMENT_PROVIDER: str = "http"
    PAYMENT_SERVICE_URL: str = "http://127.0.0.1:8001"
    PROVIDER_TIMEOUT_S: float = 5.0

    WORKER_INTERVAL_S: float = 2.0
    ABSENCE_WINDOW_S: float = 30.0
    MAX_ATTEMPTS: int = 3
    UNKNOWN_REVIEW_AFTER_S: float = 300.0
    POLL_INTERVAL_S: float = 5.0

    DEMO_SEED: bool = True
    RESULTS_DIR: str = str(REPO_ROOT / "experiments" / "results")
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    def protocol(self) -> ProtocolConfig:
        return ProtocolConfig(
            absence_window_s=self.ABSENCE_WINDOW_S,
            max_attempts=self.MAX_ATTEMPTS,
            unknown_review_after_s=self.UNKNOWN_REVIEW_AFTER_S,
            poll_interval_s=self.POLL_INTERVAL_S,
        )


settings = Settings()
