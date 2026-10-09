"""
IntentGuard gateway HTTP service (contract: docs/API.md; security: docs/SECURITY.md).

Every endpoint is under /api. Agents can only submit proposals for (and read) the intents their
token is scoped to; nothing an agent sends reaches the payment provider except through the engine.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from gateway_api import errors
from gateway_api.reconciliation import record_worker_run
from gateway_api.routers import admin, auth, intents, observability, recovery, reviews, system, webhooks
from gateway_api.seed import seed
from gateway_api.settings import settings
from intentguard.clock import SystemClock
from intentguard.db import init_schema, make_engine, make_session_factory
from intentguard.engine import IntentGuard
from intentguard.models import Policy, ProviderConfig

log = logging.getLogger("intentguard.gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

API = "/api"
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def build_provider() -> tuple[Any, Any]:
    if settings.PAYMENT_PROVIDER == "inprocess":
        from intentguard.providers.inprocess import InProcessProvider
        from paysim import PaymentSimulator

        sim = PaymentSimulator(state_path="paysim_state.json")
        return InProcessProvider(sim), sim
    from intentguard.providers.http import HttpProvider

    return HttpProvider(settings.PAYMENT_SERVICE_URL, timeout_s=settings.PROVIDER_TIMEOUT_S), None


def _apply_stored_config(guard: IntentGuard) -> None:
    """Admin changes survive restarts: protocol policies and the provider connection come from the DB."""
    fields = {"attempt_budget": "max_attempts", "absence_window_s": "absence_window_s",
              "unknown_review_after_s": "unknown_review_after_s"}
    with guard.session() as s:
        for row in s.query(Policy).filter(Policy.key.in_(list(fields))):
            guard.cfg = guard.cfg.without(**{fields[row.key]: row.value})
        cfg = s.get(ProviderConfig, "paysim")
        if cfg is not None and settings.PAYMENT_PROVIDER == "http":
            from intentguard.providers.http import HttpProvider

            guard.provider = HttpProvider(cfg.base_url, timeout_s=cfg.timeout_s)


async def worker_loop(guard: IntentGuard) -> None:
    while True:
        try:
            started = time.time()
            results = await asyncio.to_thread(guard.tick_detailed)
            if results:
                await asyncio.to_thread(record_worker_run, guard, started, results)
                log.info("worker processed %d intent(s)", len(results))
        except Exception:  # noqa: BLE001 - the worker must survive individual failures
            log.exception("worker tick failed")
        await asyncio.sleep(settings.WORKER_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings.jwt_secret()  # fail fast on a short secret; warn if none is configured
    engine = make_engine(settings.DATABASE_URL)
    init_schema(engine)
    provider, sim = build_provider()
    guard = IntentGuard(make_session_factory(engine), provider, SystemClock(), settings.protocol())
    _apply_stored_config(guard)
    app.state.guard, app.state.sim, app.state.settings = guard, sim, settings
    seed(guard, sim)
    recovered = await asyncio.to_thread(guard.startup_recovery)
    log.info("startup recovery: %d intent(s) had orphaned attempts", recovered)
    task = asyncio.create_task(worker_loop(guard))
    yield
    task.cancel()


app = FastAPI(
    title="IntentGuard Gateway",
    version="3.0.0",
    description="Payment execution, recovery and reconciliation between applications or AI agents and a "
                "payment provider. Contract: docs/API.md. Simulated provider only.",
    lifespan=lifespan,
)
errors.install(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-IntentGuard-CSRF", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    rid = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:16]}"
    request.state.request_id = rid[:64]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if not request.url.path.startswith(_DOC_PATHS):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


for r in (auth.router, intents.router, recovery.router, reviews.router, webhooks.router, observability.router,
          admin.router, system.router, system.dev):
    app.include_router(r, prefix=API)


@app.get("/health", include_in_schema=False)
def root_health() -> dict[str, Any]:
    """Liveness at the root too, for launch scripts and container health checks."""
    return {"status": "ok", "service": "intentguard-gateway"}
