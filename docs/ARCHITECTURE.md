# Architecture Document (ARCHITECTURE.md) — IntentGuard

## Technology Stack
- **AI Agent Interface**: Python tool-calling interface (Scripted agents for benchmarks, LLM parser for natural language).
- **Safety Protocol**: FastAPI + Pydantic v2
- **Durable Storage**: SQLAlchemy 2.0 ORM + SQLite (development/portable) & PostgreSQL (production Docker)
- **Payment Simulator**: Standalone FastAPI service with configurable fault injection
- **Observability Dashboard**: Vanilla HTML5 + CSS3 (Glassmorphism & dark mode tokens) + JavaScript (ES6 Modules)
- **Testing & Benchmarks**: Pytest + AsyncIO + Synthetic Scenario Generator

## System Architecture Diagram
```
Operator / Support Instruction
             │
             ▼
   [ Autonomous AI Agent ] (Untrusted Context)
             │ Proposes: {intent_id, customer_id, order_id, amount, op}
             ▼
   [ Intent Safety Gateway ] ◄──► [ PostgreSQL / SQLite Ledger ]
      ├── Authorization Validator
      ├── Transaction State Machine
      ├── Concurrency Lock (In-Flight Attempt Guard)
      └── State-Aware Recovery Engine
             │ Dispatches verified requests only
             ▼
   [ Mock Payment Service ] ◄──► [ Active Reconciliation Engine ]
      ├── POST /refunds            (Queries by order on UNKNOWN)
      ├── GET /refunds?order_id=...
      └── Fault Injection Engine
```

## Security & Trust Boundary
- **Rule 1**: The AI Agent NEVER receives payment service credentials or direct network routes.
- **Rule 2**: Only the Safety Gateway owns submission, retry evaluation, cancellation, and final resolution.
- **Rule 3**: Provider effect is the single source of truth. Internal agent memory resets never constitute a transaction reversal.

## Transaction State Machine
| Current State      | Allowed Next States                                          |
|--------------------|--------------------------------------------------------------|
| AUTHORIZED         | PROPOSED, BLOCKED                                            |
| PROPOSED           | VALIDATED, EXECUTING, BLOCKED, COMPLETED                     |
| VALIDATED          | EXECUTING, BLOCKED, COMPLETED                                |
| EXECUTING          | COMPLETED, UNKNOWN, CANCEL_REQUESTED, ESCALATED, BLOCKED     |
| UNKNOWN            | RECONCILING, ESCALATED                                       |
| RECONCILING        | COMPLETED, EXECUTING, CANCEL_REQUESTED, ESCALATED, UNKNOWN   |
| CANCEL_REQUESTED   | CANCELLED, ESCALATED                                         |
| CANCELLED          | (Terminal)                                                   |
| COMPLETED          | (Terminal)                                                   |
| BLOCKED            | PROPOSED                                                     |
| ESCALATED          | COMPLETED, CANCELLED                                         |

## Folder Structure
```
IntentGuard_Documentation/
├── PRD.md
├── ARCHITECTURE.md
├── DESIGN.md
├── RULES.md
├── TASKS.md
├── DECISIONS.md
├── MEMORY.md
├── TEST_PLAN.md
├── SECURITY.md
├── .env.example
├── .gitignore
├── requirements.txt
├── pytest.ini
├── docker-compose.yml
├── Dockerfile
├── run_benchmark.py
├── benchmark_results.json
├── RESEARCH_PAPER_MANUSCRIPT.md
├── src/
│   ├── config.py
│   ├── schemas/        # Pydantic data transfer objects
│   ├── database/       # SQLAlchemy models & connection pool
│   ├── mock_payment/   # Payment simulation & fault engine
│   ├── gateway/        # Validation, state machine, reconciliation & recovery
│   ├── agent/          # Scripted and LLM agents
│   ├── experiments/    # Benchmark generator, baselines, ablations & runner
│   └── dashboard/      # Web observability interface (HTML, CSS, JS)
└── tests/              # 6 unit & integration test suites
```

## Architectural Invariants
1. Database operations belong strictly in database models and gateway engine services, not in UI or agent scripts.
2. The gateway must record decisions and attempts in durable storage *before* issuing any external network call.
3. Every execution attempt generates a unique `attempt_id`, but anchors to the parent `intent_id` for idempotency deduplication.
