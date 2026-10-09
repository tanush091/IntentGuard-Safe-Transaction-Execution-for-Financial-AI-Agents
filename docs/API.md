# REST API Contract (API.md) — IntentGuard Recovery

This document is the coordination boundary between backend and frontend (and any integrating app or agent). The backend publishes the matching OpenAPI schema at `/openapi.json`; **if they disagree, fix one of them in the same change.**

- **Base URL (dev):** `http://localhost:8000/api`
- **Format:** JSON, UTF-8. Timestamps ISO-8601 UTC (`2026-10-09T10:15:30Z`).
- **Money:** integer minor units are preferred on the wire in future versions; the current build uses decimal `amount` with explicit `currency` (ISO-4217). Never mix currencies in one request.
- **Versioning:** the current build serves unversioned `/api`. Breaking changes go to `/api/v2`; additive changes are allowed in place.

---

## 1. Conventions

### 1.1 Authentication
`Authorization: Bearer <access_token>` on every endpoint except `POST /auth/login`, `POST /auth/refresh`, `POST /webhooks/{provider}` (signature-authenticated) and `GET /health`.

### 1.2 Roles
| Role | Can |
|------|-----|
| `operator` | create authorizations, view intents, trigger reconcile/cancel on own scope |
| `agent` | submit proposals only (service principal, scoped to specific intents) |
| `reviewer` | everything an operator can, plus work the review queue, verify audit |
| `admin` | all, plus user and policy management |

### 1.3 Idempotency header
`POST` endpoints that create state accept `Idempotency-Key: <opaque string>` (client replay protection for the **API call itself**). This is separate from the provider idempotency key, which the gateway derives from the intent and never exposes for agents to choose.

### 1.4 Error format
```json
{
  "error": {
    "code": "AMOUNT_EXCEEDS_AUTHORIZATION",
    "message": "Proposed amount 15000.00 exceeds authorized 1500.00",
    "details": {"authorized": "1500.00", "proposed": "15000.00"},
    "request_id": "req_8f2c..."
  }
}
```
| HTTP | Meaning |
|------|---------|
| 400 | Malformed request / validation failure (`VALIDATION_ERROR`) |
| 401 | Missing/expired/invalid token |
| 403 | Authenticated but role/scope not permitted |
| 404 | Unknown resource |
| 409 | State conflict (e.g. illegal transition, attempt in progress) |
| 422 | Semantically invalid (Pydantic) |
| 429 | Rate limited |
| 502/503 | Provider unreachable (gateway keeps state `UNKNOWN`/held; never silently retries) |

**Important:** a gateway *decision* of `REJECTED` / `BLOCKED` / `DUPLICATE` is a **successful HTTP 200** response containing the decision, not an HTTP error.

### 1.5 Pagination
`?limit=50&cursor=<opaque>`; response `{ "items": [...], "next_cursor": "..." | null }`. Default limit 50, max 200.

### 1.6 Enumerations

**Intent state:** `AUTHORIZED, PROPOSED, VALIDATED, IN_FLIGHT, EXECUTING, UNKNOWN, RECONCILING, COMPLETED, CANCEL_REQUESTED, CANCELLED, REJECTED, BLOCKED, ESCALATED`
(authoritative list: `backend/intentguard/domain.py`)

**Operation:** `REFUND`, `PAYMENT_AUTHORIZATION`, `AUTHORIZATION_CANCEL`

**Decision:** `ALLOW`, `REJECT`, `DUPLICATE`, `HOLD_FOR_REVIEW`

**Decision reason codes (non-exhaustive):** `AMOUNT_EXCEEDS_AUTHORIZATION`, `ORDER_MISMATCH`, `CUSTOMER_MISMATCH`, `CURRENCY_MISMATCH`, `OPERATION_MISMATCH`, `EXCEEDS_REMAINING_BALANCE`, `OPERATOR_NOT_PERMITTED`, `ALREADY_COMPLETED`, `ATTEMPT_IN_PROGRESS`, `HELD_FOR_REVIEW`, `ATTEMPT_BUDGET_EXHAUSTED`

