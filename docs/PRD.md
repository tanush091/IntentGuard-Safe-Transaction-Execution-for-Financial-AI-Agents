# Product Requirements Document (PRD) — IntentGuard

## Product
**IntentGuard**: Intent-Consistent Transaction Execution and Recovery Protocol for Financial AI Agents

## Problem (Why)
Autonomous AI agents can interpret customer-support requests and initiate financial operations (e.g. refunds, payment authorizations). However:
- A successful HTTP response does not guarantee that the authorized business operation was carried out.
- The agent may hallucinate the amount (e.g., refunding ₹15,000 instead of ₹1,500) or order number (transposing `ORD-204` to `ORD-240`).
- Under timeouts or network drops, naive agents repeat requests, causing duplicate charges or refunds.
- Following an agent crash/restart, a new request ID is generated for the same instruction, completely bypassing standard client-level idempotency keys.
- Agents often falsely report transactions as "reversed" when only internal conversational memory was reset.

## Target Users
- Financial Institution Engineering Teams & FinTech Platforms
- Autonomous Agent Developers deploying tool-calling agents in production
- Operations & Compliance Reviewers requiring non-rewritable audit trails

## Goal
Build a deterministic transaction-safety gateway that sits between autonomous AI agents and payment services to eliminate duplicate and unauthorized financial effects, safely reconcile uncertain outcomes, and enforce state-aware recovery.

## Core Features
1. **Durable Intent Binding**: Anchors every transaction proposal to an immutable authorization record (`intent_id`).
2. **Deterministic Pre-Execution Validation**: Verifies order, customer, operation, currency, and amount limit prior to API dispatch.
3. **Formal Transaction State Machine**: Enforces valid state transitions and isolates terminal states.
4. **Active Reconciliation Engine**: Queries payment provider on `UNKNOWN` outcomes to discover true financial effect before permitting retries.
5. **State-Aware Recovery**: Cancels pending transactions with external verification; escalates discrepancies to human review.
6. **Intent-Anchored Idempotency**: Deduplicates transactions even across agent crashes and restarts.
7. **Durable Effects Ledger**: Immutable database record of verified external financial effects.
8. **Interactive Observability Dashboard**: Visual state flow, 1-click prescribed demos, audit logs, and review case resolver.

## MVP Scope (v1.0)
- Refund workflow simulation with full fault injection (pre/post timeouts, outages, delayed state, corrupt amount).
- Secondary payment authorization and hold cancellation workflow (transferability evaluation).
- 250-scenario reproducible benchmark comparing 5 baseline architectures and 6 ablation variants.
- Full unit and integration test suite (`pytest`).
- Glassmorphic web observability dashboard.

## Out of Scope (What is NOT in v1)
- Live production banking rails / real card network integrations (simulated provider only).
- Multi-currency dynamic FX conversion (strictly matches authorized currency).
- Direct user login / social authentication (operator-facing and API-authenticated).

## Success Criteria
1. Zero duplicate completed financial effects across timeouts, restarts, and concurrent requests.
2. Zero unauthorized or hallucinated transactions executed at the payment provider.
3. 100% of detected provider discrepancies escalated to human review with open `ReviewCase` records.
4. High legitimate completion rate (>80% overall, >95% on legitimate-eligible tasks).
5. All 11 automated test suites passing with 100% green status.
