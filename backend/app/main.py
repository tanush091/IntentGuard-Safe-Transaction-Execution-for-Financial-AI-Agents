"""
IntentGuard Safety Gateway Backend Application.
Academic Research Prototype for Intent-Consistent Financial AI Agent Execution.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.db.database import init_db
from backend.app.api.routes_intents import router as intents_router
from backend.app.api.routes_proposals import router as proposals_router
from backend.app.api.routes_transactions import router as transactions_router
from backend.app.api.routes_reviews import router as reviews_router
from backend.app.api.routes_experiments import router as experiments_router

# Configure logging format
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("intentguard.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing IntentGuard Safety Gateway...")
    logger.info(f"Target Payment Simulator URL: {settings.PAYMENT_SERVICE_URL}")
    init_db()
    logger.info("Relational database schema initialized successfully.")
    yield
    logger.info("Shutting down IntentGuard Safety Gateway.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Academic research prototype placing an intent-consistency safety layer "
        "between an AI agent and simulated financial transaction services."
    ),
    lifespan=lifespan
)

# Enable CORS for local research dashboard and developer tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(intents_router)
app.include_router(proposals_router)
app.include_router(transactions_router)
app.include_router(reviews_router)
app.include_router(experiments_router)


@app.get("/", tags=["System"])
async def root():
    return {
        "project": "IntentGuard",
        "description": "Intent-Consistent Transaction Execution and Recovery for Financial AI Agents",
        "prototype_notice": "Research Prototype / Simulation Only - No Real Financial Connectivity",
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "health_check": "/health"
    }


@app.get("/health", tags=["System"], status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "healthy",
        "service": "intentguard-backend",
        "environment": settings.ENVIRONMENT,
        "database_configured": bool(settings.DATABASE_URL),
        "payment_service_target": settings.PAYMENT_SERVICE_URL
    }


@app.get("/info", tags=["System"])
async def system_info():
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "default_currency": settings.DEFAULT_CURRENCY,
        "default_timeout_seconds": settings.DEFAULT_TIMEOUT_SECONDS,
        "max_attempts_per_intent": settings.MAX_ATTEMPTS_PER_INTENT,
        "llm_provider": settings.LLM_PROVIDER
    }