**Attempt status:** `SUBMITTING, SUCCEEDED, FAILED, UNKNOWN, RECONCILED`

**Review case status:** `OPEN, RESOLVED`

---

## 2. Auth

### `POST /auth/login`
```json
// request
{ "email": "ops@example.com", "password": "..." }
// 200
{ "access_token": "<jwt>", "refresh_token": "<opaque>", "expires_in": 900,
  "user": { "id": "usr_1", "email": "ops@example.com", "role": "operator" } }
```

### `POST /auth/refresh`
```json
{ "refresh_token": "<opaque>" }   // 200 → new access_token (+ rotated refresh_token)
```

### `POST /auth/logout`
Revokes the refresh token. `204`.

### `GET /auth/me` → current user.

---

## 3. Authorizations and intents

### `POST /authorizations`  *(operator, reviewer, admin)*
Creates the durable authorization and its intent.
```json
// request
{
  "customer_id": "C-17",
  "order_id": "ORD-204",
  "operation": "REFUND",
  "authorized_amount": "1500.00",
  "currency": "INR",
  "ticket_text": "Please refund my returned item for order ORD-204",   // optional
  "metadata": { }
}
// 201
{ "intent_id": "INT-1001", "state": "AUTHORIZED", "approval_status": "APPROVED",
  "created_at": "2026-10-09T10:15:30Z" }
```

### `GET /intents`
Query: `state`, `customer_id`, `order_id`, `operation`, `created_from`, `created_to`, `limit`, `cursor`.
```json
{ "items": [ { "intent_id": "INT-1001", "state": "COMPLETED", "operation": "REFUND",
               "customer_id": "C-17", "order_id": "ORD-204",
               "authorized_amount": "1500.00", "currency": "INR",
               "effect_amount": "1500.00", "updated_at": "..." } ],
  "next_cursor": null }
```

### `GET /intents/{intent_id}`
```json
{
  "intent_id": "INT-1001",
  "state": "COMPLETED",
  "operation": "REFUND",
  "customer_id": "C-17",
  "order_id": "ORD-204",
  "authorized_amount": "1500.00",
  "currency": "INR",
  "generation": 0,
  "attempts": [ { "attempt_id": "ATT-001", "status": "UNKNOWN",   "started_at": "...", "completed_at": null },
                { "attempt_id": "ATT-002", "status": "RECONCILED","started_at": "...", "completed_at": "..." } ],
  "effects":  [ { "effect_id": "EFF-1", "provider_transaction_id": "re_123", "amount": "1500.00",
                  "currency": "INR", "status": "completed", "observed_at": "..." } ],
  "open_review_case_id": null
}
```

### `GET /intents/{intent_id}/timeline`
Ordered, human-readable events (authorization, proposals, decisions, attempts, provider observations, recovery actions).
```json
{ "intent_id": "INT-1001",
  "events": [ { "ts": "...", "kind": "DECISION", "summary": "ALLOW", "ref": "DEC-9" },
              { "ts": "...", "kind": "ATTEMPT_UNKNOWN", "summary": "timeout after execution", "ref": "ATT-001" },
              { "ts": "...", "kind": "RECONCILED", "summary": "effect found at provider", "ref": "EFF-1" } ] }
```

### `GET /intents/{intent_id}/history`
Raw rows: proposals, decisions, attempts, effects (never overwritten).

### `POST /intents/{intent_id}/cancel`  *(operator, reviewer, admin)*
Requests cancellation of a **pending** provider operation. Gateway verifies the provider state afterwards.
```json
// 202
{ "intent_id": "INT-1001", "state": "CANCEL_REQUESTED" }
// 409  if provider effect already completed → code "NOT_CANCELLABLE"
```

---

## 4. Proposals (agent boundary)

