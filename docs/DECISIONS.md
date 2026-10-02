# Architecture Decision Records (DECISIONS.md) — IntentGuard

## ADR-001: SQLite Default with Dual PostgreSQL Support
- **Decision**: Use SQLite as the default local development database (`intentguard.db`) while fully supporting PostgreSQL via `DATABASE_URL` in Docker Compose.
- **Reason**: Allows seamless offline developer execution, rapid local testing with zero external daemon requirements, while remaining enterprise-ready for containerized multi-node deployments.

## ADR-002: Intent-Anchored Idempotency vs. Request-Level Idempotency
- **Decision**: Derive provider idempotency keys from the business `intent_id` (`idem_{intent_id}`) rather than using the agent's raw `request_id`.
- **Reason**: In autonomous AI workflows, an agent crash or restart generates a fresh `request_id` for the identical business request. Standard client-level idempotency interprets the restart as a new transaction and double-refunds. Anchoring to `intent_id` ensures deterministic deduplication across arbitrary process restarts.

## ADR-003: Decoupled Mock Payment Service
- **Decision**: Implement the simulated payment provider as an independent FastAPI service and state machine rather than an in-memory dictionary embedded in the gateway.
- **Reason**: Mirrors realistic network boundaries, allows physical HTTP transport simulation, enables genuine connection drops, and preserves clean architectural isolation between the trusted gateway and external banking infrastructure.

## ADR-004: Active Post-Execution Reconciliation Over Blind Retries
- **Decision**: Treat all network timeouts as `UNKNOWN`, mark the intent in `RECONCILING`, and actively discover existing provider effects by order reference before allowing any retry.
- **Reason**: Eliminates the "lost response" duplicate refund vulnerability where a transaction succeeds at the payment processor but the response drops before reaching the client.

## ADR-005: Deterministic Extraction Fallback in AI Agent
- **Decision**: Equip the AI Agent with an intelligent deterministic parameter extractor alongside optional Gemini/OpenAI tool-calling hooks.
- **Reason**: Ensures the benchmark suite and local demos execute deterministically, offline, and without incurring third-party API costs or rate limit failures.
