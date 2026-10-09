from __future__ import annotations

import logging
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from intentguard.config import ProtocolConfig
from intentguard.envfile import load_env

# Repository root (backend/gateway_api/settings.py -> ../..), so the root .env and
# experiments/results are found whether the gateway is started from the root or from backend/.
REPO_ROOT = Path(__file__).resolve().parents[2]

# Variables read with os.getenv elsewhere (LLM_*, SIMULATOR_MODE in tools) also come from .env.
load_env()

log = logging.getLogger("intentguard.gateway")


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

    # Simulator-only endpoints (/api/dev/*) exist only when this is true (docs/SECURITY.md section 11).
    SIMULATOR_MODE: bool = False
    # Demo users and orders on first start (sandbox only; passwords from DEMO_PASSWORD).
    DEMO_SEED: bool = True
    DEMO_PASSWORD: str = "intentguard-demo"
    # First admin when the users table is empty and DEMO_SEED is off.
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    # Authentication (docs/SECURITY.md section 3). HS256 needs a secret of at least 32 bytes.
    JWT_SECRET: str = ""
    JWT_ISSUER: str = "intentguard"
    JWT_AUDIENCE: str = "intentguard-api"
    ACCESS_TOKEN_TTL_S: int = 900
    AGENT_TOKEN_MAX_TTL_S: int = 300
    REFRESH_TOKEN_TTL_S: int = 7 * 24 * 3600
    REFRESH_TOKEN_ABSOLUTE_S: int = 30 * 24 * 3600
    COOKIE_SECURE: bool = True
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_S: int = 900
    RATE_LIMIT_PER_MINUTE: int = 1200
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 20

    # Provider webhooks: shared HMAC secret for signature verification.
    WEBHOOK_SECRET: str = ""
    WEBHOOK_TOLERANCE_S: int = 300

    RESULTS_DIR: str = str(REPO_ROOT / "experiments" / "results")
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    def protocol(self) -> ProtocolConfig:
        return ProtocolConfig(
            absence_window_s=self.ABSENCE_WINDOW_S,
            max_attempts=self.MAX_ATTEMPTS,
            unknown_review_after_s=self.UNKNOWN_REVIEW_AFTER_S,
            poll_interval_s=self.POLL_INTERVAL_S,
        )

    def jwt_secret(self) -> str:
        if not self.JWT_SECRET:
            # Development fallback: tokens stop working when the process restarts.
            self.JWT_SECRET = secrets.token_urlsafe(48)
            log.warning("JWT_SECRET is not set; using a random per-process secret (development only)")
        if len(self.JWT_SECRET.encode()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return self.JWT_SECRET


settings = Settings()
