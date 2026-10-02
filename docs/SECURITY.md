# Security Policy & Requirements (SECURITY.md) — IntentGuard

## Security Boundary & Threat Model
Autonomous AI agents are treated as **untrusted callers**. An AI agent may suffer prompt injections, hallucinatory errors, or process restarts that generate invalid API commands. 

### Key Security Invariants
1. **Network & Credential Isolation**:
   - The AI Agent must never hold payment gateway API credentials, secret tokens, or direct network routes to the payment processor.
   - All financial operations must pass through the IntentGuard Safety Gateway.
2. **Pre-Execution Authorization Binding**:
   - Every financial operation requires a durable authorization record stored in the database.
   - The Gateway checks authorization status (`approval_status == APPROVED`) before permitting execution.
3. **Intent-Anchored Idempotency**:
   - To defeat replay attacks and restart duplicates, idempotency keys are anchored to the immutable `intent_id` (`idem_{intent_id}`) rather than user/agent-generated tokens.
4. **Input & Parameter Validation**:
   - Every request is validated against strict Pydantic models.
   - Amount limits are strictly enforced: `0 < proposed_amount <= authorized_amount`.
5. **Secrets Management**:
   - No sensitive API keys or database credentials in version control.
   - Secrets are loaded via environment variables using `pydantic-settings` (`.env.example`).
6. **Immutable Audit Trail**:
   - The `audit_logs` table preserves all state changes, decisions, and reconciliation checks chronologically. Historical log entries are never rewritten or deleted.
