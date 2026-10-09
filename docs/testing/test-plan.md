# Test plan (as built)

This page lists the automated tests that exist today and what each one proves. The target test
plan is [../TEST_PLAN.md](../TEST_PLAN.md); the last section lists its items that have no test
yet.

```bash
cd backend && python -m pytest -q      # 127 tests, about 1.5 minutes (make test)
cd frontend && npm test                # 19 Vitest tests
```

PostgreSQL, the route contract check, lint and the benchmark gate:
[../operations/running.md](../operations/running.md#tests-and-checks).

## Test setup

Engine tests build a "world" (`backend/tests/conftest.py`, `make_world`): the engine, the
`paysim` simulator behind the in-process provider adapter, and a simulated clock, sharing one
database (SQLite in memory, a SQLite file where threads need one, or `TEST_DATABASE_URL`).
`World.settle()` advances simulated time and runs the worker whenever something is due, so
settlement, the absence window and review timeouts are deterministic.

HTTP tests use the fixtures in `backend/tests/api_support.py`. `api` runs the real gateway app
against the real provider app, reached through the real `HttpProvider` over an in-process
transport (no ports), with the provider's settle delay at 0. `api_inprocess` embeds the simulator
in the gateway, for tests that create provider transactions directly. Both seed the demo users,
set a 48-byte JWT secret and a webhook secret, raise the rate limits, keep argon2id at minimal
cost, and force `LLM_PROVIDER=offline`; LLM replies are mocked where a test needs them.

## Summary

| File | Tests | What it proves |
|---|---|---|
| `test_protocol_spec.py` | 11 | One test per row of the required-behaviour table, plus the authorization-hold transfer case |
| `test_ablations.py` | 7 | Each ablation is a real code path that changes behaviour in the scenario it exists for |
| `test_concurrency_and_crash.py` | 6 | Concurrent agents, gateway crashes, attempt budget |
| `test_safety_properties.py` | 1 | Hypothesis property test over random faults, proposals, crashes and restarts (150 examples) |
| `test_components.py` | 14 | Money, simulator semantics, audit log, ticket extraction, state machine |
| `test_engine_features.py` | 18 | Identifiers, operator cancel, kill switch and limits, remaining balance, separation of duties, review resolutions, schema versioning |
| `test_http_services.py` | 3 | End to end over HTTP through the gateway and provider apps |
| `test_api_auth.py` | 16 | Login, lockout, refresh rotation and reuse, cookie mode and CSRF, invalid tokens, session invalidation |
| `test_api_rbac.py` | 13 | Role matrix, scoped and revocable agent tokens, separation of duties over HTTP |
| `test_api_contract.py` | 11 | The REST contract of [../API.md](../API.md): envelope, decisions as 200, pagination, idempotency, identifiers |
| `test_api_operations.py` | 11 | Matching runs and mismatches, policies, LLM output validation, simulator mode, metrics, providers, demo orders |
| `test_investigator.py` | 10 | The AI investigator only recommends; the policy gate decides; invalid output is rejected |
| `test_webhooks.py` | 6 | Signed provider webhooks: verification, dedupe, ordering, unknown intents, delays |
| **Total** | **127** | |
| `frontend/src/domain.test.js`, `frontend/src/api/client.test.js` | 19 | State labels, pipeline, role gating, money; HTTP client auth and error handling |

## Protocol specification (11) — `test_protocol_spec.py`

| Test | Scenario → expected |
|---|---|
| `test_amount_exceeding_authorization_is_blocked` | ₹15,000 proposed against a ₹1,500 intent → `REJECT`, `AMOUNT_EXCEEDS_AUTHORIZATION`; no provider transaction |
| `test_wrong_order_is_blocked` | Near-miss `ORD-240` → `REJECT`, `ORDER_MISMATCH`; no provider transaction |
| `test_confirmed_refund_is_verified_and_completed` | Clean refund → `ALLOW`, `COMPLETED`; the effect is `INTENDED` and `COMPLETED`; one live transaction |
| `test_timeout_marks_unknown_and_never_retries_blindly` | `TIMEOUT_BEFORE_EXECUTION` → `UNKNOWN` after one create call; after the absence window, absence is proven and one controlled retry completes; one live refund |
| `test_lost_response_is_found_by_reconciliation_without_a_second_refund` | `TIMEOUT_AFTER_EXECUTION` → found by the inline reconciliation, `COMPLETED`; one execution |
| `test_restart_with_new_request_id_cannot_cause_a_second_effect` | Lost response hidden from search for 20 s, gateway restart, re-proposal with a new request id → `DUPLICATE`; one live refund; `COMPLETED` |
| `test_incorrect_pending_refund_is_cancelled_and_verified` | Wrong amount (×10) while still pending → the wrong refund is cancelled and verified, the correct ₹1,500 completes; intent `COMPLETED` |
| `test_incorrect_completed_refund_is_escalated_not_reported_reversed` | Wrong amount (×10), settled at once → `ESCALATED`, case `IRREVERSIBLE_DISCREPANCY` with ₹13,500 at stake; the wrong refund stays `COMPLETED` at the provider |
| `test_authorization_hold_with_wrong_amount_is_voided_even_when_authorized` | Second transaction type: a hold with the wrong amount (×1.5) is voided although it already completed; the correct hold completes |
| `test_revoked_operator_blocks_execution` | Operator deactivated after authorizing → `REJECT`, `OPERATOR_NOT_PERMITTED` |
| `test_unresolvable_outcome_is_held_for_review` | Lost response and the provider can never be queried → `ESCALATED`; the attempt stays `UNKNOWN` (never declared success or failure) |

## Ablations (7) — `test_ablations.py`

Each test runs the full protocol and the ablated configuration side by side. Where one safeguard
is masked by another (defence in depth), the test shows that and then removes both. Partial
refunds keep the provider's own balance check from masking a duplicate.

| Test | Shows |
|---|---|
| `test_intent_binding_off_executes_hallucinated_amount` | Without intent binding, a ₹3,000 proposal against a ₹1,500 intent executes; with it, it does not |
| `test_effect_dedup_off_approves_second_proposal_but_stable_key_masks_it` | Without the dedup gate a second proposal is `ALLOW`, but the stable key keeps one live refund; without both, two |
| `test_reconciliation_off_assumes_failure_after_lost_response` | Without reconciliation the gateway assumes no effect and retries; the stable key replays the original and `attempt.absence_assumption_violated` is audited; without the key, two refunds |
| `test_absence_window_prevents_premature_retry_under_delayed_visibility[30.0-1]`, `[0.0-2]` | Stable key removed, lost response hidden for 20 s: window 30 s → one refund; window 0 → two, and the intent still reports `COMPLETED` (the duplicate goes unnoticed) |
| `test_state_aware_recovery_off_claims_reversal_that_never_happened` | Without verified recovery, a completed wrong refund is "cancelled" blindly and the intent reports `COMPLETED` while both refunds stay completed at the provider |
| `test_serialization_off_lets_concurrent_agents_both_pass_the_gate` | Deterministic two-agent race with the key removed: serialized → one `ALLOW`, one refund. Unserialized on SQLite → two of each; on PostgreSQL the `(intent_id, attempt_no)` unique constraint rejects the second reservation (one refund, one error) |

## Concurrency and crashes (6) — `test_concurrency_and_crash.py`

| Test | Shows |
|---|---|
| `test_concurrent_agents_produce_exactly_one_effect[2]`, `[4]`, `[8]` | N threads submit for one intent at once (file database, overlapping provider calls) → exactly one `ALLOW`, the rest `DUPLICATE`; one live effect, one execution |
| `test_gateway_crash_is_recovered_on_restart_with_one_effect[after_attempt_recorded]`, `[after_provider_response]` | Crash at either point: the attempt survives (`IN_FLIGHT`); after restart a re-proposal is `DUPLICATE` and the intent completes with one live effect |
| `test_attempt_budget_exhaustion_escalates` | Permanent timeouts before execution → exactly `max_attempts` (3) create calls, zero executions, `ESCALATED` |

## Property-based safety (1) — `test_safety_properties.py`

`test_safety_properties_hold_under_arbitrary_faults` (Hypothesis, `max_examples=150`) generates up
to four faults (each firing 1–3 times) from `OUTAGE`, `TIMEOUT_BEFORE_EXECUTION`,
`TIMEOUT_AFTER_EXECUTION`, `DELAYED_STATUS`, `DELAYED_VISIBILITY` (25 s, and 120 s, which violates
the absence-window assumption), `CORRUPT_AMOUNT`, `FAILED_CANCELLATION` and `LOOKUP_OUTAGE`; one to
eight actions (correct proposals, proposals with the amount ×10, a near-miss order or another
customer, waits, restarts); an optional crash at either crash point; a partial or full refund. After
20 minutes of simulated settling, against the provider's ground truth:

- **P1** at most one live effect matching the intent exists, unless a review case was opened;
- **P2** no unintended live effect exists unless a review case was opened;
- **P3** if the gateway reports `COMPLETED`, exactly the intended effect is live;
- **P4** the gateway never reports `COMPLETED` while an unintended effect is live;
- **P5** the audit chain verifies and the final intent state is one of the state machine's states.

## Components (14) — `test_components.py`

| Test | Area |
|---|---|
| `test_money_round_trip_and_precision` | Minor-unit conversion; too much precision (`1.005` INR) is rejected |
| `test_refund_settles_and_can_only_be_cancelled_while_pending` | Simulator refund semantics |
| `test_authorization_can_be_voided_after_completion` | Simulator hold semantics |
| `test_idempotency_replays_and_rejects_changed_parameters` | Key replay; `idempotency_key_reuse` for changed parameters |
| `test_balance_and_ownership_are_enforced_by_the_provider` | Provider customer ownership and `insufficient_balance` |
| `test_lost_response_executes_and_delayed_visibility_hides_it_from_search` | Lost response and eventual consistency of search |
| `test_simulator_state_survives_restart` | Provider state and idempotency keys persist |
| `test_audit_log_is_append_only_and_tamper_evident` | `UPDATE`/`DELETE` on `audit_logs` are refused by the database; a rewrite after dropping the trigger is detected at the right `seq` (SQLite and PostgreSQL triggers) |
| `test_extraction_never_confuses_ids_with_amounts` (4 cases) | `C-1712` or `ORD-204` is never parsed as an amount; ₹, INR, Rs. and USD forms |
| `test_extraction_detects_authorization_and_rejects_incomplete_tickets` | Hold tickets map to `PAYMENT_AUTHORIZATION`; a ticket without order and customer raises |
| `test_state_machine_rejects_illegal_transitions` | `check_transition` accepts `AUTHORIZED → IN_FLIGHT` and refuses `COMPLETED → IN_FLIGHT` and `CANCELLED → AUTHORIZED` |

## Engine features (18) — `test_engine_features.py`

| Test | Shows |
|---|---|
| `test_intents_attempts_and_decisions_use_readable_ids_and_separate_records` | `INT-1001`, `ATT-001`; the proposal row is `VALIDATED` with a separate `ALLOW` decision row; a smaller amount gives `REJECTED` with `AMOUNT_BELOW_AUTHORIZATION` |
| `test_cancel_without_effect_is_immediate` | Cancelling an `AUTHORIZED` intent → `CANCELLED`; a later proposal → `REJECT`, `INTENT_NOT_ACTIVE`; no provider call |
| `test_cancel_of_pending_refund_is_verified_at_the_provider` | Cancel while the refund is pending → cancelled at the provider and verified; `CANCELLED`, nothing live |
| `test_completed_refund_cannot_be_cancelled` | `NOT_CANCELLABLE`; the intent stays `COMPLETED` and the refund live |
| `test_completed_authorization_hold_can_be_voided` | Cancelling a completed hold voids it → `CANCELLED` |
| `test_failed_cancellation_escalates_and_can_be_written_off` | The provider refuses the cancel → `ESCALATED` with `CANCEL_REJECTED`; `WRITTEN_OFF` → `CLOSED` |
| `test_cancel_refused_while_outcome_unknown` | Cancelling an `UNKNOWN` intent → `ATTEMPT_IN_PROGRESS` |
| `test_kill_switch_holds_every_new_proposal_without_provider_calls` | Kill switch on → `HOLD_FOR_REVIEW` with `KILL_SWITCH`, zero create calls, intent stays `AUTHORIZED`; off → `ALLOW` |
| `test_policy_amount_limit_applies_to_new_and_existing_intents` | With a ₹1,000 limit a ₹1,200 authorization is refused and a proposal for an existing ₹1,500 intent is `REJECT`, both `POLICY_LIMIT_EXCEEDED`; no transaction |
| `test_remaining_order_balance_is_enforced_by_the_gateway` | ₹4,000 refunded on a ₹5,000 order; another intent's ₹1,500 → `REJECT` with only `EXCEEDS_REMAINING_BALANCE`; one create call in total |
| `test_separation_of_duties_blocks_the_authorizing_operator` | The authorizing operator cannot resolve the case (`SEPARATION_OF_DUTIES`); with the policy off, they can |
| `test_accepted_as_is_requires_a_verified_effect` | An escalated lost response with no visible effect → `ACCEPTED_AS_IS` refused with `NO_VERIFIED_EFFECT` |
| `test_accepted_as_is_keeps_a_refund_whose_cancellation_failed` | A pending intended refund whose cancel failed → `ACCEPTED_AS_IS` → `EXECUTING`, then `COMPLETED` with one live refund |
| `test_confirmed_no_effect_allows_a_controlled_retry` | Timeout before execution and an unreachable provider → escalated; `CONFIRMED_NO_EFFECT` → controlled retry → `COMPLETED`; two attempts, one live refund |
| `test_other_resolution_reescalates_while_the_provider_is_unreachable` | `OTHER` while the provider still cannot be queried → a new `UNRESOLVABLE_OUTCOME` case |
| `test_other_resolution_reconciles_once_the_provider_answers` | `OTHER` once the provider is back → the lost refund is found, `COMPLETED`, one live refund |
| `test_database_from_an_earlier_version_is_refused` | A database with a table of the old schema → `SchemaMismatch` |
| `test_proposal_rows_never_store_the_effect_when_rejected` | A rejected proposal leaves no effect row |

## HTTP end to end (3) — `test_http_services.py`

| Test | Shows |
|---|---|
| `test_end_to_end_lost_response_over_http` | A ₹15,000 proposal is an HTTP 200 `REJECT`; the agent endpoint (offline rules) is `ALLOW`; the lost response is reconciled; `COMPLETED`, verified, one `INTENDED` effect, one refund in the provider ledger |
| `test_review_flow_over_http` | Completed wrong amount (×2) → `ESCALATED`, case `IRREVERSIBLE_DISCREPANCY` (`RC-…`, ₹1,500.00 at stake); an operator's resolve is 403; the reviewer's `REFUND_RECOVERED_OUT_OF_BAND` → retry with a fresh key → `COMPLETED`; the remediated refund stays in the provider's history |
| `test_unknown_intent_is_404_and_bad_authorization_is_422` | Unknown intent → 404 `NOT_FOUND`; Ravi authorizing ₹6,000 over his ₹5,000 limit → 422 `OPERATOR_LIMIT_EXCEEDED`; the envelope carries a `req_…` request id |

## Authentication (16) — `test_api_auth.py`

| Test | Shows |
|---|---|
| `test_login_returns_tokens_and_wrong_password_is_generic` | A 900 s bearer token and an HttpOnly, `SameSite=Strict` `ig_refresh` cookie; a wrong password and an unknown email give the same 401 `INVALID_CREDENTIALS` |
| `test_browser_cookie_mode_keeps_the_refresh_token_out_of_the_body` | With the CSRF header (browser mode) login and refresh return no `refresh_token` in the body, only the cookie; an API client gets it in the body |
| `test_repeated_failures_lock_the_account` | Five failures → 429 `ACCOUNT_LOCKED` with `Retry-After`, even with the right password |
| `test_refresh_rotates_and_reuse_revokes_the_family` | Refresh returns a new token; reusing the old one → 401 `REFRESH_TOKEN_REUSED`, and the whole family, including the newest token, is revoked |
| `test_cookie_refresh_needs_the_csrf_header_and_logout_revokes` | Cookie refresh without `X-IntentGuard-CSRF` → `CSRF_REQUIRED`; with it → 200; logout (204) revokes the family |
| `test_invalid_access_tokens_are_rejected` (8 cases) | Expired, wrong audience, wrong issuer, `alg: none`, HS512, tampered payload, missing `jti`, garbage → 401 `INVALID_TOKEN` or `TOKEN_EXPIRED` |
| `test_role_change_and_deactivation_end_existing_sessions` | After an admin changes a user's role or deactivates them, their existing access token gets 401 |
| `test_passwords_must_be_long_enough` | A short password → 422 `WEAK_PASSWORD` |
| `test_unauthenticated_requests_are_401` | No token → 401 `UNAUTHENTICATED`; `/api/health` needs none |

## Roles and scopes (13) — `test_api_rbac.py`

| Test | Shows |
|---|---|
| `test_role_matrix` (8 cases) | An operator gets 403 `FORBIDDEN` for resolving a case, verifying the audit chain, listing users and running matching; a reviewer may verify and run matching but not read policies; an admin may read policies |
| `test_agent_token_is_scoped_to_its_intent` | The token lifetime is capped at 300 s; `ALLOW` on its own intent; 403 for proposing on or reading another intent; the intent list shows only its intent; authorizations, cancel, investigate and `/api/dev/ledger` are 403 |
| `test_revoked_agent_token_stops_working` | After `DELETE /api/admin/service-tokens/{jti}` the token gets 401 |
| `test_customer_scoped_agent_token` | A token scoped to customer C-17 reads C-17's intent but not C-71's |
| `test_agents_cannot_log_in_and_must_be_scoped` | Issuing a service token without a scope, or for a human user with an empty scope, → 422 |
| `test_separation_of_duties_over_http` | A reviewer who authorized an intent gets 403 `SEPARATION_OF_DUTIES` on its case; the admin's `WRITTEN_OFF` → `CLOSED` |

## API contract (11) — `test_api_contract.py`

| Test | Shows |
|---|---|
| `test_every_documented_endpoint_exists_in_the_openapi_schema` | Every method and path listed from [../API.md](../API.md) exists in the app's OpenAPI schema |
| `test_error_envelope` | Errors have exactly `code`, `message`, `details`, `request_id`; a client `X-Request-ID` is echoed in the body and the header |
| `test_malformed_json_is_400_and_unknown_fields_are_422` | Bad JSON → 400 `MALFORMED_REQUEST`; an unknown field → 422 `VALIDATION_ERROR`; a negative amount → 422 |
| `test_decisions_are_http_200_with_reason_codes` | `ORDER_MISMATCH`, `CUSTOMER_MISMATCH` and `AMOUNT_BELOW_AUTHORIZATION` rejections, then `ALLOW`, then `DUPLICATE`/`ALREADY_COMPLETED`, all HTTP 200 with `PRP-` ids |
| `test_pagination_cursor` | Pages of two return all five intents newest first with nothing skipped or repeated; `limit=500` → 422; a bad cursor → 400 |
| `test_idempotency_key_replays_the_original_response` | The same `Idempotency-Key` and body replays the 201 response (`Idempotent-Replay: true`, one intent); the same key with another body → 422 `IDEMPOTENCY_KEY_REUSE` |
| `test_provider_idempotency_key_is_never_exposed` | Intent, history, timeline and audit responses never contain `ig-<intent>`; the audit payload shows `[redacted]` |
| `test_timestamps_are_iso8601_and_ids_are_prefixed` | `INT-`, `ATT-001`, `EFF-` ids; millisecond UTC ISO-8601 timestamps; decimal-string amounts |
| `test_unknown_states_are_never_reported_as_failed` | A lost response with the provider unreachable → `ALLOW`, state `UNKNOWN`, `verified: false`, and no `FAILED` anywhere in the body |
| `test_security_headers` | `nosniff` and a `default-src 'none'` Content-Security-Policy on API responses |
| `test_simulator_ledger_never_exposes_the_provider_idempotency_key` | The simulator-only `/api/dev/ledger` redacts the provider idempotency key too |

## Operational endpoints (11) — `test_api_operations.py`

| Test | Shows |
|---|---|
| `test_matching_run_reports_mismatches_without_changing_anything` | A matching run finds a wrong-amount effect (`AMOUNT`) and a refund no intent accounts for (`MISSING`); no intent state changes; a second run adds nothing; an operator cannot mark a mismatch handled (403), a reviewer can |
| `test_matching_run_detects_a_duplicate_left_by_an_ablated_gateway` | With dedup and the stable key switched off, two refunds for one intent → a `DUPLICATE` mismatch |
| `test_kill_switch_and_policy_limit_through_the_api` | `PUT /api/admin/policies`: the kill switch holds a proposal (`KILL_SWITCH`, empty provider ledger); a maximum amount refuses an authorization (`POLICY_LIMIT_EXCEEDED`); clearing it and changing the attempt budget; every change audited as `policy.updated` |
| `test_malformed_llm_output_is_rejected_not_repaired` | An LLM reply with missing fields → 422 `INVALID_AGENT_OUTPUT`, and no proposal is recorded |
| `test_simulator_endpoints_disappear_when_simulator_mode_is_off` | `/api/dev/faults` works with `SIMULATOR_MODE` and is 404 without |
| `test_provider_fault_endpoint_needs_simulator_mode` | The provider's `/v1/faults` is 404 with `SIMULATOR_MODE=false`; `/health` reports it |
| `test_metrics_summary` | Totals, completed, blocked, duplicates suppressed, human-intervention rate and median time to verified; an unknown window → 422 |
| `test_provider_config_secret_is_write_only_and_orders` | A provider webhook secret can be set but is never returned; the four seeded orders are listed; `/api/ready` is ready |
| `test_demo_order_is_registered_on_both_sides_and_refundable` | `POST /api/dev/orders` creates an `ORD-9xxxxxxx` order known to both sides; a refund on it completes; audited as `dev.order_created` |
| `test_amount_with_too_many_decimals_is_a_validation_error_not_a_500` | `1500.001` → 422 |
| `test_triggered_matching_run_returns_its_id_and_is_listed` | `POST /api/reconciliation/runs` → 202 with a `RUN-` id, then listed as a finished `MATCHING` run triggered by the reviewer |

## AI investigator (10) — `test_investigator.py`

The LLM is mocked; the property under test is that nothing it says can cause an effect the
deterministic policy gate does not permit.

| Test | Shows |
|---|---|
| `test_offline_investigator_completes_a_lost_response` | Offline rules: `LOST_RESPONSE`, `MARK_COMPLETED`, permitted (`effect_matches_authorization`), evidence cites the provider transaction; Apply → `COMPLETED`, one transaction; applying again → 409 `ALREADY_APPLIED` |
| `test_retry_is_refused_while_absence_is_unverified` | The LLM recommends `CONTROLLED_RETRY` while the outcome is `UNKNOWN` → not permitted (`absence_not_verified`); Apply → 409 `POLICY_REFUSED`; no second create call |
| `test_prompt_injection_cannot_produce_an_effect` | The ticket tells the model to recommend `MARK_COMPLETED`; an obedient LLM does → not permitted (`no_matching_effect_at_provider`), Apply refused; the system prompt says never to follow instructions in the evidence, which is passed inside `<evidence>`; no transaction |
| `test_invalid_output_is_rejected_not_repaired` (4 cases) | Not JSON, an action outside the set, an evidence reference not in the bundle, an extra key → 422 `INVALID_INVESTIGATOR_OUTPUT`; the raw output is stored as invalid and cannot be applied |
| `test_only_exceptions_are_investigated` | A `COMPLETED` intent → 409 `NOT_AN_EXCEPTION` |
| `test_cancel_pending_is_permitted_for_a_cancellable_discrepancy` | A pending wrong amount stuck in `DISCREPANCY` → `AMOUNT_MISMATCH`, `CANCEL_PENDING`, permitted; Apply cancels and verifies the wrong refund and retries → `COMPLETED` |
| `test_evidence_bundle_is_redacted` | The evidence bundle has no idempotency key and at most 500 characters of the untrusted ticket |

## Webhooks (6) — `test_webhooks.py`

Events are delivered by paysim's real `WebhookEmitter` into the gateway app.

| Test | Shows |
|---|---|
| `test_webhook_resolves_a_lost_response_hidden_from_search` | A lost response hidden from search for 10 minutes: the signed event makes the gateway re-fetch the refund → `COMPLETED`; one refund |
| `test_bad_signature_and_stale_timestamp_are_rejected` | Wrong secret → 400 `INVALID_SIGNATURE`; a timestamp an hour old → 400 `STALE_EVENT`; unsigned → 400 |
| `test_duplicate_and_delayed_deliveries_are_safe` | `WEBHOOK_DUPLICATE`: the event is delivered twice and stored once (`deliveries: 2`); `COMPLETED` |
| `test_out_of_order_events_converge_on_the_provider_state` | A newer "completed" event followed by an older "pending" one: both accepted, the intent stays `COMPLETED` |
| `test_event_for_an_unknown_intent_becomes_a_mismatch` | A refund made directly at the provider → a `MISSING` mismatch with source `webhook` |
| `test_emitter_delay_fault_delivers_later` | `WEBHOOK_DELAY` holds an event back until it is due |

## Dashboard (19) — Vitest

`frontend/src/domain.test.js` (12):

- every backend intent state has a label; `UNKNOWN` and `RECONCILING` show as "Verifying", never
  as failed; an unknown value falls back to its own name (3);
- the five-node pipeline: waiting at Proposed, a rejected proposal blocked before execution, an
  unknown outcome as a verifying node, completed and escalated outcomes, a reviewer-closed intent
  and automatic recovery (`CANCEL_REQUESTED`, `DISCREPANCY`) shown apart from escalation, a later
  allowed proposal ahead of an earlier rejection (6);
- role gating mirrors the server: operators cannot resolve reviews, verify the audit chain or
  administer; reviewers resolve, admins administer, agents get nothing (2);
- money formatting (1).

`frontend/src/api/client.test.js` (7): the error envelope maps to `ApiError`; requests send the
bearer token and the `Idempotency-Key`; a 401 triggers one refresh with the CSRF header and a retry
with the new token; a failed refresh signals auth loss; login and refresh declare cookie mode so the
refresh token stays out of the body; a `REJECT` decision is data, not an error; a network failure is
an `ApiError` with status 0.

## Route contract check

Code, committed schema and dashboard are kept in step:

- `python scripts/export_openapi.py --check` (CI backend job) fails when `docs/api/openapi.json`
  differs from the schema the gateway app generates;
- `npm run check:contract` (`frontend/scripts/check-contract.mjs`) fails when any of the 45 routes
  in `frontend/src/api/endpoints.js` is missing from that schema or has another method;
- `test_every_documented_endpoint_exists_in_the_openapi_schema` checks the paths listed from
  `docs/API.md` against the app.

## PostgreSQL run

With `TEST_DATABASE_URL` set, every backend test runs against PostgreSQL instead of SQLite; the
`public` schema is dropped and recreated for each test, so the database name must contain `test`.
CI's "Backend tests (PostgreSQL)" job runs the whole suite on PostgreSQL 16. This exercises the
row locks, the partial unique index on `effects`, the `audit_no_modify` trigger
(`test_audit_log_is_append_only_and_tamper_evident` drops it to simulate tampering) and the
`(intent_id, attempt_no)` constraint that stops the unserialized race in
`test_serialization_off_lets_concurrent_agents_both_pass_the_gate`.

## Benchmark safety gate

CI runs a quick benchmark (15 arms, 2 seeds, 60 scenarios per seed) and then
`scripts/check_bench_safety.py`, which fails unless the full protocol (`E_intentguard`) has zero
`duplicate_effects`, zero `undetected_wrong_minor` and zero `misreports` in every seed. Everything
else in the summary (completion, latency, review counts) is a measurement, not a pass/fail
property. Measured results: [../research/results.md](../research/results.md).

## Target items without a test yet

Against [../TEST_PLAN.md](../TEST_PLAN.md):

| Target section | Not covered today |
|---|---|
| 3. Unit and state machine | No exhaustive test of the transition table (three transitions are spot-checked; P5 checks the final state only). `CLOSED` is never checked as terminal. The target lists `COMPLETED` as terminal; in the code it is not (a late duplicate or mismatch reopens it, and a completed hold can be voided). No pure-function tests of `checks.evaluate`; `OPERATION_MISMATCH` and `CURRENCY_MISMATCH` have no test at all. No direct test of key derivation, of table-driven state derivation, of a removed or reordered audit entry, or of zero and NaN amounts |
| 4. Behaviour table | Row 5 (wrong currency): no test. Row 10: only a wrong amount is tested; the simulator has no fault that produces a wrong order. Row 13 (delayed status): covered only indirectly (a delayed refund settles in `test_accepted_as_is_keeps_a_refund_whose_cancellation_failed`, and in the property test). Row 15: the crash test asserts the end state, not the intermediate absence and retry. Rows 10 and 19: the code reaches `ESCALATED` with a review case, which is what the tests assert |
| 5. Ablations | "No intent binding" is tested with a wrong amount, not a mutated order. There is no separate state-machine switch: turning off `effect_dedup` also makes transitions permissive, and no test shows an illegal transition accepted. The `readback_verification` switch has no test |
| 6. Concurrency and crash | No 32-agent or nightly run; no test that no lock is held across a provider call |
| 7. Property-based | Not asserted: "`UNKNOWN` never triggers an uncontrolled immediate retry" (covered by example tests only) and "the audit chain contains every state change". Under provider faults an unintended effect can exist, so the test asserts that it is escalated rather than that it never exists. No extended nightly run |
| 8. AI agent and investigator | No test of prompt injection inside a provider response or webhook payload, of an ambiguous ticket over the API (`422 EXTRACTION_FAILED`), of the `WAIT_AND_RECHECK` or `ESCALATE` actions being applied, or against a live LLM (no `live_llm` marker). Investigator evaluation metrics are not implemented |
| 9. API and contract | The OpenAPI check compares paths, not request and response schemas; the frontend client is a checked route table, not generated from the schema. No test of the intent list filters or of tolerance to unknown response fields |
| 10. Security | No test of `429 RATE_LIMITED`. Cross-tenant and row-level security tests do not apply: multi-tenancy is not built |
| 11. Webhooks and reconciliation | No test of a webhook arriving while the create call is still in flight, of delays beyond a fraction of a second, or of `ORDER` and `CUSTOMER` mismatches in a matching run |
| 12. Benchmark | CI does not check that two runs with the same seeds give identical `scenarios.csv` |
| 13. Frontend | No component, accessibility (axe), reduced-motion, keyboard or Playwright tests; the demo cards and the review flow are not tested in a browser |
| 14. CI | No mypy, eslint or tsc stage; no nightly jobs; no provider sandbox tests (no real provider adapter exists) |

Also untested: the `CANCEL_UNVERIFIED` review reason, `POST /api/admin/orders`, and two gateway
processes sharing one database.
