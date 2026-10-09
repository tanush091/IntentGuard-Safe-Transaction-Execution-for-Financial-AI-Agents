# Demo: four scenarios

These are the four demonstrations from the earlier prototype's dashboard, reproduced on the
current stack. The React dashboard has no one-click demo buttons; you create the intent and act as
the agent in the dashboard, and inject provider faults through the provider's API. Each scenario
below was run against `provider_api` + `gateway_api` on 2026-10-09; the outcomes shown are what
the gateway returned.

## Setup

Start the stack ([running.md](running.md)) with a fresh database so the demo orders are seeded:

| Operator | Permitted | Limit |
|---|---|---|
| `op-asha` | refunds and holds | ₹50,000 |
| `op-ravi` | refunds | ₹5,000 |

| Order | Customer | Value |
|---|---|---|
| `ORD-204` | C-17 | ₹5,000 |
| `ORD-240` | C-17 | ₹12,000 (near-miss of ORD-204) |
| `ORD-2041` | C-71 | ₹20,000 (near-miss, other customer) |
| `ORD-311` | C-17 | ₹8,000 |

Dashboard actions used below:

- **Intents → New intent**: choose operator, order, operation and amount, paste a ticket, then **Authorize intent**.
- **Intent detail**: tabs **Structured proposal** (button **Submit proposal**), **Run agent**, **Reconcile / revoke**. The timeline shows proposals, attempts, effects, reviews and audit events.
- **Reviews → Resolve…**: pick a resolution, then **Resolve case**.
- **Audit → Verify chain**.

Faults are injected at http://127.0.0.1:8001/docs → `POST /v1/faults`, or with curl:

```bash
curl -X POST http://127.0.0.1:8001/v1/faults -H "content-type: application/json" \
     -d '{"kind": "LOST_RESPONSE", "order_id": "ORD-311"}'
```

Each fault fires once for its order and is then consumed. `GET /v1/ledger?order_id=…` shows the
provider's ground truth at any time.

## 1. Unauthorized amount (the agent hallucinates)

1. New intent: `op-asha`, `ORD-204` (C-17), Refund, amount `1500`, ticket
   "Refund ₹1,500 for ORD-204 to C-17".
2. **Structured proposal**: change the amount to `15000` and **Submit proposal**.

Result: decision **`REJECTED`**, findings `AMOUNT_MISMATCH` and `BALANCE_EXCEEDED` (₹15,000 is
more than the ₹5,000 order). The intent stays `AUTHORIZED`; the provider ledger for ORD-204 is
empty. Changing the order to the near-miss `ORD-240` instead gives `ORDER_MISMATCH`
(`test_wrong_order_is_blocked`). Submitting the correct proposal afterwards is approved.

## 2. Lost response (executed, but the reply never arrives)

1. Inject `{"kind": "LOST_RESPONSE", "order_id": "ORD-311"}`.
2. New intent: `op-asha`, `ORD-311`, Refund, `2000`, ticket "Please refund ₹2,000 on ORD-311 for customer C-17".
3. **Run agent**.

Result: decision **`APPROVED`**, intent `PENDING_SETTLEMENT`, then `COMPLETED` a few seconds later.
The timeline shows:

```
AUTHORIZED -> IN_FLIGHT -> OUTCOME_UNKNOWN -> PENDING_SETTLEMENT -> COMPLETED
```

The provider executed the refund but returned 504. The gateway marked the attempt unknown, found
the refund by searching the order (it carries the intent id in its metadata) and recorded it. It
did not send a second refund: the ledger has exactly one ₹2,000 refund for this intent.

## 3. Agent restart (same instruction, new request ID)

1. New intent: `op-asha`, `ORD-240`, Refund, `1200`, ticket "Refund ₹1,200 for ORD-240 to C-17".
2. **Submit proposal** with the correct values.
3. **Submit proposal** again, unchanged. Each submission from the dashboard gets a new request ID,
   as a restarted agent's would.

Result: the first is **`APPROVED`** (`PENDING_SETTLEMENT`, then `COMPLETED`). The second is
**`DUPLICATE`** with finding `ALREADY_FULFILLED`, and returns the same provider reference. The
ledger has one refund. Had the agent's request ID been the provider key, the second request
would have been a new payment (baseline C in the benchmark). Here the key is
`ig-<intent>-g0` for every attempt of the intent.

## 4. Wrong amount at the provider

### 4a. Still pending: cancel, verify, retry

1. Inject `{"kind": "AMOUNT_MISMATCH", "order_id": "ORD-2041", "params": {"factor": 10}}`.
2. New intent: `op-asha`, `ORD-2041` (C-71), Refund, `1000`, ticket "Refund ₹1,000 for ORD-2041 to C-71".
3. **Run agent**.

Result: **`APPROVED`**, then `COMPLETED`.

```
AUTHORIZED -> IN_FLIGHT -> DISCREPANCY -> RETRYABLE -> IN_FLIGHT -> PENDING_SETTLEMENT -> COMPLETED
```

The provider created a ₹10,000 refund. The gateway classified it `MISMATCH`, cancelled it while
it was still pending, read it back as `CANCELLED` (`effect.reversal_verified`), moved to key
generation 1 and retried (`attempt.controlled_retry`). Effects: ₹10,000 `CANCELLED`, ₹1,000
`COMPLETED`. Attempt keys: `…-g0`, `…-g1`.

### 4b. Cannot be reversed: escalate, never claim a reversal

1. Inject `AMOUNT_MISMATCH` (factor 10) **and** `{"kind": "CANCEL_REJECTED", "order_id": "ORD-2041"}`.
2. New intent as in 4a, then **Run agent**.

Result: **`APPROVED`**, intent **`NEEDS_REVIEW`**:

```
AUTHORIZED -> IN_FLIGHT -> DISCREPANCY -> NEEDS_REVIEW
```

**Reviews** shows a `CANCEL_REJECTED` case with ₹9,000 at stake (₹10,000 paid instead of
₹1,000). The wrong refund stays live at the provider, and nothing reports it as reversed.

3. **Reviews → Resolve…**: reviewer `rev-meera`, resolution `MANUALLY_REMEDIATED`, notes
   "wrong refund handled with the customer", **Resolve case**.

Result: the wrong effect is marked remediated, the key generation moves to 1, and the gateway pays
the correct ₹1,000:

```
NEEDS_REVIEW -> RETRYABLE -> IN_FLIGHT -> PENDING_SETTLEMENT -> COMPLETED
```

The ₹10,000 refund remains `COMPLETED` in the provider's ledger: it is history, recorded as
remediated outside the system. **Audit → Verify chain** reports `ok`.

A refund that has already *completed* with the wrong amount cannot be cancelled at all; the
gateway opens `IRREVERSIBLE_DISCREPANCY` instead. That path is covered end to end by
`test_review_flow_over_http`. To see it live, start the provider with `PAYSIM_SETTLE_DELAY_S=0`
in its environment so refunds complete immediately.
