# 02 — System Architecture

```text
Operator / Customer
        |
        v
+-------------------+
|     AI Agent      |
| Intent extraction |
| Structured action |
+---------+---------+
          |
          v
+----------------------------+
|     Intent Safety Gateway  |
| Authorization validation   |
| State machine              |
| Duplicate protection       |
| Retry/recovery policy      |
+-------------+--------------+
              |
              v
+----------------------------+
|   Mock Payment Service     |
| Refund / Payment APIs      |
| Fault injection            |
+-------------+--------------+
              |
              v
+----------------------------+
| Reconciliation Engine      |
| Discover provider effects  |
| Verify financial outcome   |
| Retry / Complete / Escalate|
+-------------+--------------+
              |
              v
+----------------------------+
| PostgreSQL Effects Ledger  |
| Audit + transaction state  |
+-------------+--------------+
              |
              v
        React Dashboard
```

## Security Boundary
The AI agent must not have direct access to the payment service.

Only the gateway can submit, retry, cancel, or finalize a transaction.

## State Machine

```text
AUTHORIZED
    |
    v
PROPOSED
    |
    v
VALIDATED
    |
    v
EXECUTING
   /   /    v     v
COMPLETED  UNKNOWN
              |
              v
        RECONCILING
        /    |            v     v      v
 COMPLETED RETRY  ESCALATED

PENDING → CANCEL_REQUESTED → CANCELLED
```

## Important Rule
Internal recovery must never be treated as proof that an external financial effect was reversed.
