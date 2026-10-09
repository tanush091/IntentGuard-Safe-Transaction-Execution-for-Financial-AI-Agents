> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

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
| SQLite / PostgreSQL Ledger   |
| Audit + transaction state  |
+-------------+--------------+
              |
              v
        Vanilla HTML/CSS/JS Dashboard
```

## Security Boundary
The AI agent must not have direct access to the payment service.

Only the gateway can submit, retry, cancel, or finalize a transaction.

## State Machine

| Current State      | Allowed Next States                                          |
|--------------------|--------------------------------------------------------------|
| AUTHORIZED         | PROPOSED, BLOCKED                                            |
| PROPOSED           | VALIDATED, EXECUTING, BLOCKED, COMPLETED                     |
| VALIDATED          | EXECUTING, BLOCKED, COMPLETED                                |
| EXECUTING          | COMPLETED, UNKNOWN, CANCEL_REQUESTED, ESCALATED, BLOCKED     |
| UNKNOWN            | RECONCILING, ESCALATED                                       |
| RECONCILING        | COMPLETED, EXECUTING, CANCEL_REQUESTED, ESCALATED, UNKNOWN   |
| CANCEL_REQUESTED   | CANCELLED, ESCALATED                                         |
| CANCELLED          | (Terminal)                                                   |
| COMPLETED          | (Terminal)                                                   |
| BLOCKED            | PROPOSED                                                     |
| ESCALATED          | COMPLETED, CANCELLED                                         |

## Important Rule
Internal recovery must never be treated as proof that an external financial effect was reversed.
