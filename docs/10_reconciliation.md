# 10. Active Reconciliation

## Handling Uncertain Outcomes in Financial Distributed Systems

In distributed transaction processing, network timeouts or connection drops create an `UNKNOWN` state. In naive AI systems, an agent typically assumes failure and immediately re-submits the transaction, resulting in dangerous duplicate financial effects.

IntentGuard enforces the rule:
> **An UNKNOWN outcome must NEVER result in an automatic, immediate retry without active external reconciliation.**

---

## The 8-Step Reconciliation Algorithm

When an execution attempt times out or yields an indeterminate HTTP status:
1. Mark `attempt.status = UNKNOWN`.
2. Transition transaction FSM: `SUBMITTED → UNKNOWN → RECONCILING`.
3. Query mock payment provider by `provider_reference` (if an early ACK was logged).
4. Query mock payment provider by `order_id` (`GET /refunds?order_id=ORD-204`).
5. Scan returned external effects and compare them with the durable authorization record:
   - Does an effect match the authorized `amount`?
   - Does an effect match the authorized `currency`?
   - Does an effect match the authorized `operation_type`?
6. Check whether any discovered effect is already linked to another intent in the local ledger.
7. Formulate a reconciliation verdict:
   - **Case 1: Effect Observed and Verified (COMPLETED)**
     The refund executed successfully before the network timed out. Record the effect into `effects`, mark attempt `COMPLETED`, and transition intent to `COMPLETED`. **Result**: Duplicate execution avoided.
   - **Case 2: Zero Effect Observed (RETRY_ALLOWED)**
     Payment provider confirms no record exists for this order/attempt. Transition intent to `RETRY_ALLOWED`. A new attempt may now proceed with an incremented attempt number and unique idempotency key.
   - **Case 3: Inconsistent / Incorrect Effect Discovered**
     An unexpected effect is discovered (e.g., wrong amount or wrong customer). Transition intent to `CANCEL_REQUESTED` and attempt provider cancellation.
8. If the provider state remains ambiguous or cancellation fails, transition to `ESCALATED` and generate an urgent `ReviewCase` for human operator investigation.
