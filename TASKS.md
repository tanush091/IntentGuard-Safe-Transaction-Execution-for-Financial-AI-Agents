# Task Breakdown (TASKS.md) — IntentGuard

## Phase 1: Data Layer & Identity Schemas
- [x] **TASK-001**: Define Pydantic types and schemas for authorizations, proposals, attempts, effects, decisions, and review cases (`src/schemas/types.py`)
- [x] **TASK-002**: Implement SQLAlchemy ORM models for durable effects ledger and audit log (`src/database/models.py`)
- [x] **TASK-003**: Create database connection and initialization lifecycle (`src/database/connection.py`)

## Phase 2: Mock Payment Service & Fault Injection
- [x] **TASK-004**: Implement mock payment service with refund APIs (`POST /refunds`, `GET /refunds`, `POST /cancel`)
- [x] **TASK-005**: Add secondary payment authorization and hold workflow (`POST /payments/authorizations`)
- [x] **TASK-006**: Build configurable fault injection engine for timeouts before/after execution, 503 outages, delayed statuses, and amount corruptions (`src/mock_payment/faults.py`)

## Phase 3: Safety Gateway & State Machine
- [x] **TASK-007**: Implement formal transaction state machine with legal transition enforcement (`src/gateway/state_machine.py`)
- [x] **TASK-008**: Build gateway validator for order, customer, amount, currency, and concurrency checks (`src/gateway/validator.py`)
- [x] **TASK-009**: Implement active reconciliation engine to discover provider effects upon `UNKNOWN` outcomes (`src/gateway/reconciliation.py`)
- [x] **TASK-010**: Implement state-aware recovery policies (cancel-and-verify, controlled retry, human review escalation) (`src/gateway/recovery.py`)
- [x] **TASK-011**: Assemble Gateway coordinator engine and REST API (`src/gateway/engine.py`, `src/gateway/api.py`)

## Phase 4: AI Agents
- [x] **TASK-012**: Build scripted agents with faithful and flawed profiles for reproducible benchmarks (`src/agent/scripted_agent.py`)
- [x] **TASK-013**: Implement natural language customer support extraction agent with offline deterministic parser fallback (`src/agent/llm_agent.py`)

## Phase 5: Empirical Benchmark & Ablations
- [x] **TASK-014**: Create synthetic scenario generator producing 250 reproducible scenarios with fixed seeds across 12 failure modes (`src/experiments/generator.py`)
- [x] **TASK-015**: Implement 4 baseline architectures (Direct Access, Fixed Validation, Idempotency Alone, LLM Reviewer) alongside IntentGuard (`src/experiments/baselines.py`)
- [x] **TASK-016**: Implement 6 ablation studies isolating individual protocol components (`src/experiments/ablations.py`)
- [x] **TASK-017**: Build benchmark execution suite and export results to JSON (`src/experiments/runner.py`, `run_benchmark.py`)

## Phase 6: Observability Dashboard & UX
- [x] **TASK-018**: Build modern glassmorphic dashboard interface (`src/dashboard/index.html`, `style.css`)
- [x] **TASK-019**: Implement interactive client-side logic for 4 prescribed demos, custom transaction submission, live visual state machine, and review case resolution (`src/dashboard/app.js`)
- [x] **TASK-020**: Mount static dashboard routes on FastAPI gateway (`src/gateway/api.py`)

## Phase 7: Verification & Research Deliverables
- [x] **TASK-021**: Create comprehensive `pytest` test suites across all modules (`tests/`)
- [x] **TASK-022**: Author complete academic research paper manuscript (`RESEARCH_PAPER_MANUSCRIPT.md`)
- [x] **TASK-023**: Configure multi-container Docker Compose deployment (`docker-compose.yml`, `Dockerfile`)
