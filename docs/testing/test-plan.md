# Test plan

```bash
cd backend
python -m pytest            # 42 tests, about 25-60 s
```

`make test` does the same from the repository root. CI (`.github/workflows/ci.yml`) runs the
suite on Python 3.12 for every push and pull request, and builds the frontend.

Tests live in `backend/tests/`. Most build a "world" (`conftest.make_world`): a gateway, a
`paysim` simulator and a simulated clock sharing one SQLite database, so time-dependent behaviour
(settlement, absence window, review timeouts) is deterministic. `test_http_services.py` runs both
real FastAPI apps instead.

## Summary

| File | Tests | What it proves |
|---|---|---|
| `test_protocol_spec.py` | 11 | One test per row of the specification's required-behaviour table, plus the authorization-hold transfer case |
| `test_ablations.py` | 7 | Each ablation is a real code path that changes behaviour in the scenario it exists for |
| `test_concurrency_and_crash.py` | 6 | Concurrent agents, gateway crashes, attempt budget |
| `test_safety_properties.py` | 1 | Hypothesis property test over random faults, proposals, crashes and restarts (150 examples) |
| `test_components.py` | 14 | Money, simulator semantics, audit log, ticket extraction, state machine |
| `test_http_services.py` | 3 | End-to-end over HTTP through the gateway and provider APIs |
| **Total** | **42** | |

## Protocol specification (11)

| Test | Scenario → expected |
|---|---|
| `test_amount_exceeding_authorization_is_blocked` | Agent proposes more than authorized → `REJECTED`, nothing executes |
| `test_wrong_order_is_blocked` | Near-miss order → `REJECTED` |
| `test_confirmed_refund_is_verified_and_completed` | Clean refund → read back, `COMPLETED` |
| `test_timeout_marks_unknown_and_never_retries_blindly` | Timeout → `OUTCOME_UNKNOWN`; no retry before absence is confirmed |
| `test_lost_response_is_found_by_reconciliation_without_a_second_refund` | Lost response → reconciliation finds the refund; one effect |
| `test_restart_with_new_request_id_cannot_cause_a_second_effect` | Restarted agent, new request ID → no second effect |
| `test_incorrect_pending_refund_is_cancelled_and_verified` | Wrong amount, still pending → cancelled, cancellation verified |
| `test_incorrect_completed_refund_is_escalated_not_reported_reversed` | Wrong amount, completed → review case, never reported reversed |
| `test_authorization_hold_with_wrong_amount_is_voided_even_when_authorized` | Second transaction type: wrong hold is voided even after it is authorized |
| `test_revoked_operator_blocks_execution` | Operator deactivated after approval → `OPERATOR_NOT_PERMITTED` |
| `test_unresolvable_outcome_is_held_for_review` | Provider cannot be queried → held for review, not retried |

## Ablations (7)

Each test runs the full protocol and the ablated configuration side by side. Where one safeguard
is masked by another (defence in depth), the test shows that and then removes both.

| Test | Shows |
|---|---|
| `test_intent_binding_off_executes_hallucinated_amount` | Without binding, a ₹3,000 proposal against a ₹1,500 intent executes |
| `test_effect_dedup_off_approves_second_proposal_but_stable_key_masks_it` | Without the gate a second proposal is approved, but the stable key keeps one live refund; without both, two |
| `test_reconciliation_off_assumes_failure_after_lost_response` | Without reconciliation the gateway assumes failure and retries; the stable key replays the original and `attempt.absence_assumption_violated` is audited; without the key, two refunds |
| `test_absence_window_prevents_premature_retry_under_delayed_visibility[30.0-1]`, `[0.0-2]` | With the stable key removed and delayed visibility: window 30 s → one refund; window 0 → two, and the duplicate goes unnoticed |
| `test_state_aware_recovery_off_claims_reversal_that_never_happened` | Without verified recovery, a completed wrong refund is "cancelled" blindly and the intent reports `COMPLETED` while it stays live |
| `test_serialization_off_lets_concurrent_agents_both_pass_the_gate` | Deterministic two-agent race: serialized → one approval and one refund; unserialized (key also removed) → two of each |

