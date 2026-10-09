# Data model

Target spec: [ARCHITECTURE.md §6 Data model (summary)](../ARCHITECTURE.md#6-data-model-summary). This page describes the code as built.

Source: [`backend/intentguard/models.py`](../../backend/intentguard/models.py) (SQLAlchemy 2.0),
`SCHEMA_VERSION = "2"`. The schema is created by `init_schema` in
[`backend/intentguard/db.py`](../../backend/intentguard/db.py) (`Base.metadata.create_all`; there
are no migrations, see [Schema version](#schema-version)). Timestamps are float epoch seconds: the
engine takes them from its injected clock, the API layer from wall-clock time. Money is stored as
integers in minor units (`amount_minor`, e.g. paise for INR); the API converts with
`backend/intentguard/money.py`.

Planned, not implemented: multi-tenancy (a `tenant_id` on every table with PostgreSQL row-level
security, [DECISIONS.md ADR-020](../DECISIONS.md#adr-020-multi-tenancy-via-tenant_id-and-postgresql-rls)).
No table has a tenant column today.

## Identifiers

| Record | Stored key | Shown by the API as |
|---|---|---|
| Intent | `INT-1001`, `INT-1002`, … (counter `intent`, starts at 1000) | same |
| Attempt | `ATT-001`, `ATT-002`, … (counter `attempt`, starts at 0, zero-padded to three digits) | same |
| Proposal, decision, effect, review case, webhook event, investigation, reconciliation run, mismatch | integer, autoincrement | `PRP-n`, `DEC-n`, `EFF-n`, `RC-n`, `WH-n`, `INV-n`, `RUN-n`, `MM-n` |

The counters live in the `counters` table; `engine._next_seq` locks the counter row
(`SELECT … FOR UPDATE`) and increments it. The API prefixes are added in
`backend/gateway_api/serializers.py`. The provider idempotency key `ig-<intent_id>-g<generation>` is
stored on each attempt and never returned by the API.

## Tables

There are 20 tables, grouped as in `models.py`.

### Principals

#### users

Operators, reviewers, admins and agent service principals.

| Column | Notes |
|---|---|
| `id` str(64) PK | e.g. `op-asha`, `agent-support` |
| `email` str(254), **unique**, nullable | Login name; null for agent principals |
| `name`, `role` | `role` is `operator`, `reviewer`, `admin` or `agent` |
| `password_hash` | argon2id; null for agent principals |
| `active` | Re-checked on every request, and on every proposal for the authorizing operator |
| `permitted_operations` JSON list, `limit_minor` | What this user may authorize: `REFUND`, `PAYMENT_AUTHORIZATION`; per-intent amount limit |
| `failed_logins`, `locked_until` | Login lockout |
| `created_at` | |

#### refresh_tokens

Opaque rotating refresh tokens. Only the SHA-256 of a token is stored (`token_hash`, **unique**). `user_id` (FK → users), `family_id` (indexed), `issued_at`, `expires_at`,
`absolute_expires_at`, `used_at` (set when the token is rotated), `revoked_at`, `user_agent`. Reusing a
rotated token revokes its whole family.

#### service_tokens

Issued agent JWTs, kept so they can be listed and revoked. `jti` PK, `user_id`
(FK → users, the agent principal), `scopes` JSON (e.g. `proposals:create:<intent_id>`,
`intents:read:<intent_id>`, or the same per customer),
`issued_by`, `issued_at`, `expires_at`, `revoked_at`. Every agent request checks that its `jti` exists
and is not revoked.

### Merchant data

#### orders

The merchant's own record of what was paid.

| Column | Notes |
|---|---|
| `id` str(64) PK | e.g. `ORD-204` |
| `customer_id` (indexed), `currency` | |
| `amount_minor` | Order value. `authorize` requires `0 < amount ≤ order value`; a proposal is rejected (`EXCEEDS_REMAINING_BALANCE`) if its amount plus the live, unremediated effects of the same operation on the order from other intents exceeds it |
| `created_at` | |

### The protocol

#### intents

One operator authorization and the intent it creates.

| Column | Notes |
|---|---|
| `id` str(64) PK | `INT-n` |
| `operator_id` | FK → users.id |
| `customer_id`, `order_id` (FK → orders.id), `operation`, `amount_minor`, `currency` | The authorized operation |
| `approval_status` | Always `APPROVED` as written by `authorize` |
| `state` (indexed) | See [state-machine.md](state-machine.md) |
| `ticket` text, nullable | Support ticket the agent endpoint reads |
| `metadata` JSON, nullable | Free-form, from `POST /api/authorizations` (attribute `metadata_`) |
| `attempt_count` | Attempts reserved so far (budget: `max_attempts`) |
| `key_generation` | `g<n>` in the provider idempotency key; incremented only after a verified reversal of an effect produced by one of the intent's attempts, or a `REFUND_RECOVERED_OUT_OF_BAND` resolution (and, under the state-aware-recovery ablation, after an unverified cancel) |
| `cancel_requested_at`, `cancel_requested_by` | Set by `engine.cancel`; cleared by an `ACCEPTED_AS_IS` resolution |
| `next_check_at` (index `ix_intents_due`) | When the worker should look at the intent next |
| `unknown_since` | Start of the current unknown-outcome period (for `unknown_review_after_s`) |
| `watch_until` | End of the post-completion watch for late-visible duplicates |
| `created_at`, `updated_at` | `updated_at` changes on every state change and drives polling back-off |

#### agent_proposals

Every proposal, including rejected ones.

| Column | Notes |
|---|---|
| `id` int PK | `PRP-n` |
| `intent_id` | FK → intents.id, indexed |
| `request_id`, `agent_id` | Supplied by the caller; never used as the provider key |
| `operation`, `customer_id`, `order_id`, `amount_minor`, `currency`, `rationale` | What was asked for (`order_id` is not a foreign key: a proposal may name any order) |
| `status` | `ProposalStatus`: `VALIDATED`, `REJECTED` or `BLOCKED` |
| `created_at` | |

#### gateway_decisions

The gateway's decision on one proposal, written in the same transaction.

| Column | Notes |
|---|---|
| `id` int PK | `DEC-n` |
| `proposal_id` | FK → agent_proposals.id, **unique**: one decision per proposal |
| `intent_id` | FK → intents.id, indexed |
| `decision` | `ALLOW`, `REJECT`, `DUPLICATE`, `HOLD_FOR_REVIEW` |
| `reasons` JSON list | Findings: `{check, detail, decision}` |
| `decided_at` | |

#### transaction_attempts

One provider call, written with status `SUBMITTING` *before* the call.

| Column | Notes |
|---|---|
| `id` str(64) PK | `ATT-nnn` |
| `intent_id` | FK → intents.id, indexed |
| `proposal_id` | FK → agent_proposals.id, nullable; a gateway retry reuses the previous attempt's proposal |
| `attempt_no` | Unique per intent (`uq_attempt_no`) |
| `idempotency_key` str(128) | `ig-<intent>-g<generation>` (or `ig-<intent>-a<n>` under the stable-key ablation) |
| `operation`, `order_id`, `customer_id`, `amount_minor`, `currency` | Parameters actually sent |
| `status` | `SUBMITTING`, `SUCCEEDED`, `UNKNOWN`, `RECONCILED`, `FAILED` ([state-machine.md](state-machine.md#related-status-sets)) |
| `provider_ref`, nullable | Provider transaction id once known |
| `error` text, nullable | |
| `incarnation` | Id of the gateway process that made the attempt (restart recovery) |
| `lease_expires_at` | A `SUBMITTING` attempt past its lease is treated as `UNKNOWN` |
| `created_at`, `updated_at`, `completed_at` | `created_at` is the reference point for the absence window; `completed_at` is set when the status leaves `SUBMITTING`/`UNKNOWN` |

#### effects

A transaction observed at the provider and attributed to an intent.

| Column | Notes |
|---|---|
| `id` int PK | `EFF-n` |
| `intent_id` | FK → intents.id, indexed |
| `attempt_id` | FK → transaction_attempts.id, nullable (set from the transaction's `attempt_id` metadata when that attempt exists) |
| `provider_ref` str(64), **unique** | One row per provider transaction |
| `operation`, `order_id` (indexed), `customer_id`, `amount_minor`, `currency` | As reported by the provider (the settled amount) |
| `provider_status` | `PENDING`, `COMPLETED`, `CANCELLED`, `FAILED` |
| `classification` | `INTENDED`, `DUPLICATE` or `MISMATCH` |
| `counts_toward_intent` | True only for a live, `INTENDED`, unremediated effect |
| `remediated` | Set by a `REFUND_RECOVERED_OUT_OF_BAND` resolution (or under the state-aware-recovery ablation) |
| `cancel_tries` | Cancellation tries without a usable answer; review `CANCEL_UNVERIFIED` at `max_cancel_tries` (3) |
| `note` text, nullable | |
| `observed_at`, `updated_at` | |

Classification (`engine._absorb`): an effect that differs from the intent in operation, order,
customer, amount or currency is `MISMATCH`. A matching effect is `DUPLICATE` if another effect already
counts toward the intent and this one is live; otherwise `INTENDED`. If the counted effect disappears
(for example it was cancelled), a live `DUPLICATE` is promoted to `INTENDED`.

#### review_cases

Cases a person must resolve, opened by the engine; see
[state-machine.md](state-machine.md#review-cases-and-resolutions).

| Column | Notes |
|---|---|
| `id` int PK | `RC-n` |
| `intent_id` | FK → intents.id, indexed |
| `reason` | `UNRESOLVABLE_OUTCOME`, `IRREVERSIBLE_DISCREPANCY`, `CANCEL_REJECTED`, `CANCEL_UNVERIFIED`, `ATTEMPT_BUDGET_EXHAUSTED`, `INVESTIGATOR_ESCALATION` |
| `discrepancy_minor` | Amount at stake: the full amount for a duplicate or for an effect on the wrong order, customer, currency or operation, else the amount difference (0 for cases not about a specific effect) |
| `details` JSON | |
| `status` (indexed) | `OPEN` / `RESOLVED` |
| `resolution`, `resolved_by`, `notes`, `resolved_at` | `ACCEPTED_AS_IS`, `REFUND_RECOVERED_OUT_OF_BAND`, `WRITTEN_OFF`, `CONFIRMED_NO_EFFECT`, `OTHER`; see [state-machine.md](state-machine.md#review-cases-and-resolutions) |
| `created_at` | |

### Recovery inputs

#### webhook_events

Signature-verified provider events. They are hints: the gateway re-fetches the transaction from the
provider ([reconciliation.md](reconciliation.md#provider-webhooks)).

| Column | Notes |
|---|---|
| `id` int PK | `WH-n` |
| `provider`, `event_id` | **Unique together** (`uq_webhook_event`): an event is stored once; a repeated delivery only increments `deliveries` |
| `type`, `object_id` (indexed) | e.g. `refund.completed`, the provider transaction id |
| `provider_created_at`, `sequence` | From the event; stored, not used for ordering |
| `payload` JSON | The event as received |
| `intent_id` (indexed), nullable | From the transaction's `metadata.intent_id` in the event; not a foreign key |
| `received_at`, `deliveries` | |
| `processed_at`, `outcome` | `absorbed`, `unknown_intent`, `unsupported_object`, `terminal_intent`, `terminal_intent_live_effect`, or `provider_unreachable: …` |

#### reconciliation_runs

`id` (`RUN-n`), `kind` (`WORKER` or `MATCHING`), `triggered_by` (`worker`
or the user id), `started_at`, `finished_at`, `examined`, `resolved`, `escalated`, `errors`,
`mismatches_found`. See [reconciliation.md](reconciliation.md#reconciliation-runs).

#### mismatches

Disagreements between the ledger and the provider, found by matching runs or by webhook processing.

| Column | Notes |
|---|---|
| `id` int PK | `MM-n` |
| `run_id` | FK → reconciliation_runs.id, nullable (null when found by a webhook), indexed |
| `kind` | `MISSING`, `DUPLICATE`, `AMOUNT`, `ORDER`, `CUSTOMER` |
| `status` (indexed) | `OPEN` / `RESOLVED` |
| `fingerprint` | e.g. `MISSING:<ref>`, `GONE:<ref>`, `LATE:<ref>`, `AMOUNT:<ref>`, `DUPLICATE:<intent>:<refs>`; no second `OPEN` mismatch with the same fingerprint is stored (checked by the application) |
| `intent_id` (indexed), `provider_ref`, `order_id` | Nullable references; not foreign keys |
| `details` JSON | Reason and compared values; resolving adds `resolved_by` and `note` |
| `detected_at`, `resolved_at` | |

#### investigations

One AI investigator run.

| Column | Notes |
|---|---|
| `id` int PK | `INV-n` |
| `intent_id` | FK → intents.id, indexed |
| `intent_state` | State when the investigation ran |
| `valid_output` | False when the classifier output was rejected |
| `classification`, `summary`, `evidence_refs` JSON, `recommended_action` | The advisory output |
| `policy_permitted`, `policy_rule` | The deterministic policy gate's verdict |
| `model`, `prompt`, `raw_output`, `tokens_in`, `tokens_out` | `offline-rules` or the LLM model name; prompt and raw output are kept for audit (truncated to 20,000 characters) |
| `created_by`, `created_at` | |
| `applied_at`, `applied_by`, `apply_outcome` | Set when a permitted recommendation is applied (`"<action> -> <state>"`) |

### Operations

#### policies

Admin-editable values: `key` PK, `value` JSON, `updated_by`, `updated_at`. Keys written by
`PUT /api/admin/policies`: `kill_switch`, `max_amount_minor` and `separation_of_duties` (read by the
engine; without a row: off, no limit, on), and `attempt_budget`, `absence_window_s` and
`unknown_review_after_s` (applied to `ProtocolConfig` at once and again at startup). Every change is
audited as `policy.updated`.

#### provider_configs

`name` PK (`paysim`), `base_url`, `timeout_s`, `webhook_secret` (write-only
through the API; when set it is used instead of `WEBHOOK_SECRET` to verify that provider's webhooks),
`updated_by`, `updated_at`. At startup, with `PAYMENT_PROVIDER=http`, a stored `paysim` row replaces
the configured provider URL and timeout.

#### api_idempotency

Stored responses for the client `Idempotency-Key` header. Primary key
(`principal`, `key`); `method`, `path`, `body_hash` (SHA-256 of path and body), `status_code`,
`response` JSON, `created_at`. A replay with the same key and body returns the stored response; the
same key with a different body is refused (422 `IDEMPOTENCY_KEY_REUSE`). This is separate from the
provider idempotency key.

#### counters

`name` PK, `value`. `intent` starts at 1000, `attempt` at 0.

#### schema_meta

`key` PK, `value`. Holds `schema_version` = `"2"`.

### Audit

#### audit_logs

| Column | Notes |
|---|---|
| `seq` int PK, autoincrement | Global order |
| `chain_id` (indexed) | The intent id, or `system` for events that belong to no intent |
| `intent_id`, nullable | Same as `chain_id` on intent chains; null on the `system` chain |
| `kind` | See below |
| `actor` | `gateway` for the engine's own steps; otherwise a user id, the proposal's `agent_id` (for `proposal.decided`), or a label such as `seed`, `bootstrap` or `anonymous` (failed login for an unknown email) |
| `payload` JSON | Stored exactly as hashed |
| `ts` | Event time (attribute `created_at`) |
| `prev_hash`, `hash` | SHA-256 chain |

Event kinds written by the code:

- Intent chains: `intent.authorized`, `intent.state`, `intent.cancel_requested`, `intent.cancelled`,
  `intent.recheck_scheduled`, `proposal.decided`, `attempt.reserved`, `attempt.result`,
  `attempt.lease_expired`, `attempt.orphaned`, `attempt.absence_confirmed`,
  `attempt.absence_assumption_violated`, `attempt.controlled_retry`, `effect.observed`,
  `effect.reversal_verified`, `effect.reversal_assumed` (ablation only), `reconcile.lookup_failed`,
  `review.opened`, `review.resolved`, `investigation.created`, `investigation.rejected_output`,
  `investigation.apply_refused`, `investigation.applied`, and `mismatch.resolved` when the mismatch
  names an intent.
- `system` chain: `operator.upserted`, `operator.active_changed`, `user.created`, `user.updated`,
  `service_token.issued`, `service_token.revoked`, `auth.login`, `auth.login_failed`,
  `auth.refresh_reuse_detected`, `policy.updated`, `provider.updated`, `order.upserted`,
  `reconciliation.run`, `mismatch.resolved` (no intent), `dev.fault_injected`, `dev.order_created`.

## Constraints enforced by the database

These hold even if application code is wrong:

| Guarantee | Mechanism |
|---|---|
| At most one effect counts toward an intent | Partial unique index `uq_one_live_intended_effect` on `effects(intent_id)` where `counts_toward_intent` (`counts_toward_intent = 1` on SQLite) |
| One effect row per provider transaction | `effects.provider_ref` is `UNIQUE` |
| Attempt numbers unique per intent | `UNIQUE (intent_id, attempt_no)` (`uq_attempt_no`) |
| One decision per proposal | `gateway_decisions.proposal_id` is `UNIQUE` |
| A webhook event is stored once | `UNIQUE (provider, event_id)` (`uq_webhook_event`); the duplicate insert fails and the receiver increments `deliveries` instead |
| One user per email; one row per refresh-token hash | `users.email` and `refresh_tokens.token_hash` are `UNIQUE` |
| One stored response per client idempotency key | Primary key `(principal, key)` on `api_idempotency` |
| Audit log is append-only | SQLite: triggers `audit_no_update` and `audit_no_delete` (`BEFORE UPDATE`/`BEFORE DELETE ON audit_logs … SELECT RAISE(ABORT, 'audit_logs is append-only')`). PostgreSQL: function `audit_logs_append_only()` (raises `audit_logs is append-only`) and trigger `audit_no_modify` (`BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW`) |
| An audit chain cannot fork | `UNIQUE (chain_id, prev_hash)` (`uq_audit_chain_link`) |
| Referential integrity | Foreign keys; SQLite connections run `PRAGMA foreign_keys=ON` |

The triggers are attached to the `after_create` event of the `audit_logs` table, so they are created
together with the table.

Enforced by the application, not the database: legal state transitions (`TRANSITIONS`, see
[state-machine.md](state-machine.md)), at most one open review case per intent and reason, and at
most one open mismatch per fingerprint.

Other indexes: `ix_intents_state`, `ix_intents_due` (`next_check_at`), `ix_orders_customer_id`,
`ix_effects_order_id`, `ix_review_cases_status`, `ix_mismatches_status`, `ix_mismatches_run_id`,
`ix_webhook_events_object_id`, `ix_webhook_events_intent_id`, `ix_audit_logs_chain_id`,
`ix_refresh_tokens_family_id`, and an `intent_id` or `user_id` index on each table that references
an intent or a user.

## Hash-chained audit log

[`backend/intentguard/audit.py`](../../backend/intentguard/audit.py). Each event's

```
hash = SHA-256(prev_hash + canonical JSON of {chain, kind, actor, payload, at})
```

where the JSON has sorted keys and compact separators, `at` is `repr()` of the timestamp, and
`prev_hash` is the previous event's hash in the same chain (64 zeros for the first). The payload is
stored as the JSON round-trip of what was hashed. `audit.verify` recomputes every chain in `seq` order
and returns the first broken link. `GET /api/audit/verify` (reviewer, admin) returns
`{valid, entries_checked, chains, first_break}`.

`test_audit_log_is_append_only_and_tamper_evident` (in `backend/tests/test_components.py`) checks
that `UPDATE` and `DELETE` are refused, and that a row rewritten after dropping the trigger
(`audit_no_modify` on PostgreSQL, `audit_no_update` on SQLite) is detected at the right `seq`.

## Schema version

`init_schema(engine)` (`backend/intentguard/db.py`), called by the gateway at startup:

1. If the database already has tables, it reads `schema_meta.schema_version` and raises
   `SchemaMismatch` if any table of the earlier schema exists (`operators`, `proposals`, `attempts`,
   `audit_events`) or if `intents` exists with a version other than `"2"`. The gateway then does not
   start. (If the error is raised during a request, the API maps it to HTTP 500 `SCHEMA_MISMATCH`.)
2. Otherwise it runs `create_all` (which creates only missing tables), writes `schema_version = "2"`
   if absent, and seeds the `intent` and `attempt` counters if absent.

`test_database_from_an_earlier_version_is_refused` covers step 1.

[`scripts/check_db.py`](../../scripts/check_db.py) runs from `scripts/start.bat` before the services
start. It reads `DATABASE_URL` (from the environment or `.env`; default
`sqlite:///./intentguard_gateway.db`, relative to `backend/`). For a SQLite file that the gateway
would refuse (same test as above), it renames the file and its `-wal`/`-shm` companions to
`<name>.schema-<old>-<timestamp>.bak`, together with the simulator's state file (`PAYSIM_STATE_PATH`,
default `paysim_state.json`), because the two stores describe the same payments and must start fresh
together. Nothing is deleted. PostgreSQL databases are left alone; the gateway reports them with
`SchemaMismatch`.

## Transactions and locking

`backend/intentguard/db.py`:

- **SQLite:** every transaction starts with `BEGIN IMMEDIATE` (takes the write lock up front), WAL
  journal for file databases, 60 s busy timeout, `foreign_keys=ON`. The benchmark uses shared-cache
  in-memory databases, where transactions are serialized with a process-local lock instead.
- **PostgreSQL:** each unit of work locks the intent row with `SELECT … FOR UPDATE`
  (`engine._locked`); counter rows are locked the same way.
- The serialization ablation (`serialize_intent=False`) splits the decision and the attempt
  reservation into two transactions.

PostgreSQL is used by `docker compose`, and CI runs the whole backend test suite against PostgreSQL 16
(`TEST_DATABASE_URL`, job "Backend tests (PostgreSQL)" in `.github/workflows/ci.yml`). Locally the
tests use SQLite unless `TEST_DATABASE_URL` is set.
