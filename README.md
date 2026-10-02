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
