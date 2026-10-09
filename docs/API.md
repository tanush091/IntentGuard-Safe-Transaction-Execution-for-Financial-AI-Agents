# REST API Contract (API.md) — IntentGuard Recovery

This document is the coordination boundary between backend and frontend (and any integrating app or agent). The backend publishes the matching OpenAPI schema at `/openapi.json`, exported to [`docs/api/openapi.json`](api/openapi.json); **if they disagree, fix one of them in the same change.**

> **Status: implemented.** Every endpoint below exists in `backend/gateway_api/` and is covered by tests. CI enforces the contract:
> - `scripts/export_openapi.py --check` fails when the committed schema drifts from the code.
> - `frontend/scripts/check-contract.mjs` fails when the dashboard calls a route the schema does not have.
>
> The endpoint-by-endpoint reference generated from the code is [architecture/api.md](architecture/api.md). Items marked *planned* are not built.

- **Base URL (dev):** `http://localhost:8000/api`
- **Format:** JSON, UTF-8. Timestamps ISO-8601 UTC with milliseconds (`2026-10-09T10:15:30.123Z`).
- **Money:** decimal strings (`"1500.00"`) with an explicit `currency` (ISO-4217) on the wire. Storage uses integer minor units. An amount with more decimals than the currency has is rejected (`422 INVALID_AMOUNT`), never rounded. Never mix currencies in one request.
- **Versioning:** the current build serves unversioned `/api`. Breaking changes go to `/api/v2`; additive changes are allowed in place.

---

## 1. Conventions

### 1.1 Authentication
`Authorization: Bearer <access_token>` is required on every endpoint except:
- `POST /auth/login` and `POST /auth/refresh`;
- `POST /webhooks/{provider}`, which is signature-authenticated;
- `GET /health` and `GET /ready`.

Access tokens are HS256 JWTs. They live 15 minutes, carry `iss`, `aud`, `sub`, `exp`, `iat` and `jti`, and are checked against an algorithm allow-list.

### 1.2 Roles
| Role | Can |
|------|-----|
| `operator` | create authorizations, view intents, submit proposals, run the agent, reconcile, cancel, investigate exceptions, read reviews, audit and metrics |
| `agent` | submit proposals for, and read, only the intents (or customers) its service token is scoped to; nothing else |
| `reviewer` | everything an operator can, plus resolve review cases, verify the audit chain, trigger matching runs, resolve mismatches |
| `admin` | all, plus users, service tokens, policies, providers and orders |

The capability table is `CAPABILITIES` in `backend/gateway_api/security.py`; the dashboard mirrors it only to hide controls, and the server enforces it. Separation of duties: the operator who authorized an intent cannot resolve its review case (`403 SEPARATION_OF_DUTIES`). This is a policy, on by default.

### 1.3 Idempotency header
`POST` endpoints that create state accept `Idempotency-Key: <opaque string>` (client replay protection for the **API call itself**):
- Repeating a key with the same body replays the stored response.
- Repeating it with a different body is `422 IDEMPOTENCY_KEY_REUSE`.

This is separate from the provider idempotency key, which the gateway derives from the intent (`ig-<intent>-g<generation>`). It is never exposed and agents never choose it.

