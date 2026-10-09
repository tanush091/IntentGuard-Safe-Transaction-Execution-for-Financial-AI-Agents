> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

# 03 — Implementation Plan

## Phase 1 — Data Layer
Create SQLite/PostgreSQL models for:
- authorizations
- agent_proposals
- gateway_decisions
- transaction_attempts
- effects
- review_cases

Use SQLAlchemy and Pydantic.

## Phase 2 — Mock Payment Service
Build a separate FastAPI service:
- POST /refunds
- GET /refunds/{refund_id}
- GET /refunds?order_id=...
- POST /refunds/{refund_id}/cancel

Support states:
- pending
- completed
- cancelled
- failed

## Phase 3 — Safety Gateway
Implement:
- authorization matching
- amount/currency validation
- customer/order validation
- operation validation
- duplicate detection
- concurrent-attempt detection
- decision persistence

## Phase 4 — State Machine
Enforce legal transaction transitions and reject invalid transitions.

## Phase 5 — Fault Injection
Implement deterministic faults:
- timeout before execution
- timeout after execution
- service outage
- delayed status
- failed cancellation
- agent crash
- gateway restart

## Phase 6 — Reconciliation
For UNKNOWN outcomes:
1. Query provider.
2. Search by provider transaction ID.
3. Search by order reference.
4. Compare customer, amount, currency, and operation.
5. Resolve as completed, controlled retry, or escalation.

## Phase 7 — LLM Integration
Start with scripted proposals.

Then add an LLM with structured output/tool calling.

The LLM remains outside the trusted execution boundary.

## Phase 8 — Dashboard
Display:
- original authorization
- agent proposal
- gateway decision
- attempts
- provider effects
- current state
- recovery actions
- unresolved cases

## Phase 9 — Research Evaluation
Generate 200–300 reproducible scenarios and compare baselines.

## Recommended Build Order
Refund simulator → deterministic gateway → fault tests → reconciliation → experiments → LLM → second transaction type → dashboard.
