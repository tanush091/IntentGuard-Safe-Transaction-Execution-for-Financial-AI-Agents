> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

# 07 — Experiment Scenarios

## Scenario 1 — Correct Refund
Authorization: ₹1,500 / ORD-204.
Proposal matches.
Expected: complete after provider verification.

## Scenario 2 — Wrong Amount
Proposal: ₹15,000.
Expected: block before provider call.

## Scenario 3 — Wrong Order
Proposal: ORD-240.
Expected: block.

## Scenario 4 — Timeout Before Execution
Provider never executes.
Expected: UNKNOWN → reconciliation → controlled retry if evidence is sufficient.

## Scenario 5 — Timeout After Execution
Provider completes refund but response is lost.
Expected: UNKNOWN → provider query → effect found → complete; no second refund.

## Scenario 6 — Agent Restart
Agent creates a new request ID for the same instruction.
Expected: associate with original intent and suppress duplicate effect.

## Scenario 7 — Concurrent Agents
Two agents propose the same intent simultaneously.
Expected: only one execution path is allowed.

## Scenario 8 — Incorrect Completed Refund
Provider reports a completed effect that does not match authorization.
Expected: record discrepancy and escalate.

## Scenario 9 — Pending Cancellation
Refund is pending and cancellation is supported.
Expected: cancel and verify.

## Scenario 10 — Failed Cancellation
Cancellation request fails.
Expected: preserve state and escalate if unresolved.

## Scenario 11 — Delayed Status
Provider initially reports pending, later completed.
Expected: reconciliation updates final state using observed provider evidence.

## Scenario 12 — Provider Outage
Provider unavailable during reconciliation.
Expected: keep UNKNOWN and avoid uncontrolled retry.
