# HTTP APIs

Taken from the FastAPI route definitions in
[`backend/gateway_api/main.py`](../../backend/gateway_api/main.py) (request models in
[`schemas.py`](../../backend/gateway_api/schemas.py)) and
[`backend/provider_api/main.py`](../../backend/provider_api/main.py). Interactive docs:
http://127.0.0.1:8000/docs (gateway) and http://127.0.0.1:8001/docs (provider). Neither API has
authentication.

## Gateway API (port 8000)

Amounts cross this API as **decimal strings in major units** (`"1500.00"`), and responses add
`amount_display` (`"₹1,500.00"`). Internally everything is stored in minor units.

### System

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | `{status, service, provider}` |
| GET | `/info` | Active `ProtocolConfig`, provider mode, agent extractor (`offline-rules` or the LLM provider) |
| POST | `/api/worker/tick` | Run one worker pass now; returns `{processed}` |

### Operators and orders (admin)

| Method | Path | Body | Purpose |
|---|---|---|---|
| GET | `/api/operators` | | List operators |
| POST | `/api/operators` → 201 | `OperatorIn {id, name, permitted_operations[], limit, currency="INR", active=true}` | Create or update an operator |
| PATCH | `/api/operators/{operator_id}` | `{active}` | Activate or deactivate (a deactivated operator's intents are rejected at proposal time) |
| GET | `/api/orders` | | List the merchant's orders |
| POST | `/api/orders` → 201 | `OrderIn {id, customer_id, currency="INR", amount}` | Create or update an order; also registers it with the provider |

### Intents

| Method | Path | Body / query | Purpose |
|---|---|---|---|
| POST | `/api/intents` → 201 | `IntentIn {operator_id, customer_id, order_id, operation="REFUND", amount, currency="INR", ticket?}` | Operator authorization. 422 if the operator, order, customer, currency or amount is not allowed |
| GET | `/api/intents` | `?state=&limit=50` (max 500) | Newest first |
| GET | `/api/intents/{intent_id}` | | Timeline: `{intent, proposals, attempts, effects, reviews, audit}` |
| POST | `/api/intents/{intent_id}/reconcile` | | Reconcile and drive now; returns `{intent_state}` |
| POST | `/api/intents/{intent_id}/revoke` | `{actor}` | Only from `AUTHORIZED` or `RETRYABLE` (else 409) |

### Agent

| Method | Path | Body | Purpose |
|---|---|---|---|
| POST | `/api/intents/{intent_id}/proposals` | `ProposalIn {operation, customer_id, order_id, amount, currency="INR", request_id?, agent_id="external-agent", rationale=""}` | Submit a structured proposal |
| POST | `/api/intents/{intent_id}/agent` | `AgentRunIn {ticket?, agent_id="support-agent"}` | Extract a proposal from the ticket (body, else the intent's stored ticket) and submit it |

Both return `SubmitOut`:

```json
{"decision": "APPROVED", "intent_id": "int_…", "intent_state": "PENDING_SETTLEMENT",
 "findings": [], "proposal_id": 1, "attempt_id": "att_…", "provider_ref": "rf_…"}
```

`findings` lists every check that fired as `{check, detail, decision}`. For `DUPLICATE`,
`provider_ref` is the existing effect. The agent endpoint wraps it as
`{extractor, extracted, extraction_error, result}`; if extraction fails, `result` is `null` and
nothing is submitted. Decision meanings: [../product/overview.md](../product/overview.md#what-the-agent-gets-back).

The extractor is the offline rule extractor unless `LLM_PROVIDER` (`openai`, `ollama`, `gemini`)
is set in the gateway's *process environment*.

### Reviews

| Method | Path | Body / query | Purpose |
|---|---|---|---|
| GET | `/api/reviews` | `?status=OPEN` (default; pass empty for all) | Review cases, newest first |
| POST | `/api/reviews/{case_id}/resolve` | `ResolveIn {reviewer_id, resolution, notes=""}` | `resolution` ∈ `CONFIRMED_COMPLETED`, `CONFIRMED_NO_EFFECT`, `MANUALLY_REMEDIATED`, `CLOSED_UNFULFILLED`. 409 if already resolved, or if `CONFIRMED_COMPLETED` is claimed without a verified intended effect |

### Audit, metrics, experiments

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/audit` | `?intent_id=&limit=100` (max 1000); newest first |
| GET | `/api/audit/verify` | Recompute all hash chains: `{ok, checked, chains}` or `{ok: false, broken_at_seq, chain_id}` |
| GET | `/api/metrics` | Live counts from the ledger: intents by state, proposals by decision, attempts by status, effects by class, live unintended effects (count and amount), open reviews (count and discrepancy) |
| GET | `/api/experiments/latest` | `RESULTS_DIR/latest/summary.json`; 404 if no benchmark has been run |

### Errors

| Status | When |
|---|---|
| 404 | Unknown intent, operator or review case |
| 409 | `ConflictError` or `IllegalTransition` (e.g. revoke in the wrong state, resolve a resolved case) |
| 422 | Authorization refused at intent creation, request validation errors, agent endpoint without a ticket |

## Provider API (port 8001)

A mock payment provider backed by `paysim`. Amounts are **integers in minor units**. It never
connects to real accounts.

| Method | Path | Body / headers | Purpose |
|---|---|---|---|
| GET | `/health` | | Status and call counters (`create_calls`, `executions`, `lookups`, `cancels`) |
| POST | `/v1/orders` → 201 | `{order_id, customer_id, currency="INR", amount_minor}` | Register an order (the gateway does this for seeded and new orders) |
| POST | `/v1/refunds` → 201 | `{order_id, customer_id, amount_minor, currency="INR", metadata={}}`, header `Idempotency-Key` | Create a refund (`PENDING`, settles to `COMPLETED` after `PAYSIM_SETTLE_DELAY_S`) |
| GET | `/v1/refunds?order_id=` | | Search by order. **Eventually consistent**: a transaction appears only after its `visible_at` |
| GET | `/v1/refunds/{tx_id}` | | Lookup by id. Strongly consistent |
| POST | `/v1/refunds/{tx_id}/cancel` | | Cancel. Only a `PENDING` refund can be cancelled; cancelling a cancelled one is a no-op |
| POST | `/v1/authorizations` → 201 | as refunds | Create an authorization hold |
| GET | `/v1/authorizations?order_id=` | | Search by order (eventually consistent) |
| GET | `/v1/authorizations/{tx_id}` | | Lookup by id |
| POST | `/v1/authorizations/{tx_id}/void` | | Void a hold while `PENDING` or `COMPLETED` (authorized) |
| GET | `/v1/faults` | | Queued faults |
| POST | `/v1/faults` → 201 | `{kind, order_id?, times=1, params={}}` | Queue a fault (see below) |
| DELETE | `/v1/faults` | | Clear all faults |
| GET | `/v1/ledger?order_id=` | | Ground truth: every transaction regardless of search visibility. For evaluation and demos |

Transactions are returned as
`{id, kind, order_id, customer_id, amount_minor, currency, status, idempotency_key, metadata, created_at, settles_at, visible_at, cancelled_at}`.

**Idempotency.** A repeated `Idempotency-Key` with the same parameters returns the original
transaction; with different parameters it is rejected (`idempotency_key_reuse`). Keys expire after
24 h.

**Errors** use `{"detail": {"code", "message"}}`:

| Status | Codes | Gateway treats it as |
|---|---|---|
| 504 | `timeout` (timeout before execution, or response lost after execution) | Unknown outcome |
| 503 | `unavailable` (outage, lookup outage) | Unknown outcome on create; failed lookup on read |
| 404 | `not_found`, `order_not_found` | Definitive rejection |
| 409 | `not_cancellable`, `cancel_rejected` | Definitive rejection (cancellation refused) |
| 422 | `customer_mismatch`, `currency_mismatch`, `invalid_amount`, `insufficient_balance`, `idempotency_key_reuse` | Definitive rejection |

### Faults

`kind` values (`paysim.FaultKind`). A fault applies to `order_id` (or any order if omitted), fires
`times` times (`-1` = forever), and is consumed when it fires.

| Kind | Applies to | Effect | `params` |
|---|---|---|---|
| `OUTAGE` | create | 503, nothing executed | |
| `TIMEOUT_BEFORE_EXECUTION` | create | 504, nothing executed | |
| `LOST_RESPONSE` | create | Executes (or replays), then 504 | |
| `SLOW_SETTLEMENT` | create (fresh execution) | Settles after a longer delay | `settle_delay_s` (default 60) |
| `DELAYED_VISIBILITY` | create (fresh execution) | Hidden from search for a while | `lag_s` (default 20) |
| `AMOUNT_MISMATCH` | create (fresh execution) | Settled amount = requested × factor | `factor` (default 10) |
| `CANCEL_REJECTED` | cancel / void | 409 `cancel_rejected`, even when cancellation would be allowed | |
| `LOOKUP_OUTAGE` | get / search | 503 | |
