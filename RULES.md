# Development Rules (RULES.md) — IntentGuard

## General Coding Standards
- Maintain strict typing with Pydantic v2 schemas and SQLAlchemy 2.0 type hints.
- Keep business logic isolated inside gateway engines and domain services; never place SQL queries in route handlers or UI scripts.
- Do not modify unrelated files during bug fixes or refactoring.
- Maintain documentation integrity: every state machine change must be reflected in documentation.

## Pre-Coding Invariants
- Read `PRD.md`, `ARCHITECTURE.md`, `RULES.md`, and `TASKS.md` before writing code.
- Review existing models in `src/database/models.py` before creating new database entities.
- Never write credentials or hardcoded keys into source files (use `src/config.py` and `.env`).

## Financial Safety Boundary Invariants
1. **Zero Direct Agent Access**: The agent layer (`src/agent/`) must NEVER hold credentials or endpoints to directly communicate with the payment service (`src/mock_payment/`). All communication routes through the Gateway (`src/gateway/`).
2. **Pre-Execution Persistence**: The Gateway must write the proposal, validation result, and initial attempt status to durable storage *before* dispatching any HTTP request to the payment service.
3. **Intent-Anchored Idempotency**: Idempotency keys must be derived from `intent_id` (`idem_{intent_id}`) rather than non-deterministic agent attempt UUIDs, ensuring duplicate suppression across agent crashes.
4. **Active Discovery Over Assumption**: Under network timeouts (`UNKNOWN`), the gateway must actively query the provider for existing effects before permitting any retry. A timeout alone must NEVER cause an immediate fresh refund.
5. **Observed Effect is Ground Truth**: Never report a transaction as "reversed" or "cancelled" based on internal agent state; require verified provider evidence.

## Testing & Verification
- Every new feature or fix must be verified with automated `pytest` suites.
- Do not mark tasks complete without running tests and verifying green status.
- Windows compatibility: Avoid unescaped Unicode characters in terminal prints (use `INR` instead of raw symbol `₹`).

## Git & Commits
- Use descriptive conventional commit messages: `feat:`, `fix:`, `test:`, `docs:`, `perf:`.
- Small, focused, verified commits.
