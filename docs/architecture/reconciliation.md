# Reconciliation and recovery

Code: `IntentGuard.reconcile`, `recover`, `_maybe_retry` and `_absorb` in
[`backend/intentguard/engine.py`](../../backend/intentguard/engine.py). Parameters are in
`ProtocolConfig` ([`config.py`](../../backend/intentguard/config.py)).

## Unknown outcomes

A provider call that returns no usable answer (client timeout, lost response reported as 504, any
5xx, a network error) leaves the attempt `UNKNOWN`. It is **never** treated as failed. The intent
moves to `OUTCOME_UNKNOWN`, which the gateway owns: further agent proposals get `IN_PROGRESS`.

An attempt also becomes `UNKNOWN` when:

- it is still `SUBMITTING` after its lease (`submit_lease_s`, 15 s), for example because the
  gateway hung or crashed between recording the attempt and recording the response;
- the gateway restarts and finds `SUBMITTING` attempts from a previous process (`startup_recovery`).

## How reconciliation looks for evidence

For an intent in `IN_FLIGHT`, `PENDING_SETTLEMENT`, `OUTCOME_UNKNOWN`, `DISCREPANCY` or
`COMPLETED`, `reconcile` does this, outside any database lock:

1. **Lookup by id** (strongly consistent) of every provider reference already known from attempts
   and effects.
2. **Search by order** (eventually consistent), only when an attempt is `SUBMITTING` or `UNKNOWN`,
   or during the post-completion watch. A search result is attributed to the intent if its
   metadata carries this `intent_id` or one of its `attempt_id`s, or if its idempotency key is one
   of this intent's keys.

Then, under the intent lock, it absorbs every transaction found, re-classifies effects and
re-derives the intent state.

## The absence window

Provider search is eventually consistent: a transaction can exist and still be missing from search
results (the simulator's `DELAYED_VISIBILITY` fault). "Not found" is therefore weak evidence.

An `UNKNOWN` attempt becomes `NO_EFFECT` only if **all** of these hold:

- the lookups and the search in this pass succeeded;
- a search was performed;
- at least `absence_window_s` (30 s, `ABSENCE_WINDOW_S`) have passed since the attempt was created.

Only then does the intent become `RETRYABLE`, and the gateway itself retries
(`attempt.controlled_retry`) under the *same* idempotency key, so even if the transaction surfaces
late the provider replays it instead of executing a second one. If a transaction for a `NO_EFFECT`
attempt turns up later anyway, the attempt is corrected to `ACKNOWLEDGED` and
`attempt.absence_assumption_violated` is written to the audit log.

If the provider cannot be queried (`LOOKUP_OUTAGE`, 5xx), nothing is concluded
(`reconcile.lookup_failed` is audited). If the intent stays `OUTCOME_UNKNOWN` for
`unknown_review_after_s` (300 s), a review case `UNRESOLVABLE_OUTCOME` is opened. The gateway does
not guess.

Ablations: `absence_window_s=0` trusts the first successful "not found"; `reconciliation=False`
marks a failed call `NO_EFFECT` immediately. Their measured effect is in
[../research/results.md](../research/results.md).

## Post-completion watch

When an intent completes after more than one attempt, or after any attempt error, the gateway
keeps reconciling it until `watch_until = now + 2 × absence_window_s`. A late-visible duplicate or
mismatch found in this period reopens it (`COMPLETED → DISCREPANCY`).

## State-aware recovery

An intent is in `DISCREPANCY` while a live effect that is not `INTENDED` and not remediated
exists: a wrong amount, order, customer, currency or operation (`MISMATCH`), or a second matching
effect (`DUPLICATE`). `recover` re-reads each such effect and applies the cancellation policy
(`domain.cancellation_policy`):

| Operation | Provider status | Action | Outcome |
|---|---|---|---|
| Refund | `PENDING` | cancel, then read back | `CANCELLED` → `effect.reversal_verified`; otherwise review `CANCEL_UNVERIFIED` |
| Refund | `COMPLETED` | none: the provider cannot reverse it | review `IRREVERSIBLE_DISCREPANCY` with the amount at stake |
| Authorization hold | `PENDING` or `COMPLETED` (authorized) | void, then read back | as for a pending refund |
| Any | cancel refused (409) | | review `CANCEL_REJECTED` |
| Any | cancel or read-back gives no usable answer | count a try | review `CANCEL_UNVERIFIED` after `max_cancel_tries` (3) |
| Any | already `CANCELLED`/`FAILED` when re-read | nothing to do | |

A reversal is recorded only when the provider's read-back shows `CANCELLED`. Nothing is ever
reported as reversed on the strength of a cancel call alone. The amount at stake
(`discrepancy_minor`) is the full amount for a duplicate or an effect on the wrong
order/customer/currency/operation, and the difference otherwise.

Once nothing unintended is live, the intent re-derives. If the reversed effect came from the
gateway's own last attempt, the intent is `RETRYABLE` and the gateway retries the correct
operation, within the attempt budget (`max_attempts` = 3, then review `ATTEMPT_BUDGET_EXHAUSTED`).

Ablation: `state_aware_recovery=False` issues a cancel blindly, does not verify it, and marks the
effect remediated anyway (`effect.reversal_assumed`). This is the "claims a reversal that never
happened" behaviour the protocol exists to prevent.

## Idempotency key generations

Every attempt for an intent carries the provider idempotency key

```
ig-<intent_id>-g<key_generation>
```

- It is derived from the **intent**, not from the agent's request ID. A restarted agent, a second
  concurrent agent and the gateway's own retry all send the same key, so the provider replays the
  original transaction instead of executing a new one (and rejects the key if the parameters differ).
- `key_generation` starts at 0 and is incremented only when a wrong effect produced by one of the
  intent's attempts is **verifiably reversed**, or when a reviewer resolves a case as
  `MANUALLY_REMEDIATED`. The next retry then gets a fresh key, so it executes the correct operation
  instead of replaying the reversed or remediated transaction.
- A timeout, an unknown outcome or a confirmed absence does **not** change the generation.

Ablation: `stable_idempotency_key=False` uses `ig-<intent_id>-a<attempt_no>`, a new key per
attempt, which is what request-scoped idempotency amounts to.

## Worked example (verified on the running stack)

Lost response on `ORD-311`, ₹2,000 refund (see [../operations/demo.md](../operations/demo.md)):

```
AUTHORIZED -> IN_FLIGHT            proposal approved, attempt 1 reserved (key ig-<intent>-g0)
IN_FLIGHT -> OUTCOME_UNKNOWN       provider executed the refund but the response was lost (504)
OUTCOME_UNKNOWN -> PENDING_SETTLEMENT   reconciliation found it by search (intent_id metadata)
PENDING_SETTLEMENT -> COMPLETED    worker saw it settle
```

The provider ledger holds exactly one refund for the intent.
