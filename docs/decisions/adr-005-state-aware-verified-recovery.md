# ADR-005: Recovery is state-aware and verified; otherwise escalate

**Status:** Accepted

## Context
A provider can execute the wrong amount, or an agent mistake can slip through under an ablation.
Some effects can be reversed (pending refunds, authorization holds) and some cannot (completed
refunds). Reporting a reversal because a cancel call was issued is a false claim.

## Decision
`recover` applies `domain.cancellation_policy`: cancel a pending refund, void a pending or
authorized hold, then read the transaction back and record a reversal only if it is `CANCELLED`.
A completed refund, a rejected cancel, or a cancel that cannot be verified after 3 tries opens a
review case with the amount at stake. The intent is `DISCREPANCY` until nothing unintended is live.

## Consequences
- Wrong money that cannot be reversed is never hidden: undetected wrong money is ₹0 for the full protocol in the recorded run.
- Some cases need a human. That is the measured cost (human reviews per 300 scenarios).
