# Phase 0: IntentGuard Project Foundation & Final Documentation

> **Official Document Location**: [`docs/PHASE_0.md`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/docs/PHASE_0.md)  
> **Status**: **Phase 0 Complete** — Fully implemented, benchmarked, tested, and documented.

---

## Executive Summary

**IntentGuard** is an intent-consistent transaction execution and recovery protocol for financial AI agents operating under uncertain outcomes.

### The Problem
Autonomous AI agents initiating financial transactions (e.g. refunds or payment authorizations) introduce severe vulnerabilities:
- Parameter hallucinations (e.g. proposing ₹15,000 for a ₹1,500 authorization).
- Blind retries upon network timeouts, yielding double refunds.
- Changed request IDs after agent restarts that bypass standard client-level idempotency keys.
- False claims of transaction reversal when only internal agent state was restored.

### What We Have Built
1. **Durable Data Layer & Ledger** ([`src/database/models.py`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/src/database/models.py)): Authorizations, proposals, decisions, attempts, durable effects ledger, review cases, and immutable audit logs.
2. **Mock Payment Service & Fault Engine** ([`src/mock_payment/service.py`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/src/mock_payment/service.py)): Simulating refunds, payment authorizations, and 6 failure modes (timeouts, 503 outages, delayed state, corrupt amounts).
3. **Deterministic Safety Gateway** ([`src/gateway/`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/src/gateway)): Formal state machine, pre-execution validator, active reconciliation engine, and state-aware recovery policies.
4. **AI Agents** ([`src/agent/`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/src/agent)): Scripted agents with distinct behavioral profiles and natural language support instruction parser.
5. **Empirical Benchmark Suite** ([`src/experiments/`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/src/experiments)): 250 synthetic scenarios across 12 failure classes, comparing 5 baseline architectures and 6 ablation variants.
6. **Glassmorphic Observability Dashboard** ([`src/dashboard/`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/src/dashboard)): Interactive UI with 1-click demos, live visual state machine, autoscrolling trace, effects ledger, and operator escalation resolver.
7. **Automated Test Suite** ([`tests/`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/tests)): 11 unit, integration, and e2e test suites passing with 100% green status.
8. **Academic Research Manuscript** ([`docs/RESEARCH_PAPER_MANUSCRIPT.md`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/docs/RESEARCH_PAPER_MANUSCRIPT.md)): Complete publication-ready paper.
9. **Container Deployment** ([`docker-compose.yml`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/docker-compose.yml), [`Dockerfile`](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/Dockerfile)): Multi-container Docker configuration with PostgreSQL.

### Key Benchmark Findings (N = 250 Scenarios, Seed = 42)
- **Duplicate Financial Effects**: Baselines A, B, and D suffered 42 duplicates; Baseline C suffered 21 duplicates. **IntentGuard produced 0 duplicate effects.**
- **Uncontained Incorrect Transactions**: Baselines A and C executed 42 incorrect transactions. **IntentGuard permitted 0 uncontained incorrect transactions.**
- **Monetary Discrepancies**: Baselines produced up to ₹505,000 in uncontained loss. **IntentGuard achieved ₹0.00 uncontained discrepancy.**
- **Legitimate Task Completion**: IntentGuard achieved **83.2% overall completion** (and **98.4% across legitimate-eligible requests**) compared to 32.8% - 49.6% for standard baselines.

---

For the full detailed deep-dive, diagrams, and operational commands, read:
👉 [**`docs/PHASE_0.md`**](file:///c:/Users/srith/OneDrive/Desktop/HACKATHONS/Nextgen/IntentGuard_Project_Research_Documentation/IntentGuard_Documentation/docs/PHASE_0.md)
