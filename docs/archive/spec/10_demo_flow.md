> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

# 10 — Recommended Demonstration

## Demo 1: Unauthorized Amount
Operator authorizes ₹1,500.

Agent proposes ₹15,000.

Gateway:
`BLOCKED — AMOUNT_EXCEEDS_AUTHORIZATION`

No provider effect occurs.

## Demo 2: Lost Response
Agent submits correct ₹1,500 refund.

Provider completes it.

Response is intentionally lost.

Gateway:
`UNKNOWN`

Reconciliation queries provider.

Result:
`EFFECT VERIFIED`

No duplicate refund occurs.

## Demo 3: Restart
System restarts.

Agent submits the same business request using a new request ID.

Gateway finds the existing intent/effect.

Result:
`DUPLICATE SUPPRESSED`

## Demo 4: Incorrect Completed Effect
Provider reports an unexpected amount/order.

Gateway records:
`DISCREPANCY`

Result:
`ESCALATE FOR REVIEW`

## Best Demo Message
**The AI proposes. The gateway controls. The provider effect is verified.**
