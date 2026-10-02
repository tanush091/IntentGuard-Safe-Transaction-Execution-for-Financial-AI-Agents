# IntentGuard: Intent-Consistent Transaction Execution and Recovery for Financial AI Agents

## Recommended Project Title
**IntentGuard: Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes**

### Short title
**IntentGuard**

## Project Summary
IntentGuard is a safety and reliability protocol for financial AI agents. The AI agent can interpret a user/operator request and propose a transaction, but it cannot directly execute the financial operation. A deterministic safety gateway validates the proposal against a durable authorization record, controls execution, tracks attempts, observes actual provider effects, and safely handles timeouts, crashes, retries, duplicates, cancellation, and escalation.

Refunds are the primary workflow. Payment authorization and cancellation are used as a secondary workflow to evaluate transferability.

## Core Principle
**Authorization → Proposal → Validation → Execution → Observation → Reconciliation → Final Resolution**

The system treats the externally observed financial effect as the source of truth rather than assuming that an API response or restored internal state proves what happened.

## Main Features
- Intent binding
- Authorization validation
- AI transaction proposal
- Safety gateway
- Transaction state machine
- Idempotency and duplicate prevention
- Durable effects ledger
- Timeout/unknown-outcome handling
- State-aware recovery
- Controlled retries
- Cancellation and verification
- Crash recovery
- Concurrent-agent protection
- Fault injection
- Audit logging
- Human escalation
- Research benchmark and ablation testing
- Monitoring dashboard

## Technology Stack
- Python
- FastAPI
- Pydantic
- SQLite default, PostgreSQL via DATABASE_URL
- SQLAlchemy
- Vanilla HTML/CSS/JS
- pytest
- Docker Compose
- Optional: Celery + Redis
- Optional LLM: Gemini, OpenAI, or Ollama

## Research Question
Can an intent-consistent transaction protocol reduce incorrect and duplicate final financial outcomes under timeouts, crashes, concurrent attempts, and changed retries while preserving legitimate-task completion?

## Getting Started & Running the Dashboard

You can start the IntentGuard Gateway and the Mock Payment Service via Docker Compose. This automatically spins up a PostgreSQL database and exposes the interactive dashboard.

1. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
2. (Optional) Set your `LLM_API_KEY` (e.g., `GEMINI_API_KEY` or `OPENAI_API_KEY`) in `.env` if you want to use the live LLM chat panel. Otherwise, it defaults to offline rule-based extraction.
3. Start the services:
   ```bash
   docker-compose up -d
   ```
4. Access the Interactive Studio Dashboard at: **http://127.0.0.1:8000**

You can also run the research benchmark suite locally:
```bash
python run_multiple_seeds.py
```