### 1.4 Error format
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "request validation failed",
    "details": {"errors": [{"loc": ["body", "order_id"], "msg": "Field required", "type": "missing"}]},
    "request_id": "req_7b90d1b6b2ce4c3e"
  }
}
```
Every response carries `X-Request-ID`, which matches `request_id`.

| HTTP | Meaning | Codes |
|------|---------|-------|
| 400 | Malformed request | `MALFORMED_REQUEST` (body is not JSON), `INVALID_CURSOR`, `INVALID_IDEMPOTENCY_KEY`, `INVALID_SIGNATURE`, `STALE_EVENT`, `MALFORMED_EVENT` |
| 401 | Missing/expired/invalid credentials | `UNAUTHENTICATED`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `INVALID_CREDENTIALS`, `INVALID_REFRESH_TOKEN`, `REFRESH_TOKEN_REUSED` |
| 403 | Authenticated but role/scope not permitted | `FORBIDDEN`, `CSRF_REQUIRED`, `SEPARATION_OF_DUTIES` |
| 404 | Unknown resource, or a simulator-only endpoint with `SIMULATOR_MODE` off | `NOT_FOUND` |
| 405 | Method not allowed on this path | `METHOD_NOT_ALLOWED` |
| 409 | State conflict | `STATE_CONFLICT`, `ILLEGAL_TRANSITION`, `ATTEMPT_IN_PROGRESS`, `NOT_CANCELLABLE`, `NO_VERIFIED_EFFECT`, `ALREADY_RESOLVED`, `ALREADY_APPLIED`, `ALREADY_EXISTS`, `NOT_AN_EXCEPTION`, `POLICY_REFUSED` |
| 422 | Semantically invalid | `VALIDATION_ERROR` (including unknown fields: request bodies are strict), `INVALID_AMOUNT`, `ORDER_NOT_FOUND`, `CUSTOMER_MISMATCH`, `CURRENCY_MISMATCH`, `OPERATOR_NOT_PERMITTED`, `OPERATOR_LIMIT_EXCEEDED`, `POLICY_LIMIT_EXCEEDED`, `WEAK_PASSWORD`, `IDEMPOTENCY_KEY_REUSE`, `NO_TICKET`, `EXTRACTION_FAILED`, `INVALID_AGENT_OUTPUT`, `INVALID_INVESTIGATOR_OUTPUT` |
| 429 | Rate limited or locked | `RATE_LIMITED`, `ACCOUNT_LOCKED` (with `Retry-After`) |
| 500 | Server fault | `INTERNAL_ERROR`; `SCHEMA_MISMATCH` (the database was created by an earlier schema version) |
| 502/503 | Provider error / unreachable, on the simulator-only `/dev/*` passthroughs and `GET /ready` | `PROVIDER_ERROR`, `PROVIDER_UNAVAILABLE` |

A provider problem during a proposal, cancel or reconciliation is **not** an HTTP error: the call returns 200/202 with the intent in `UNKNOWN` (or held), and the gateway never silently retries.

**Important:** a gateway *decision* of `REJECT` / `HOLD_FOR_REVIEW` / `DUPLICATE` is a **successful HTTP 200** response containing the decision, not an HTTP error.

### 1.5 Pagination
`?limit=50&cursor=<opaque>`; response `{ "items": [...], "next_cursor": "..." | null }`. Default limit 50, max 200. A cursor is only valid for the list that issued it (`400 INVALID_CURSOR` otherwise).

### 1.6 Enumerations
Authoritative lists are in `backend/intentguard/domain.py` and `backend/intentguard/checks.py`.

**Intent state:** `AUTHORIZED, IN_FLIGHT, EXECUTING, UNKNOWN, RECONCILING, DISCREPANCY, CANCEL_REQUESTED, ESCALATED, COMPLETED, CANCELLED, CLOSED`. Terminal: `CANCELLED`, `CLOSED`.
- `DISCREPANCY`: a live provider effect does not match the authorization, and the gateway is remediating it.
- `CLOSED`: a reviewer resolved the case without the authorized effect.
- The diagram is in [ARCHITECTURE.md §4](ARCHITECTURE.md#4-state-model).

**Proposal status** (per proposal, not an intent state): `PROPOSED, VALIDATED, REJECTED, BLOCKED`. The mapping from the decision is ALLOW→VALIDATED, REJECT→REJECTED, and HOLD_FOR_REVIEW or DUPLICATE→BLOCKED. An earlier draft listed these among intent states; they describe one proposal, and an intent can have several (ADR-029).

**Operation:** `REFUND`, `PAYMENT_AUTHORIZATION`. Cancelling is the `POST /intents/{id}/cancel` action on an existing intent, not a separate operation (ADR-030).

**Decision:** `ALLOW`, `REJECT`, `DUPLICATE`, `HOLD_FOR_REVIEW`. When several checks fail, the precedence is REJECT > HOLD_FOR_REVIEW > DUPLICATE.

**Decision reason codes:**
- Scope: `INTENT_NOT_ACTIVE`, `OPERATOR_NOT_PERMITTED`.
- Binding to the authorization: `OPERATION_MISMATCH`, `CUSTOMER_MISMATCH`, `ORDER_MISMATCH`, `CURRENCY_MISMATCH`, `AMOUNT_EXCEEDS_AUTHORIZATION`, `AMOUNT_BELOW_AUTHORIZATION`.
- Limits: `EXCEEDS_REMAINING_BALANCE`, `POLICY_LIMIT_EXCEEDED`, `KILL_SWITCH`.
- Progress: `ALREADY_COMPLETED`, `ATTEMPT_IN_PROGRESS`, `HELD_FOR_REVIEW`, `ATTEMPT_BUDGET_EXHAUSTED`.

The amount must match the authorization exactly; partial refunds are separate authorizations (ADR-031).

**Attempt status:** `SUBMITTING, SUCCEEDED, FAILED, UNKNOWN, RECONCILED`

**Effect status** (as observed at the provider): `PENDING, COMPLETED, CANCELLED, FAILED`. **Effect classification:** `INTENDED, DUPLICATE, MISMATCH`.

**Review case status:** `OPEN, RESOLVED`. **Review reason:** `UNRESOLVABLE_OUTCOME, IRREVERSIBLE_DISCREPANCY, CANCEL_REJECTED, CANCEL_UNVERIFIED, ATTEMPT_BUDGET_EXHAUSTED, INVESTIGATOR_ESCALATION`.

---

## 2. Auth

### `POST /auth/login`
Passwords are argon2id hashed, at least 12 characters. Five failures lock the account for 15 minutes (`429 ACCOUNT_LOCKED`), and logins are rate limited per client.
```json
// request
{ "email": "asha@intentguard.test", "password": "..." }
// 200
{ "access_token": "<jwt>", "token_type": "bearer", "expires_in": 900,
  "refresh_token": "<opaque>",
  "user": { "id": "op-asha", "email": "asha@intentguard.test", "name": "Asha (support lead)", "role": "operator" } }
```
The refresh token always arrives as an HttpOnly `SameSite=Strict` cookie `ig_refresh` on path `/api/auth`. A browser sends `X-IntentGuard-CSRF: 1` on `/auth/*` calls. It then gets **no** `refresh_token` in the body, so page script never sees it. API clients that omit the header receive it in the body.

### `POST /auth/refresh`
```json
{ "refresh_token": "<opaque>" }   // API clients; browsers send no body, the cookie and X-IntentGuard-CSRF: 1
// 200 → new access_token (+ rotated refresh token, same delivery rules as login)
```
Refresh tokens rotate on every use. Presenting a used token again revokes the whole token family (`401 REFRESH_TOKEN_REUSED`). A cookie refresh without the CSRF header is `403 CSRF_REQUIRED`.

### `POST /auth/logout`
Revokes the refresh token family and clears the cookie. `204`.

### `GET /auth/me` → `{ "id", "name", "role", "kind": "user" | "agent", "scopes": [...] }`.

---

## 3. Authorizations and intents

### `POST /authorizations`  *(operator, reviewer, admin)*
Creates the durable authorization and its intent. The operator must be permitted the operation and within their limit (`422 OPERATOR_NOT_PERMITTED`). If set, the policy limit applies too (`422 POLICY_LIMIT_EXCEEDED`).
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
  "created_at": "2026-10-09T10:15:30.339Z" }
```

### `GET /intents`
Query: `state`, `customer_id`, `order_id`, `operation`, `created_from`, `created_to`, `limit`, `cursor`.
```json
{ "items": [ { "intent_id": "INT-1001", "state": "COMPLETED", "operation": "REFUND",
               "customer_id": "C-17", "order_id": "ORD-204",
               "authorized_amount": "1500.00", "currency": "INR",
               "effect_amount": "1500.00", "operator_id": "op-asha",
               "created_at": "...", "updated_at": "..." } ],
  "next_cursor": null }
```
`effect_amount` counts only effects that count toward the authorization. An unintended effect (wrong amount, duplicate) appears under `effects` with `counts_toward_intent: false`.

### `GET /intents/{intent_id}`
```json
{
  "intent_id": "INT-1001", "state": "COMPLETED", "operation": "REFUND",
  "customer_id": "C-17", "order_id": "ORD-204",
  "authorized_amount": "1500.00", "currency": "INR", "effect_amount": "1500.00",
  "operator_id": "op-asha", "approval_status": "APPROVED",
  "generation": 0, "attempt_count": 1, "ticket_text": "...", "metadata": {},
  "cancel_requested": false, "verified": true, "open_review_case_id": null,
  "proposals": [ { "proposal_id": "PRP-2", "status": "VALIDATED", "decision": { "decision": "ALLOW", "...": "..." }, "...": "..." } ],
  "attempts": [ { "attempt_id": "ATT-001", "attempt_no": 1, "status": "SUCCEEDED", "amount": "1500.00",
                  "provider_transaction_id": "rf_6f02000001", "started_at": "...", "completed_at": "..." } ],
  "effects":  [ { "effect_id": "EFF-1", "provider_transaction_id": "rf_6f02000001", "attempt_id": "ATT-001",
                  "amount": "1500.00", "currency": "INR", "status": "COMPLETED", "classification": "INTENDED",
                  "counts_toward_intent": true, "remediated": false, "observed_at": "..." } ],
  "created_at": "...", "updated_at": "..."
}
```

### `GET /intents/{intent_id}/timeline`
Ordered, human-readable events (authorization, decisions, state changes, attempts, provider observations, recovery, reviews), built from the audit chain.
```json
{ "intent_id": "INT-1001",
  "events": [ { "ts": "...", "seq": 12, "kind": "AUTHORIZED", "actor": "op-asha", "summary": "authorized REFUND of 1500.00 INR on ORD-204", "ref": null },
              { "ts": "...", "seq": 14, "kind": "DECISION", "actor": "op-asha", "summary": "ALLOW", "ref": null },
              { "ts": "...", "seq": 16, "kind": "ATTEMPT_RESERVED", "actor": "gateway", "summary": "attempt ATT-001 reserved", "ref": "ATT-001" },
              { "ts": "...", "seq": 19, "kind": "STATE", "actor": "gateway", "summary": "IN_FLIGHT -> COMPLETED", "ref": null } ] }
```

### `GET /intents/{intent_id}/history`
Raw rows: proposals, decisions, attempts, effects, review cases, webhook events, investigations (never overwritten).

### `POST /intents/{intent_id}/cancel`  *(operator, reviewer, admin)*
Cancels an intent, or requests cancellation of its **pending** provider operation; the gateway verifies the provider state afterwards.
- `AUTHORIZED` or `RECONCILING` with nothing live: `CANCELLED` at once.
- A pending refund or a hold: `CANCEL_REQUESTED`, then the provider cancel. Once verified the intent is `CANCELLED`. If the provider refuses, it is `ESCALATED` with review reason `CANCEL_REJECTED`.
```json
// 202 — state is the state reached during the request:
// CANCELLED when the cancellation was verified at once, CANCEL_REQUESTED while verification is pending
{ "intent_id": "INT-1001", "state": "CANCELLED" }
// 409 NOT_CANCELLABLE      the provider effect is already completed (a completed refund)
// 409 ATTEMPT_IN_PROGRESS  an attempt's outcome is still being established (IN_FLIGHT / UNKNOWN)
```

---

## 4. Proposals (agent boundary)

### `POST /intents/{intent_id}/proposals`  *(agent with a scope for this intent, operator, reviewer, admin)*
```json
// request
{
  "request_id": "req_agent_77",        // agent-generated; recorded, NOT used for idempotency
  "agent_id": "support-bot",           // optional
  "operation": "REFUND",
  "customer_id": "C-17",
  "order_id": "ORD-204",
  "amount": "1500.00",
  "currency": "INR",
  "rationale": "customer returned the item"   // optional, recorded
}
// 200 — allowed and executed
{ "intent_id": "INT-1001", "proposal_id": "PRP-2", "decision": "ALLOW", "reason": null, "reasons": [], "findings": [],
  "state": "COMPLETED", "attempt_id": "ATT-001", "provider_transaction_id": "rf_6f02000001", "verified": true }
// 200 — blocked before any provider call
{ "intent_id": "INT-1001", "proposal_id": "PRP-1", "decision": "REJECT",
  "reason": "AMOUNT_EXCEEDS_AUTHORIZATION",
  "reasons": ["AMOUNT_EXCEEDS_AUTHORIZATION", "EXCEEDS_REMAINING_BALANCE"],
  "findings": [ { "check": "AMOUNT_EXCEEDS_AUTHORIZATION", "detail": "amount_minor: authorized 150000, proposed 1500000", "decision": "REJECT" }, "..." ],
  "state": "AUTHORIZED", "attempt_id": null, "provider_transaction_id": null, "verified": false }
// 200 — duplicate suppressed
{ "intent_id": "INT-1001", "proposal_id": "PRP-3", "decision": "DUPLICATE",
  "reason": "ALREADY_COMPLETED", "reasons": ["ALREADY_COMPLETED"], "findings": ["..."],
  "state": "COMPLETED", "attempt_id": null, "provider_transaction_id": "rf_6f02000001", "verified": true }
```
`reason` is the first entry of `reasons` (the highest-precedence finding). If the provider outcome is uncertain, the response has `state: "UNKNOWN"` or `"RECONCILING"` and `verified: false`. Callers must **not** treat that as failure and must not resubmit as a new intent.

### `POST /intents/{intent_id}/agent`  *(operator, reviewer, admin)*
Extracts a proposal from the intent's `ticket_text` and submits it through the same path as above. Extraction uses the offline rule extractor (default) or the configured LLM (`LLM_PROVIDER`). The response has the same shape as `POST /proposals`, plus:
```json
{ "extraction": { "source": "rules" | "llm", "model": "offline-rules" | "<provider>/<model>", "proposal": { "...": "..." } } }
```
- No ticket: `422 NO_TICKET`.
- The rule extractor cannot read the ticket: `422 EXTRACTION_FAILED`.
- Malformed LLM output: `422 INVALID_AGENT_OUTPUT`. It is never silently repaired, and nothing is submitted.

---

## 5. Reconciliation and recovery

### `POST /attempts/{attempt_id}/reconcile`  *(operator, reviewer, admin)*
Forces a reconciliation pass for an attempt.
```json
// 200
{
  "attempt_id": "ATT-001", "intent_id": "INT-1001",
  "outcome": "EFFECT_FOUND",
  "intent_state": "COMPLETED", "attempt_status": "SUCCEEDED",
  "evidence": [ { "kind": "provider_lookup", "ref": "rf_6f02000001", "status": "COMPLETED", "observed_at": "..." } ],
  "next_action": "NONE"
}
```
- `outcome` is one of: `EFFECT_FOUND`, `ABSENT_CONFIRMED`, `ABSENT_PENDING_WINDOW`, `PROVIDER_UNREACHABLE`, `DISCREPANCY`, `REJECTED_BY_PROVIDER`, `NOT_RECONCILABLE`.
- `next_action` is `NONE`, `CONTROLLED_RETRY` or `HOLD_FOR_REVIEW`.
- `ABSENT_PENDING_WINDOW` means "not found yet, but inside the absence window". It is not evidence of no effect.

### `GET /reconciliation/runs`
Recent runs, filterable by `kind` (`WORKER`, `MATCHING`): `{ run_id, kind, triggered_by, started_at, finished_at, examined, resolved, escalated, errors, mismatches_found }`.

### `POST /reconciliation/runs`  *(reviewer, admin)*
Triggers a matching run over orders, refunds, holds and effects. `202 { "run_id": "RUN-4", "status": "started" }`; with `?wait=true` the run finishes first and the response carries its counts. A matching run **reports** mismatches and changes nothing.

### `GET /reconciliation/mismatches`
Query: `kind` = `MISSING | DUPLICATE | AMOUNT | ORDER | CUSTOMER` (`ORDER` also covers an effect with a different operation), `status` = `OPEN | RESOLVED`. Items: `{ mismatch_id, kind, status, intent_id, provider_transaction_id, order_id, details, run_id, detected_at, resolved_at }`. Mismatches also come from webhooks (a provider transaction no intent accounts for).

### `POST /reconciliation/mismatches/{mismatch_id}/resolve`  *(reviewer, admin)*
`{ "note": "..." }` → `{ "mismatch_id": "MM-2", "status": "RESOLVED" }`. Audited.

---

## 6. Exceptions and AI investigation

### `GET /exceptions`
Unresolved uncertain cases: intents in `UNKNOWN`, `RECONCILING`, `DISCREPANCY`, `CANCEL_REQUESTED` or `ESCALATED`, newest first.

### `POST /exceptions/{intent_id}/investigate`  *(operator, reviewer, admin)*
Builds a redacted evidence bundle and asks the classifier to classify and summarize. The classifier is the offline rule classifier by default, or an LLM with a strict output schema. **Advisory only.** An intent that is not an exception is `409 NOT_AN_EXCEPTION`.
```json
// 200
{
  "investigation_id": "INV-3", "intent_id": "INT-1002", "intent_state": "UNKNOWN", "valid_output": true,
  "classification": "LOST_RESPONSE",
  "summary": "Provider shows refund rf_… for 2400.00 INR; the response was never received.",
  "evidence_refs": ["ATT-002", "EFF-2", "PROVIDER:rf_…"],
  "recommended_action": "MARK_COMPLETED",
  "policy_verdict": { "permitted": true, "rule": "effect_matches_authorization" },
  "model": "offline-rules", "tokens": { "in": 0, "out": 0 },
  "created_by": "op-asha", "created_at": "...", "applied": null
}
```
- `classification` ∈ {`LOST_RESPONSE`, `PROVIDER_DELAY`, `AMOUNT_MISMATCH`, `WRONG_ORDER`, `UNKNOWN`}.
- `recommended_action` ∈ {`MARK_COMPLETED`, `WAIT_AND_RECHECK`, `CONTROLLED_RETRY`, `CANCEL_PENDING`, `ESCALATE`}.

The policy gate (`backend/investigator/policy.py`) is deterministic. If `policy_verdict.permitted` is false, the gateway will not execute the recommendation; the intent stays in its current state and is handled by the normal recovery and review path. Invalid model output is stored with `valid_output: false` and answered with `422 INVALID_INVESTIGATOR_OUTPUT`.

### `GET /investigations/{investigation_id}`

### `POST /investigations/{investigation_id}/apply`  *(operator, reviewer, admin)*
Applies a permitted recommendation:
- The gate is re-checked against **fresh** evidence first. If it now refuses, the response is `409 POLICY_REFUSED`.
- Applying twice is `409 ALREADY_APPLIED`.
- `MARK_COMPLETED` never writes a state directly. It re-fetches the matching effects from the provider, so only a provider-verified effect completes an intent.

---

## 7. Review queue

### `GET /review-cases`
Query: `status`, `limit`, `cursor`.
```json
{ "items": [ { "case_id": "RC-1", "intent_id": "INT-1004", "reason": "CANCEL_REJECTED",
               "discrepancy_amount": "9000.00", "currency": "INR", "status": "OPEN",
               "resolution": null, "resolved_by": null, "note": null, "details": { },
               "created_at": "...", "resolved_at": null } ],
  "next_cursor": null }
```

### `GET /review-cases/{case_id}`
Includes the intent, linked effects, timeline, and any investigation.

### `POST /review-cases/{case_id}/resolve`  *(reviewer, admin)*
```json
{ "resolution": "ACCEPTED_AS_IS | REFUND_RECOVERED_OUT_OF_BAND | WRITTEN_OFF | CONFIRMED_NO_EFFECT | OTHER", "note": "..." }
// 200 → { "case_id": "RC-1", "status": "RESOLVED", "resolution": "WRITTEN_OFF", "intent_state": "CLOSED" }
```
- `ACCEPTED_AS_IS` requires a provider-verified intended effect (`409 NO_VERIFIED_EFFECT` otherwise). The effect stands, and the intent is re-derived, normally to `COMPLETED`.
- `REFUND_RECOVERED_OUT_OF_BAND` marks the unintended live effects as remediated (all live effects, if the intent was being cancelled). It then moves to the next idempotency-key generation, so a retry cannot replay the remediated transaction.
- `CONFIRMED_NO_EFFECT` records the unknown attempts as having had no effect.
- `WRITTEN_OFF` closes the intent (`CLOSED`) and resolves any other open case for it.
- `OTHER` records the resolution.
- Except for `WRITTEN_OFF`, the gateway then re-derives the intent state from the evidence. A resolution never asserts an outcome the provider does not show.
- A resolved case cannot be resolved again (`409 ALREADY_RESOLVED`).

The resolution is appended to the audit log; prior case history is preserved.

---

## 8. Webhooks (provider → gateway)

### `POST /webhooks/{provider}`
Authenticated by **signature**, not JWT. The simulator sends `Paysim-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<raw body>">` with the shared `WEBHOOK_SECRET`. The gateway:
1. verifies the signature (`400 INVALID_SIGNATURE`) and the timestamp tolerance (`400 STALE_EVENT`);
2. dedupes by provider event id (a repeat is `200 {"status": "duplicate"}`);
3. stores the event;
4. **re-fetches** the transaction from the provider instead of trusting the payload, and feeds reconciliation.

Out-of-order and repeated delivery are expected and safe (ADR-021). A transaction that no intent accounts for becomes a `MISSING` mismatch.

---

## 9. Audit

### `GET /audit`
Query: `intent_id`, `actor`, `kind`, `from`, `to`, `limit`, `cursor`. Items: `{ seq, ts, chain_id, intent_id, actor, kind, payload, prev_hash, hash }`. Secrets in payloads are redacted.

### `GET /audit/verify`  *(reviewer, admin)*
Verifies every hash chain (one per intent, plus a system chain).
```json
{ "valid": true, "entries_checked": 1842, "chains": 37, "first_break": null }
```
The audit table is append-only in the database itself, through triggers on SQLite and PostgreSQL. Verification also catches a rewrite made after someone drops a trigger.

---

## 10. Metrics and experiments

### `GET /metrics/summary`
`?window=1h|24h|7d|30d|all`.
```json
{ "window": "24h",
  "intents": { "total": 120, "completed": 98, "blocked": 12, "unknown": 2, "escalated": 8, "by_state": { "COMPLETED": 98, "...": 0 } },
  "decisions": { "ALLOW": 100, "REJECT": 10, "DUPLICATE": 5, "HOLD_FOR_REVIEW": 2 },
  "duplicates_suppressed": 5,
  "auto_resolved_rate": 0.91,
  "human_intervention_rate": 0.07,
  "median_time_to_verified_s": 4.2,
  "live_unintended_effects": { "count": 1, "amount_minor": 900000 },
  "open_reviews": { "count": 2, "discrepancy_minor": 1350000 },
  "definitions": { "blocked": "...", "auto_resolved_rate": "...", "human_intervention_rate": "...", "median_time_to_verified_s": "..." } }
```
The numbers above are an illustration of the shape, not measurements. `definitions` states how each derived metric is computed.

### `GET /experiments/latest`
Serves the latest benchmark summary (`experiments/results/latest/summary.json`) to the dashboard.

---

## 11. Admin

| Method & path | Purpose |
|---------------|---------|
| `GET /admin/users`, `POST /admin/users`, `PATCH /admin/users/{id}` | manage users, roles, permitted operations, limits, activation, passwords |
| `GET /admin/service-tokens`, `POST /admin/service-tokens`, `DELETE /admin/service-tokens/{jti}` | issue, list and revoke agent tokens (intent- or customer-scoped, at most 300 s) |
| `GET /admin/policies`, `PUT /admin/policies` | kill switch, maximum amount, separation of duties, attempt budget, absence window, unknown-review delay. Audited, and kept across restarts |
| `GET /admin/providers`, `PUT /admin/providers/{name}` | provider connection config (base URL, timeout; the webhook secret is write-only) |
| `GET /orders` *(any staff role)*, `POST /admin/orders` | read orders; add an order (also registered with the simulator) |

---

## 12. Health and dev-only endpoints

| Path | Notes |
|------|-------|
| `GET /health` | liveness; no auth (also served at the root `/health`) |
| `GET /ready` | database and provider reachability; `503` when not ready |
| `GET`, `POST`, `DELETE /dev/faults` *(simulator only)* | inject provider faults: `TIMEOUT_BEFORE_EXECUTION`, `TIMEOUT_AFTER_EXECUTION`, `OUTAGE`, `LOOKUP_OUTAGE`, `DELAYED_STATUS`, `DELAYED_VISIBILITY`, `FAILED_CANCELLATION`, `CORRUPT_AMOUNT`, `WEBHOOK_DUPLICATE`, `WEBHOOK_DELAY` |
| `GET /dev/ledger` *(simulator only)* | the simulator's ground-truth ledger |
| `POST /dev/orders` *(simulator only)* | a fresh demo order (`ORD-9xxxxxxx`) in both the gateway and the simulator, so demos can be repeated |
| `POST /dev/worker/tick` *(simulator only)* | run one background-worker pass now |

Simulator-only endpoints answer `404` unless `SIMULATOR_MODE=true`.

### Mock provider service (internal, not for agents)
`POST /v1/refunds`, `GET /v1/refunds/{id}`, `GET /v1/refunds?order_id=...`, `POST /v1/refunds/{id}/cancel`, `POST /v1/authorizations`, `GET /v1/authorizations/{id}`, `GET /v1/authorizations?order_id=...`, `POST /v1/authorizations/{id}/void`, `POST /v1/orders`, `GET`/`POST`/`DELETE /v1/faults` (only with `SIMULATOR_MODE=true`), `GET /v1/ledger`, `GET /health`.
Reachable only from the gateway network; the agent must never have a route to it. *As built:* the simulator has no authentication. `docker-compose.yml` publishes it, and PostgreSQL, on 127.0.0.1 only; `/v1/ledger` is a research endpoint and is not gated by `SIMULATOR_MODE`. *Planned:* a real provider sandbox adapter (e.g. Stripe test mode) behind the same port.

---

## 13. Contract rules

1. Agents can call **only** `POST /intents/{id}/proposals` (and read their own intent). Enforce by scope, not by convention.
2. Decisions (`REJECT`, `DUPLICATE`, …) are HTTP 200; transport and auth problems use HTTP errors.
3. A non-terminal `state` with `verified: false` must be shown to users as "being verified", never as "failed".
4. Never expose provider secrets, webhook secrets, refresh tokens to browser script, or the derived provider idempotency key to clients.
5. Additive fields are non-breaking; clients must ignore unknown fields. Request bodies are strict: unknown request fields are rejected.

**Known gaps in the generated schema** (`docs/api/openapi.json`): it declares no security scheme. It does not list the `Idempotency-Key`, `X-IntentGuard-CSRF`, `X-Request-ID` or `Paysim-Signature` headers, or `?wait`. Response bodies are untyped. Its default 422 shape (`{detail: [...]}`) is never returned; the envelope in §1.4 is. This document is authoritative for those details.
