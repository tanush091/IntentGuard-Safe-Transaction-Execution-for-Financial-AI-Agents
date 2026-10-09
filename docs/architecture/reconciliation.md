# Reconciliation and recovery

Target spec: [ARCHITECTURE.md §5 Data flow](../ARCHITECTURE.md#5-data-flow) (5.2 to 5.7) and [API.md §5](../API.md#5-reconciliation-and-recovery), [§6](../API.md#6-exceptions-and-ai-investigation), [§8](../API.md#8-webhooks-provider--gateway). This page describes the code as built.

Code:

- Engine: `IntentGuard.reconcile`, `recover`, `_maybe_retry`, `_absorb`, `tick_detailed`,
  `startup_recovery` and `observe` in [`backend/intentguard/engine.py`](../../backend/intentguard/engine.py).
  Parameters are in `ProtocolConfig` ([`config.py`](../../backend/intentguard/config.py)).
- Gateway: the worker loop in [`backend/gateway_api/main.py`](../../backend/gateway_api/main.py),
  webhooks in [`backend/gateway_api/webhooks.py`](../../backend/gateway_api/webhooks.py), reconciliation
  runs in [`backend/gateway_api/reconciliation.py`](../../backend/gateway_api/reconciliation.py), the
  endpoints in `backend/gateway_api/routers/recovery.py` and `routers/webhooks.py`.
- Simulator webhooks: [`backend/paysim/webhooks.py`](../../backend/paysim/webhooks.py).
- AI investigator: [`backend/investigator/`](../../backend/investigator/).

## Unknown outcomes

A provider call that returns no usable answer (client timeout, a lost response reported as 504, any
other 5xx, a network error) leaves the attempt `UNKNOWN`. It is **never** treated as failed. Only a
definitive rejection (4xx) makes it `FAILED`. The intent moves to `UNKNOWN`, which the gateway owns:
further proposals get `DUPLICATE` (`ATTEMPT_IN_PROGRESS`), and a cancel request is refused with 409
`ATTEMPT_IN_PROGRESS`.

An attempt also becomes `UNKNOWN` when:

- it is still `SUBMITTING` after its lease (`submit_lease_s`, 15 s), for example because the gateway
  hung or crashed between recording the attempt and recording the response (`attempt.lease_expired`);
- the gateway restarts and finds `SUBMITTING` attempts from a previous process, identified by a
  different `incarnation` (`startup_recovery`, `attempt.orphaned`).

After a successful create the gateway reads the transaction back (`readback_verification`). If the
read-back fails, it keeps the create response and reconciliation re-reads later.

## How reconciliation looks for evidence

For an intent in `IN_FLIGHT`, `EXECUTING`, `UNKNOWN`, `DISCREPANCY`, `CANCEL_REQUESTED` or
`COMPLETED`, `reconcile` does this, outside any database lock:

1. **Lookup by id** (strongly consistent) of every provider transaction id already known from attempts
   and effects.
2. **Search by order** (eventually consistent), only when an attempt is `SUBMITTING` or `UNKNOWN`, or
   during the post-completion watch. A search result is attributed to the intent if its metadata
   carries this `intent_id` or one of its `attempt_id`s, or if its idempotency key is one of this
   intent's keys.

Then, under the intent lock, it absorbs every transaction found (`_absorb` records or updates the
effect and attributes it to the attempts that produced it), expires leases, applies the absence rule
below, and re-derives the intent state ([state-machine.md](state-machine.md#how-the-next-state-is-chosen)).

## The absence window

Provider search is eventually consistent: a transaction can exist and still be missing from search
results (the simulator's `DELAYED_VISIBILITY` fault). "Not found" is therefore weak evidence.

An `UNKNOWN` attempt becomes `RECONCILED` (`attempt.absence_confirmed`) only if **all** of these hold:

- the lookups and the search in this pass succeeded;
- a search was performed in this pass;
- at least `absence_window_s` (30 s, `ABSENCE_WINDOW_S`) have passed since the attempt was created.

Only then does an intent with an unknown outcome become `RECONCILING`. The gateway then retries by itself
(`attempt.controlled_retry`) under the *same* idempotency key, re-sending the last attempt's
parameters, so even if the transaction surfaces late the provider replays it instead of executing a
second one. The retry counts against `max_attempts` (3); when the budget is used up, a review case
`ATTEMPT_BUDGET_EXHAUSTED` is opened instead.

If a transaction for a `RECONCILED` attempt turns up later, the attempt is corrected to `SUCCEEDED`
and `attempt.absence_assumption_violated` is written to the audit log. Attribution also matches on
the idempotency key, so after a same-key controlled retry the new transaction is attributed to the
earlier `RECONCILED` attempt as well, and the event is written even when that attempt really had no
effect (see the second [worked example](#worked-examples)).

If the provider cannot be queried (`LOOKUP_OUTAGE`, 5xx, or a lookup that fails), nothing is
concluded and `reconcile.lookup_failed` is audited. If the intent is still `UNKNOWN`
`unknown_review_after_s` (300 s) after the outcome first became unknown, a review case
`UNRESOLVABLE_OUTCOME` is opened and the intent is `ESCALATED`. The gateway does not guess.

Ablations: `absence_window_s=0` trusts the first successful "not found"; `reconciliation=False`
marks a failed call `RECONCILED` immediately. Their measured effect is in
[../research/results.md](../research/results.md).

## Post-completion watch

When an intent completes after more than one attempt, or after any attempt error, the gateway keeps
reconciling it until `watch_until = now + 2 × absence_window_s`, searching by order on every pass. A
late-visible duplicate or mismatch found in this period reopens it (`COMPLETED → DISCREPANCY`).

## State-aware recovery

An intent is in `DISCREPANCY` while a live effect that is not `INTENDED` and not remediated exists: a
wrong amount, order, customer, currency or operation (`MISMATCH`), or a second matching effect
(`DUPLICATE`). In `CANCEL_REQUESTED` every live, unremediated effect is a target, the intended one
included. `recover` re-reads each target and applies the cancellation policy
(`domain.cancellation_policy`):

| Operation | Provider status | Action | Outcome |
|---|---|---|---|
| Refund | `PENDING` | cancel, then read back | `CANCELLED` → `effect.reversal_verified`; still live → review `CANCEL_UNVERIFIED` |
| Refund | `COMPLETED` | none: the provider cannot reverse it | review `IRREVERSIBLE_DISCREPANCY` with the amount at stake |
| Authorization hold | `PENDING` or `COMPLETED` (authorized) | void, then read back | as for a pending refund |
| Any | the provider refuses the cancel (a definitive rejection, e.g. 409) | | review `CANCEL_REJECTED` |
| Any | the re-read, the cancel or the read-back gives no usable answer | count a try on the effect | review `CANCEL_UNVERIFIED` after `max_cancel_tries` (3) |
| Any | already `CANCELLED`/`FAILED` when re-read | nothing to do | |

A reversal is recorded only when the provider's read-back shows `CANCELLED`. Nothing is ever reported
as reversed on the strength of a cancel call alone. The amount at stake (`discrepancy_minor`) is the
full amount for a duplicate or an effect on the wrong order, customer, currency or operation, and the
difference otherwise.

Once nothing unintended is live, the intent re-derives. If the reversed effect came from the
gateway's own last attempt, the intent is `RECONCILING` and the gateway retries the correct operation
under the next key generation, within the attempt budget.

Ablation: `state_aware_recovery=False` issues a cancel blindly, does not verify it, and marks the
effect remediated anyway (`effect.reversal_assumed`). This is the "claims a reversal that never
happened" behaviour the protocol exists to prevent.

## Idempotency key generations

Every attempt for an intent carries the provider idempotency key

```
ig-<intent_id>-g<key_generation>
```

for example `ig-INT-1001-g0`.

- It is derived from the **intent**, not from the agent's request ID. A restarted agent, a second
  concurrent agent and the gateway's own retry all send the same key, so the provider replays the
  original transaction instead of executing a new one (and rejects the key if the parameters differ).
- `key_generation` starts at 0. It is incremented only when an effect produced by one of the intent's
  attempts is **verifiably reversed**, or when a reviewer resolves a case as
  `REFUND_RECOVERED_OUT_OF_BAND`. The next retry then gets a fresh key, so it executes the correct
  operation instead of replaying the reversed or remediated transaction.
- A timeout, an unknown outcome or a confirmed absence does **not** change the generation.
- The key is stored on the attempt and never returned by the API.

Ablation: `stable_idempotency_key=False` uses `ig-<intent_id>-a<attempt_no>`, a new key per attempt,
which is what request-scoped idempotency amounts to.

## The background worker

`worker_loop` in `backend/gateway_api/main.py` runs inside the gateway process. It calls
`IntentGuard.tick_detailed` in a thread, then sleeps `WORKER_INTERVAL_S` (2 s), and repeats:

- It takes up to 200 intents whose `next_check_at` is due, earliest first.
- For each, it reconciles (if the state is reconcilable), then drives the intent (`_drive`: reconcile,
  recover, controlled retry). If the next check is still due afterwards, it is pushed back by
  `poll_interval_s`.
- When the pass processed at least one intent, it is recorded as a `WORKER` reconciliation run.
- An exception is logged and the loop continues.

`next_check_at` is set on every re-derivation (`engine._refresh`):

| State | Next check |
|---|---|
| `IN_FLIGHT` | When the earliest `SUBMITTING` lease expires |
| `UNKNOWN`, `EXECUTING`, `DISCREPANCY`, `CANCEL_REQUESTED` | `now + max(poll_interval_s, min(max_poll_interval_s, 0.5 × seconds since the last state change))`, i.e. 5 s to 60 s by default |
| `RECONCILING`, when a controlled retry is allowed | Now |
| `COMPLETED`, during the post-completion watch | The back-off above, capped at `watch_until` |
| Anything else | None |

On startup the gateway runs `startup_recovery` (orphaned `SUBMITTING` attempts become `UNKNOWN`, then
each affected intent is reconciled and driven) before the worker starts. With `SIMULATOR_MODE=true`,
`POST /api/dev/worker/tick` runs one pass on demand; it does not record a run.

`absence_window_s`, `max_attempts` (`attempt_budget`) and `unknown_review_after_s` can be changed by
an admin with `PUT /api/admin/policies`. The change applies at once, is stored in the `policies`
table, and is applied again at startup.

## Forcing a pass

`POST /api/attempts/{attempt_id}/reconcile` (operator, reviewer, admin) runs one reconciliation pass
for the attempt's intent and reports what it found. It does not drive the intent; a retry it makes
possible is run by the worker.

| `outcome` | When |
|---|---|
| `NOT_RECONCILABLE` | The intent is not in a reconcilable state |
| `PROVIDER_UNREACHABLE` | A lookup or the search failed |
| `DISCREPANCY` | The intent is in `DISCREPANCY` after the pass |
| `EFFECT_FOUND` | The attempt is `SUCCEEDED` |
| `ABSENT_CONFIRMED` | The attempt is `RECONCILED` |
| `REJECTED_BY_PROVIDER` | The attempt is `FAILED` |
| `ABSENT_PENDING_WINDOW` | Otherwise: not found yet, inside the absence window. Not evidence of no effect |

`next_action` is `CONTROLLED_RETRY` when the intent is `RECONCILING` and a retry is allowed now,
`HOLD_FOR_REVIEW` when it is `ESCALATED`, and `NONE` otherwise. `evidence` lists the effects found in
this pass (`provider_lookup`) and, if a search ran, the search (`provider_search`).

## Provider webhooks

Webhooks are hints. The gateway never takes a transaction's state from the payload; it re-fetches the
transaction from the provider.

**Sender** (`backend/paysim/webhooks.py`). `provider_api` starts a `WebhookEmitter` thread when
`PAYSIM_WEBHOOK_URL` and a secret (`PAYSIM_WEBHOOK_SECRET` or `WEBHOOK_SECRET`) are set. It emits one
event per transaction status change, with a deterministic id `evt_<transaction>_<status>`, a type such
as `refund.completed`, a per-transaction `sequence` and the transaction as `data.object`. The header is
`Paysim-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>." + raw body>`. Failed deliveries are
retried with exponential back-off, up to 6 tries. Faults: `WEBHOOK_DUPLICATE` delivers the next event
for the order twice; `WEBHOOK_DELAY` delivers it `delay_s` late, so later events can overtake it.

**Receiver** (`POST /api/webhooks/{provider}`, only `paysim`; authenticated by signature, not JWT):

1. **Verify** the signature over the raw body before parsing anything. The secret is the provider's
   `provider_configs.webhook_secret` if set, else `WEBHOOK_SECRET`; with no secret every event is
   refused. Missing, malformed or wrong signature → 400 `INVALID_SIGNATURE` (constant-time compare);
   timestamp further than `WEBHOOK_TOLERANCE_S` (300 s) from now → 400 `STALE_EVENT`; a body without
   `id`, `type` and `data.object.id` → 400 `MALFORMED_EVENT`.
2. **Dedupe**: the event is inserted into `webhook_events`, unique on (`provider`, `event_id`). A
   repeat only increments `deliveries` and is answered `200 {"status": "duplicate"}`. A new event is
   answered `200 {"status": "accepted"}` and processed in a background task.
3. **Re-fetch**: the intent comes from the transaction's `metadata.intent_id`, the operation from its
   `kind`. `engine.observe` fetches the transaction by id from the provider (strongly consistent),
   absorbs it, re-derives and drives the intent.

The processing outcome is stored on the event:

| `outcome` | Meaning |
|---|---|
| `absorbed` | Re-fetched and absorbed into a known, non-terminal intent |
| `provider_unreachable: …` | The re-fetch failed; nothing changed |
| `unknown_intent` | No known intent; if the payload says the transaction is live, a `MISSING` mismatch is recorded |
| `terminal_intent` / `terminal_intent_live_effect` | The intent is `CANCELLED` or `CLOSED`; nothing is absorbed. A live transaction is recorded as a `MISSING` mismatch |
| `unsupported_object` | The object is neither a refund nor an authorization |

Because each event only triggers a re-fetch of the current provider state, delivery order does not
matter; `sequence` and the event time are stored but not used for ordering. A webhook can resolve a
lost response that search cannot see yet, because the re-fetch is a lookup by id
(`test_webhook_resolves_a_lost_response_hidden_from_search`).

## Reconciliation runs

Stored in `reconciliation_runs` (`RUN-n`) and listed by `GET /api/reconciliation/runs` (operator,
reviewer, admin; filter `kind`).

**`WORKER`** runs record what one worker pass did: `examined` (intents processed), `resolved`
(intents that reached `COMPLETED` or `CANCELLED` in the pass), `escalated` (intents that became
`ESCALATED`).

**`MATCHING`** runs compare the gateway's ledger with the provider and **report** mismatches. They
never change money, intent state or effects, and never resolve a mismatch.
`POST /api/reconciliation/runs` (reviewer, admin) records the run, answers 202
`{"run_id": "RUN-n", "status": "started"}` and runs the pass as a background task; with `?wait=true`
it runs the pass first and the response (still 202) carries `examined`, `mismatches_found` and
`errors`. A pass:

1. **Provider to ledger.** For every order in `orders` and each operation, it lists the provider's
   transactions. A live transaction with no effect row is `MISSING`, unless its metadata names an
   intent that is `IN_FLIGHT` or `UNKNOWN` (the engine is still establishing that outcome).
2. **Ledger to provider.** For every live, unremediated effect of a known intent: if the listing did
   not show it, the transaction is looked up by id, and if the provider does not know it, it is
   `MISSING`. Otherwise the effect (as recorded in the ledger) is compared with its intent: `ORDER`,
   `CUSTOMER`, or `AMOUNT` (amount or currency) for each field that differs; an effect with a
   different operation is reported as `ORDER`.
3. **Duplicates.** More than one live effect exactly matching the same intent is `DUPLICATE`.
4. A finding is stored only if no `OPEN` mismatch with the same fingerprint exists. The run records
   `examined` (provider transactions listed plus ledger effects), `errors` (failed provider calls) and
   `mismatches_found` (new mismatches), and `reconciliation.run` is audited.

## Mismatches

Stored in `mismatches` (`MM-n`), from matching runs (`run_id` set) and from webhook processing
(`run_id` null, `details.source = "webhook"`). Kinds: `MISSING`, `DUPLICATE`, `AMOUNT`, `ORDER`,
`CUSTOMER`.

- `GET /api/reconciliation/mismatches` (operator, reviewer, admin): filters `kind` and `status`
  (default `OPEN`), cursor pagination.
- `POST /api/reconciliation/mismatches/{id}/resolve` (reviewer, admin), body `{"note": "…"}`: marks it
  `RESOLVED`, adds `resolved_by` and `note` to `details`, and audits `mismatch.resolved`. It records
  that a person handled the mismatch; it changes nothing else. A mismatch that is not open is 409
  `ALREADY_RESOLVED`.

## AI investigator

The investigator is advisory. It classifies an exception and recommends one action; a deterministic
policy gate decides whether that action is permitted, and nothing happens until a user applies a
permitted recommendation.

**When.** On demand only: `POST /api/exceptions/{intent_id}/investigate` (operator, reviewer, admin)
for an intent in `UNKNOWN`, `RECONCILING`, `DISCREPANCY`, `CANCEL_REQUESTED` or `ESCALATED` (the
states `GET /api/exceptions` lists); any other state is 409 `NOT_AN_EXCEPTION`.

**Evidence** (`investigator/evidence.py`). The bundle holds the intent, its attempts, effects, webhook
events and review cases from the ledger, plus fresh read-only provider lookups (every known
transaction id and the order's transactions that carry this intent's id or one of its attempt ids).
Every item has a reference (`ATT-001`, `EFF-1`, `WH-3`, `RC-2`, `PROVIDER:<id>`, the intent id) that
the output must cite. Provider idempotency keys and secrets are not included; the ticket is truncated
to 500 characters and marked untrusted. The facts the gate uses (provider reachable, live
transactions that match the authorization exactly, unintended live transactions and whether one is
cancellable, whether a controlled retry is allowed, open review, remaining attempt budget) are
computed by code, never by the model.

**Classifier** (`investigator/classifier.py`). Without an LLM configured (`LLM_PROVIDER` unset or
`offline`) the `OfflineClassifier` applies deterministic rules. With `LLM_PROVIDER` set to `openai`,
`gemini` or `ollama`, the `LLMClassifier` sends a fixed system prompt with the evidence between
delimiters as data. Its output must be one JSON object with exactly `classification` (`LOST_RESPONSE`,
`PROVIDER_DELAY`, `AMOUNT_MISMATCH`, `WRONG_ORDER`, `UNKNOWN`), `summary` (at most 800 characters),
`evidence_refs` (non-empty, all from the bundle) and `recommended_action` (`MARK_COMPLETED`,
`WAIT_AND_RECHECK`, `CONTROLLED_RETRY`, `CANCEL_PENDING`, `ESCALATE`). Output that breaks the schema,
or a failed LLM call, is stored with `valid_output = false` and answered with 422
`INVALID_INVESTIGATOR_OUTPUT`; it is never repaired.

**Policy gate** (`investigator/policy.py`). Confidence is not an input. A `CANCELLED` or `CLOSED`
intent refuses everything (`intent_is_terminal`). Otherwise:

| Action | Permitted when | Refusal rules |
|---|---|---|
| `MARK_COMPLETED` | No open review, provider reachable, no unintended live transaction, and a live transaction that matches the authorization exactly | `requires_review_resolution`, `provider_unreachable`, `unintended_effect_live`, `no_matching_effect_at_provider` |
| `WAIT_AND_RECHECK` | State `UNKNOWN`, `DISCREPANCY` or `CANCEL_REQUESTED` | `nothing_pending` |
| `CONTROLLED_RETRY` | State not `UNKNOWN`, attempt budget left, and the engine allows a controlled retry now | `absence_not_verified`, `attempt_budget_exhausted`, `retry_not_supported_by_evidence` |
| `CANCEL_PENDING` | State `DISCREPANCY` or `CANCEL_REQUESTED`, and an unintended live transaction that can be cancelled | `no_discrepancy_or_cancel_request`, `effect_not_cancellable` |
| `ESCALATE` | State not already `ESCALATED` | `already_escalated` |

The investigation, the verdict, the prompt and the raw output are stored in `investigations` and
audited (`investigation.created`).

**Apply** (`POST /api/investigations/{id}/apply`, operator, reviewer, admin). The gate is re-checked
on a freshly built bundle first; if it now refuses, the answer is 409 `POLICY_REFUSED` and nothing
changes. A rejected output cannot be applied (409 `POLICY_REFUSED`), and applying twice is 409
`ALREADY_APPLIED`. A permitted action runs through the engine's own operations:

| Action | Engine call |
|---|---|
| `MARK_COMPLETED` | `observe` for each matching live transaction: re-fetch and absorb, the same path as a webhook. The state is whatever the ledger then derives |
| `WAIT_AND_RECHECK` | `schedule_recheck`: next check now (`intent.recheck_scheduled`) |
| `CONTROLLED_RETRY` | `retry_now`: the worker's controlled retry, same rules |
| `CANCEL_PENDING` | `recover`, then `_drive` |
| `ESCALATE` | `escalate`: review case `INVESTIGATOR_ESCALATION` |

## Worked examples

Traced from the engine with the in-process simulator and a simulated clock (the `world` fixture in
`backend/tests/conftest.py`): a ₹1,500.00 refund on `ORD-204`, faults injected on the order. State
changes are the `intent.state` audit events.

Lost response (`TIMEOUT_AFTER_EXECUTION`):

```
AUTHORIZED -> IN_FLIGHT     proposal allowed; ATT-001 reserved with key ig-INT-1001-g0
IN_FLIGHT  -> UNKNOWN       the provider executed the refund; the response was lost (504)
UNKNOWN    -> COMPLETED     the inline reconciliation found it by order search (intent_id metadata)
```

One refund at the provider. With `DELAYED_VISIBILITY` (20 s) and `DELAYED_STATUS` added, search does
not show it at first, absence is not concluded inside the 30 s window, and the intent goes
`UNKNOWN → EXECUTING → COMPLETED` once it is visible and settles.

Timeout before execution (`TIMEOUT_BEFORE_EXECUTION`):

```
AUTHORIZED  -> IN_FLIGHT    ATT-001, key ig-INT-1001-g0
IN_FLIGHT   -> UNKNOWN      timeout; nothing executed
UNKNOWN     -> RECONCILING  after the absence window: lookups and search succeeded, nothing found
RECONCILING -> IN_FLIGHT    attempt.controlled_retry: ATT-002, same key ig-INT-1001-g0
IN_FLIGHT   -> COMPLETED
```

One refund at the provider. Because ATT-002 used the same key, ATT-001 is also marked `SUCCEEDED`
and `attempt.absence_assumption_violated` is audited for it.

Wrong amount, still pending (`CORRUPT_AMOUNT` ×10 with `DELAYED_STATUS`):

```
AUTHORIZED  -> IN_FLIGHT    ATT-001, key ig-INT-1001-g0
IN_FLIGHT   -> DISCREPANCY  the provider recorded 15,000.00 (MISMATCH, PENDING)
DISCREPANCY -> RECONCILING  cancelled and read back CANCELLED (effect.reversal_verified); generation 0 -> 1
RECONCILING -> IN_FLIGHT    attempt.controlled_retry: ATT-002, key ig-INT-1001-g1
IN_FLIGHT   -> COMPLETED    the correct 1,500.00 refund
```

Wrong amount, already completed (`CORRUPT_AMOUNT` ×10, no settlement delay):
`IN_FLIGHT → DISCREPANCY → ESCALATED` with review case `IRREVERSIBLE_DISCREPANCY` and 13,500.00 at
stake. The provider still shows the wrong refund as `COMPLETED`, and the gateway never reports it as
reversed.
