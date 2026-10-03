"""
Mock Payment Service Application.
Completely simulated, isolated financial sandbox for IntentGuard research evaluation.
NEVER CONNECTS TO REAL FINANCIAL ACCOUNTS OR REAL MONEY.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from .routes.refunds import router as refunds_router
from .routes.authorizations import router as authorizations_router
from .routes.faults import router as faults_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mock_payment_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Mock Payment Service Sandbox...")
    logger.info("NOTICE: Isolated research simulation environment. No real funds involved.")
    yield
    logger.info("Stopping Mock Payment Service Sandbox.")


app = FastAPI(
    title="Mock Payment Service Simulator",
    version="1.0.0-research",
    description="Simulated mock payment service for testing financial AI agent safety protocols.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Mock Routers
app.include_router(refunds_router)
app.include_router(authorizations_router)
app.include_router(faults_router)


@app.get("/", tags=["System"])
async def root():
    return {
        "service": "Mock Payment Service Simulator",
        "prototype_notice": "Research Sandbox - NEVER CONNECT TO REAL FINANCIAL ACCOUNTS",
        "supported_workflows": ["REFUND", "PAYMENT_AUTHORIZATION"],
        "status": "active",
        "docs_url": "/docs",
        "health_check": "/health"
    }


@app.get("/health", tags=["System"], status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "healthy",
        "service": "mock-payment-service",
        "simulation_mode": True,
        "live_money_connected": False
    }


@app.get("/info", tags=["System"])
async def system_info():
    return {
        "service": "mock-payment-service",
        "version": "1.0.0-research",
        "capabilities": [
            "refund_settlement",
            "payment_hold_authorization",
            "fault_injection",
            "active_reconciliation_lookup"
        ]
    }