## Concurrency and crashes (6)

| Test | Shows |
|---|---|
| `test_concurrent_agents_produce_exactly_one_effect[2]`, `[4]`, `[8]` | N threads submit for one intent at once → exactly one live effect |
| `test_gateway_crash_is_recovered_on_restart_with_one_effect[after_attempt_recorded]`, `[after_provider_response]` | Crash at either injection point: the attempt survives (`IN_FLIGHT`), a re-proposal gets `IN_PROGRESS`/`DUPLICATE`, restart recovery completes with one effect |
| `test_attempt_budget_exhaustion_escalates` | Permanent timeouts before execution → exactly `max_attempts` create calls, zero executions, `NEEDS_REVIEW` |

## Property-based safety (1)

`test_safety_properties_hold_under_arbitrary_faults` (Hypothesis, `max_examples=150`) generates
combinations of provider faults, correct and corrupted proposals, crashes, restarts and elapsed
time. After each run, against the provider's ground truth:

- **P1** at most one live effect matching an intent exists (unless escalated);
- **P2** no live effect exists that the protocol did not either intend or escalate;
- **P3** if the gateway reports `COMPLETED`, exactly the intended effect is live;
- **P4** the gateway never reports `COMPLETED` while an unintended effect is live and unflagged;
- **P5** the audit chain verifies and every intent state is one the state machine allows.

## Components (14)

| Test | Area |
|---|---|
| `test_money_round_trip_and_precision` | Minor-unit conversion; too much precision is rejected |
| `test_refund_settles_and_can_only_be_cancelled_while_pending` | Simulator refund semantics |
| `test_authorization_can_be_voided_after_completion` | Simulator hold semantics |
| `test_idempotency_replays_and_rejects_changed_parameters` | Key replay and fingerprint check |
| `test_balance_and_ownership_are_enforced_by_the_provider` | Provider balance and ownership checks |
| `test_lost_response_executes_and_delayed_visibility_hides_it_from_search` | Lost response and eventual consistency |
| `test_simulator_state_survives_restart` | Provider state persistence |
| `test_audit_log_is_append_only_and_tamper_evident` | `UPDATE`/`DELETE` refused; a rewrite after dropping the trigger is detected at the right `seq` |
| `test_extraction_never_confuses_ids_with_amounts` (4 cases) | `C-1712` or `ORD-204` is never parsed as an amount; ₹, INR, Rs., USD forms |
| `test_extraction_detects_authorization_and_rejects_incomplete_tickets` | Hold tickets map to `PAYMENT_AUTHORIZATION`; missing fields raise |
| `test_state_machine_rejects_illegal_transitions` | `check_transition` refuses transitions not in `TRANSITIONS` |

## HTTP end to end (3)

| Test | Shows |
|---|---|
| `test_end_to_end_lost_response_over_http` | Through both APIs (provider mounted via the real `HttpProvider`): a wrong proposal is rejected, a lost response is reconciled, one refund at the provider |
| `test_review_flow_over_http` | Completed wrong amount → `IRREVERSIBLE_DISCREPANCY` case → `MANUALLY_REMEDIATED` → retried with a fresh key → `COMPLETED`; the remediated refund stays in the provider's history |
| `test_unknown_intent_is_404_and_bad_authorization_is_422` | Error mapping |

## Gaps

- PostgreSQL is not exercised (row locks, the PL/pgSQL audit trigger, partial index syntax).
- The gateway's `BALANCE_EXCEEDED` check, `revoke`, and the `CONFIRMED_COMPLETED`,
  `CONFIRMED_NO_EFFECT` and `CLOSED_UNFULFILLED` resolutions have no dedicated tests.
- The LLM extractor (`agents/llm.py`) is not tested against a live model.
- The dashboard has no automated UI tests; CI only checks that it builds.
- No test runs two gateway processes against one database.