### `POST /intents/{intent_id}/proposals`  *(agent, operator)*
```json
// request
{
  "request_id": "req_agent_77",        // agent-generated; NOT used for idempotency
  "operation": "REFUND",
  "customer_id": "C-17",
  "order_id": "ORD-204",
  "amount": "1500.00",
  "currency": "INR"
}
// 200 — allowed and executed
{
  "intent_id": "INT-1001",
  "proposal_id": "PRP-5",
  "decision": "ALLOW",
  "reason": null,
  "state": "COMPLETED",
  "attempt_id": "ATT-001",
  "verified": true
}
// 200 — blocked
{ "intent_id": "INT-1001", "proposal_id": "PRP-6", "decision": "REJECT",
  "reason": "AMOUNT_EXCEEDS_AUTHORIZATION", "state": "AUTHORIZED", "verified": false }
// 200 — duplicate suppressed
{ "intent_id": "INT-1001", "proposal_id": "PRP-7", "decision": "DUPLICATE",
  "reason": "ALREADY_COMPLETED", "state": "COMPLETED", "verified": true }
```
If the provider outcome is uncertain: `state: "UNKNOWN"` or `"RECONCILING"`, `verified: false`. Callers must **not** treat that as failure and must not resubmit as a new intent.

### `POST /intents/{intent_id}/agent`  *(operator, reviewer, admin)*
Extracts a proposal from the intent's `ticket_text` using the offline extractor or the configured LLM, then submits it through the same path as above. Response is the same shape as `POST /proposals` plus:
```json
{ "extraction": { "source": "rules|llm", "proposal": { "...": "..." } } }
```
Malformed LLM output is rejected (`422 INVALID_AGENT_OUTPUT`), never silently repaired.

---

## 5. Reconciliation and recovery

### `POST /attempts/{attempt_id}/reconcile`  *(operator, reviewer, admin)*
Forces a reconciliation pass for an `UNKNOWN` attempt.
```json
// 200
{
  "attempt_id": "ATT-001",
  "outcome": "EFFECT_FOUND",            // EFFECT_FOUND | ABSENT_CONFIRMED | ABSENT_PENDING_WINDOW | PROVIDER_UNREACHABLE | DISCREPANCY
  "intent_state": "COMPLETED",
  "evidence": [ { "kind": "provider_lookup", "ref": "re_123", "observed_at": "..." } ],
  "next_action": "NONE"                 // NONE | CONTROLLED_RETRY | HOLD_FOR_REVIEW
}
```
`ABSENT_PENDING_WINDOW` means "not found yet, but inside the absence window" — not evidence of no effect.

### `GET /reconciliation/runs`
Recent worker runs: `{ run_id, started_at, finished_at, examined, resolved, escalated, errors }`.

### `POST /reconciliation/runs`  *(reviewer, admin)*
Triggers a run over matching orders, payments, refunds and events. `202 { "run_id": "..." }`.

### `GET /reconciliation/mismatches`
Query: `kind` = `MISSING | DUPLICATE | AMOUNT | ORDER | CUSTOMER`, `status`. Items reference intents/effects/events.

---

## 6. Exceptions and AI investigation

### `GET /exceptions`
Unresolved uncertain cases (UNKNOWN, held, discrepancy), newest first.

### `POST /exceptions/{intent_id}/investigate`  *(operator, reviewer, admin)*
Builds an evidence bundle and asks the LLM to classify and summarize. **Advisory only.**
```json
// 200
{
  "investigation_id": "INV-3",
  "classification": "LOST_RESPONSE | PROVIDER_DELAY | AMOUNT_MISMATCH | WRONG_ORDER | UNKNOWN",
  "summary": "Provider shows refund re_123 for 1500 INR created 40s after the attempt; response never received.",
  "evidence_refs": ["ATT-001", "EFF-1", "WH-88"],
  "recommended_action": "MARK_COMPLETED",
  "policy_verdict": { "permitted": true, "rule": "effect_matches_authorization" },
  "model": "provider/model-name",
  "created_at": "..."
}
```
`recommended_action` ∈ {`MARK_COMPLETED`, `WAIT_AND_RECHECK`, `CONTROLLED_RETRY`, `CANCEL_PENDING`, `ESCALATE`}. If `policy_verdict.permitted` is false the gateway will not execute it; the case stays escalated.

