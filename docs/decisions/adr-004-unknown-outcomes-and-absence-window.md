# ADR-004: Unknown outcomes are reconciled; absence counts only after a window

**Status:** Accepted (refines the earlier "active reconciliation" ADR in the archive)

## Context
After a timeout or a lost response the gateway cannot tell whether the provider executed the
operation. Retrying blindly duplicates; giving up loses legitimate work. Provider search is
eventually consistent, so "not found" right after the call is weak evidence.

## Decision
A call without a usable answer leaves the attempt `UNKNOWN` and the intent `OUTCOME_UNKNOWN`.
Reconciliation looks up known references by id and searches the order, attributing results by
`intent_id`, `attempt_id` or idempotency key. An `UNKNOWN` attempt becomes `NO_EFFECT` only after
a successful search at least `absence_window_s` (30 s) after the attempt. Only then does the
gateway retry, under the same key. If the provider cannot be queried, the intent goes to review
after `unknown_review_after_s` (300 s).

## Consequences
- No duplicate from lost responses even when search lags, provided the lag is under the window or the stable key is available.
- The window is an assumption about the provider; the ablations measure what happens when it is wrong.
- Retries after a timeout are delayed by at least the window.
