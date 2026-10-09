> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# 09. Safety Gateway

## The 10-Point Pre-Execution Validation Protocol

The Safety Gateway acts as the deterministic gatekeeper. Every proposed financial transaction must successfully pass all 10 independent verification checks before any network packet is dispatched to the payment simulator.

---

## The 10 Invariant Checks

```
┌─────────────────────────────────────────────────────────────┐
│                 10-POINT GATEWAY PIPELINE                   │
│                                                             │
│  [1] Customer Match      ──► [6] Operator Authorization     │
│  [2] Order Match         ──► [7] Duplicate Effect Check     │
│  [3] Operation Match     ──► [8] Concurrent In-Flight Check │
│  [4] Amount Conformity   ──► [9] Existing Provider Effect   │
│  [5] Currency Match      ──► [10] FSM State Validity        │
└─────────────────────────────────────────────────────────────┘
```

### Check 1 — Customer Identification
- **Rule**: `proposal.customer_id == intent.customer_id`
- **Failure Consequence**: `BLOCKED` (Reason: "Customer mismatch: proposed C-99 does not match authorized C-17").

### Check 2 — Order Association
- **Rule**: `proposal.order_id == intent.order_id`
- **Failure Consequence**: `BLOCKED` (Reason: "Order mismatch: proposed ORD-240 does not match authorized ORD-204").

### Check 3 — Operation Type
- **Rule**: `proposal.operation == intent.operation_type`
- **Failure Consequence**: `BLOCKED` (Reason: "Operation mismatch: proposed PAYMENT does not match authorized REFUND").

### Check 4 — Amount Conformity
- **Rule**: `proposal.amount == intent.authorized_amount` (Exact match policy for initial prototype).
- **Failure Consequence**: `BLOCKED` (Reason: "Amount mismatch: proposed 15000.00 violates authorized limit of 1500.00").

### Check 5 — Currency Code
- **Rule**: `proposal.currency.upper() == intent.currency.upper()`
- **Failure Consequence**: `BLOCKED` (Reason: "Currency mismatch: proposed USD does not match authorized INR").

### Check 6 — Operator Authorization
- **Rule**: Verify that `intent.operator_id` is a recognized, valid operator with active signing authority.
- **Failure Consequence**: `BLOCKED` (Reason: "Operator OP-99 is revoked or unauthorized").

### Check 7 — Duplicate Completed Effect
- **Rule**: Check the durable `effects` ledger. If a `COMPLETED` effect already exists for this `intent_id`, reject.
- **Failure Consequence**: `BLOCKED` (Reason: "Intent INT-001 already has a settled effect ref_sim_123 in ledger").

### Check 8 — Concurrent Attempt Lock
- **Rule**: Check if another attempt for `intent_id` is currently in status `SUBMITTED`, `PENDING`, or `RECONCILING`.
- **Failure Consequence**: `BLOCKED` (Reason: "Active execution attempt already in flight for intent INT-001").

### Check 9 — Existing External Provider Effect
- **Rule**: Proactively query the mock payment service (`GET /refunds?order_id=...`). If a completed refund exists for this order that has not been reconciled, halt.
- **Failure Consequence**: `BLOCKED` (Reason: "Payment service already reports settled effect for order ORD-204").

### Check 10 — Transaction State Validity
- **Rule**: Confirm that the transition from `intent.current_state` to `APPROVED` is permitted by the formal FSM.
- **Failure Consequence**: `BLOCKED` (Reason: "Cannot transition from state CANCELLED to APPROVED").

---

## Audit Decision Logging
Every decision produces an immutable `audit_events` record:
- Decision (`APPROVED` or `BLOCKED`)
- Timestamp (UTC)
- Intent ID
- Detailed breakdown of all checks evaluated
- Explicit failure reason (if blocked)