### `GET /investigations/{investigation_id}`

---

## 7. Review queue

### `GET /review-cases`
Query: `status`, `limit`, `cursor`.
```json
{ "items": [ { "case_id": "RC-4", "intent_id": "INT-1009", "reason": "COMPLETED_AMOUNT_MISMATCH",
               "discrepancy_amount": "13500.00", "status": "OPEN", "created_at": "...", "resolved_at": null } ],
  "next_cursor": null }
```

### `GET /review-cases/{case_id}`
Includes linked effects, timeline, and any investigation.

### `POST /review-cases/{case_id}/resolve`  *(reviewer, admin)*
```json
{ "resolution": "ACCEPTED_AS_IS | REFUND_RECOVERED_OUT_OF_BAND | WRITTEN_OFF | OTHER", "note": "..." }
// 200 → status RESOLVED
```
Resolution is itself appended to the audit log; prior case history is preserved.

---

## 8. Webhooks (provider → gateway)

### `POST /webhooks/{provider}`
Authenticated by **signature**, not JWT. Gateway verifies the signature against the configured secret, dedupes by provider event ID, stores the event, then feeds reconciliation. Returns `200` quickly for valid and duplicate events; `400` for bad signatures. Out-of-order and repeated delivery are expected and safe.

---

## 9. Audit

### `GET /audit`
Query: `intent_id`, `actor`, `kind`, `from`, `to`, `limit`, `cursor`.

### `GET /audit/verify`  *(reviewer, admin)*
Verifies the hash chain.
```json
{ "valid": true, "entries_checked": 1842, "first_break": null }
```

---

## 10. Metrics and experiments

### `GET /metrics/summary`
```json
{ "window": "24h",
  "intents": { "total": 120, "completed": 98, "blocked": 12, "unknown": 2, "escalated": 8 },
  "duplicates_suppressed": 5,
  "auto_resolved_rate": 0.91,
  "human_intervention_rate": 0.07,
  "median_time_to_verified_s": 4.2 }
```

### `GET /experiments/latest`
Serves the latest benchmark summary (`experiments/results/latest/summary.json`) to the dashboard.

---

## 11. Admin

| Method & path | Purpose |
|---------------|---------|
| `GET /admin/users`, `POST /admin/users`, `PATCH /admin/users/{id}` | manage users and roles |
| `POST /admin/service-tokens` | issue scoped agent tokens (intent- or customer-scoped, short-lived) |
| `GET /admin/policies`, `PUT /admin/policies` | refund limits, attempt budget, absence window |
| `GET /admin/providers`, `PUT /admin/providers/{name}` | provider connection config (secrets write-only) |

---

## 12. Health and dev-only endpoints

| Path | Notes |
|------|-------|
| `GET /health` | liveness; no auth |
| `GET /ready` | DB and provider reachability |
| `POST /dev/faults` *(simulator only)* | inject provider faults (`TIMEOUT_BEFORE_EXECUTION`, `TIMEOUT_AFTER_EXECUTION`, `OUTAGE`, `DELAYED_STATUS`, `FAILED_CANCELLATION`, `CORRUPT_AMOUNT`); disabled outside simulator mode |

### Mock provider service (internal, not for agents)
`POST /v1/refunds`, `GET /v1/refunds/{id}`, `GET /v1/refunds?order_id=...`, `POST /v1/refunds/{id}/cancel`, `POST /v1/authorizations`, `POST /v1/faults`, `GET /v1/ledger`.
Reachable only from the gateway network; the agent must never have a route to it.

---

## 13. Contract rules

1. Agents can call **only** `POST /intents/{id}/proposals` (and read their own intent). Enforce by scope, not by convention.
2. Decisions (`REJECT`, `DUPLICATE`, …) are HTTP 200; transport and auth problems use HTTP errors.
3. A non-terminal `state` with `verified: false` must be shown to users as "being verified", never as "failed".
4. Never expose provider secrets, webhook secrets or the derived provider idempotency key to clients.
5. Additive fields are non-breaking; clients must ignore unknown fields.
