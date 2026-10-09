> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

# 01 — Project Overview

## Problem
Financial AI agents can make incorrect transaction proposals or repeat a transaction after an uncertain API outcome. A successful API request does not necessarily prove that the intended financial effect occurred.

## Proposed Solution
Place a deterministic transaction-safety gateway between the AI agent and a simulated payment service.

The gateway:
1. Binds the action to a durable authorization.
2. Validates customer, order, operation, amount, and currency.
3. Assigns attempts to the original intent.
4. Prevents duplicate effects.
5. Records uncertain outcomes.
6. Reconciles with the payment service.
7. Retries only when evidence supports a retry.
8. Cancels only when the provider state allows it.
9. Escalates unresolved discrepancies.

## Key Identity Model
`intent_id` = original authorized business intent.

`attempt_id` = one API execution attempt.

Multiple attempts can belong to one intent:

INT-1001
- ATT-001
- ATT-002
- ATT-003

A new attempt must not automatically become a new authorization.

## Example
Authorization:
Refund ₹1,500 for ORD-204 to C-17.

If the refund executes but the response times out:

Timeout → UNKNOWN → Reconcile → Find provider effect → Verify → COMPLETE

The system must not immediately issue another refund.
