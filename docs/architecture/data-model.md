# Data model

Source: [`backend/intentguard/models.py`](../../backend/intentguard/models.py) (SQLAlchemy 2.0),
schema created by `init_schema` (`Base.metadata.create_all`; there are no migrations).
Timestamps are float epoch seconds from the injected clock. Money is stored as integers in minor
units (`amount_minor`, e.g. paise for INR), and the API converts with `intentguard/money.py`.

## Tables

### operators

| Column | Type | Notes |
|---|---|---|
| `id` | str(64) PK | e.g. `op-asha` |
| `name` | str(128) | |
| `active` | bool | Re-checked on every proposal |
| `permitted_operations` | JSON list | `REFUND`, `PAYMENT_AUTHORIZATION` |
| `limit_minor` | bigint | Per-intent authorization limit |
| `created_at` | float | |

### orders

The merchant's own record of what was paid.

| Column | Type | Notes |
|---|---|---|
| `id` | str(64) PK | e.g. `ORD-204` |
| `customer_id` | str(64), indexed | |
| `currency` | str(3) | |
| `amount_minor` | bigint | Order value; upper bound for live effects of one operation across all intents |
| `created_at` | float | |

### intents

| Column | Type | Notes |
|---|---|---|
| `id` | str(64) PK | `int_<16 hex>` |
| `operator_id` | FK → operators.id | |
| `customer_id`, `order_id` (FK → orders.id), `operation`, `amount_minor`, `currency` | | The authorized operation |
| `state` | str(32), indexed | See [state-machine.md](state-machine.md) |
| `ticket` | text, nullable | Support ticket the agent endpoint reads |
| `attempt_count` | int | Attempts reserved so far (budget: `max_attempts`) |
| `key_generation` | int | `g<n>` in the idempotency key; bumped only after a verified reversal or a manual remediation |
| `next_check_at` | float, nullable | When the worker should look at the intent next (index `ix_intents_due`) |
| `unknown_since` | float, nullable | Start of the current unknown-outcome period (for `unknown_review_after_s`) |
| `watch_until` | float, nullable | End of the post-completion watch for late-visible duplicates |
| `created_at`, `updated_at` | float | `updated_at` changes on every state change and drives polling back-off |

### proposals

Every agent proposal and the gateway's decision, including rejected ones.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK, autoincrement | |
| `intent_id` | FK → intents.id, indexed | |
| `request_id`, `agent_id` | str(64) | Agent-supplied; not used as the provider key |
| `operation`, `customer_id`, `order_id`, `amount_minor`, `currency`, `rationale` | | What the agent asked for |
| `decision` | str(16) | `APPROVED`, `REJECTED`, `DUPLICATE`, `IN_PROGRESS`, `HELD` |
| `reasons` | JSON list | Findings: `{check, detail, decision}` |
| `created_at` | float | |

### attempts

One provider call. Written with status `SUBMITTING` *before* the call.

| Column | Type | Notes |
|---|---|---|
| `id` | str(64) PK | `att_<16 hex>` |
| `intent_id` | FK → intents.id, indexed | |
| `proposal_id` | FK → proposals.id, nullable | |
| `attempt_no` | int | Unique per intent (`uq_attempt_no`) |
| `idempotency_key` | str(128) | `ig-<intent>-g<generation>` (or `ig-<intent>-a<n>` under the stable-key ablation) |
| `operation`, `order_id`, `customer_id`, `amount_minor`, `currency` | | Parameters actually sent |
| `status` | str(16) | `SUBMITTING`, `ACKNOWLEDGED`, `UNKNOWN`, `NO_EFFECT`, `REJECTED` |
| `provider_ref` | str(64), nullable | Provider transaction id once known |
| `error` | text, nullable | |
| `incarnation` | str(64) | Id of the gateway process that made the attempt (crash recovery) |
| `lease_expires_at` | float | A `SUBMITTING` attempt past its lease is treated as `UNKNOWN` |
| `created_at`, `updated_at` | float | `created_at` is the reference point for the absence window |

### effects

A transaction observed at the provider and attributed to an intent.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `intent_id` | FK → intents.id, indexed | |
| `attempt_id` | FK → attempts.id, nullable | |
| `provider_ref` | str(64), **unique** | One row per provider transaction |
| `operation`, `order_id` (indexed), `customer_id`, `amount_minor`, `currency` | | As reported by the provider (the settled amount) |
| `provider_status` | str(16) | `PENDING`, `COMPLETED`, `CANCELLED`, `FAILED` |
| `classification` | str(16) | `INTENDED`, `DUPLICATE` or `MISMATCH` |
| `counts_toward_intent` | bool | True only for a live, `INTENDED`, unremediated effect |
| `remediated` | bool | Set when a reviewer resolves with `MANUALLY_REMEDIATED` (or under the state-aware-recovery ablation) |
| `cancel_tries` | int | Unverified cancellation attempts; escalates at `max_cancel_tries` (3) |
| `note` | text, nullable | |
| `observed_at`, `updated_at` | float | |

Classification (`engine._absorb`): an effect that differs from the intent in operation, order,
customer, amount or currency is `MISMATCH`. A matching effect is `DUPLICATE` if another effect
already counts toward the intent and this one is live; otherwise `INTENDED`. If the counted effect
disappears (for example it was cancelled), a live `DUPLICATE` is promoted to `INTENDED`.

### review_cases

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `intent_id` | FK → intents.id, indexed | |
| `reason` | str(48) | `UNRESOLVABLE_OUTCOME`, `IRREVERSIBLE_DISCREPANCY`, `CANCEL_REJECTED`, `CANCEL_UNVERIFIED`, `ATTEMPT_BUDGET_EXHAUSTED` |
| `discrepancy_minor` | bigint | Amount at stake: the full amount for a duplicate or wrong-target effect, else the amount difference |
| `details` | JSON | |
| `status` | str(16), indexed | `OPEN` / `RESOLVED`; at most one open case per intent and reason |
| `resolution`, `resolved_by`, `notes`, `resolved_at` | | See [../product/overview.md](../product/overview.md#what-a-reviewer-can-decide) |
| `created_at` | float | |

### audit_events

| Column | Type | Notes |
|---|---|---|
| `seq` | int PK, autoincrement | Global order |
| `chain_id` | str(64), indexed | The intent id, or `system` for operator events |
| `kind` | str(64) | See below |
| `actor` | str(64) | `gateway`, an operator, an agent id, or a reviewer |
| `payload` | JSON | Stored exactly as hashed |
| `created_at` | float | |
| `prev_hash`, `hash` | str(64) | SHA-256 chain |

Event kinds written by the engine: `intent.authorized`, `intent.revoked`, `intent.state`,
`proposal.decided`, `attempt.reserved`, `attempt.result`, `attempt.lease_expired`,
`attempt.orphaned`, `attempt.absence_confirmed`, `attempt.absence_assumption_violated`,
`attempt.controlled_retry`, `effect.observed`, `effect.reversal_verified`,
`effect.reversal_assumed` (ablation only), `reconcile.lookup_failed`, `review.opened`,
`review.resolved`, `operator.upserted`, `operator.active_changed`.

## Constraints enforced by the database

These hold even if application code is wrong:

| Guarantee | Mechanism |
|---|---|
| At most one live intended effect per intent | Partial unique index `uq_one_live_intended_effect` on `effects(intent_id)` where `counts_toward_intent` (`= 1` on SQLite) |
| One effect row per provider transaction | `effects.provider_ref` is `UNIQUE` |
| Attempt numbers unique per intent | `UNIQUE (intent_id, attempt_no)` (`uq_attempt_no`) |
| Audit log is append-only | SQLite triggers `audit_no_update` / `audit_no_delete` (`BEFORE UPDATE`/`BEFORE DELETE … RAISE(ABORT)`); PostgreSQL trigger `audit_no_modify` calling `audit_events_append_only()` |
| An audit chain cannot fork | `UNIQUE (chain_id, prev_hash)` (`uq_audit_chain_link`) |
| Referential integrity | Foreign keys; SQLite connections run `PRAGMA foreign_keys=ON` |

## Hash-chained audit log

`backend/intentguard/audit.py`. Each event's
`hash = SHA-256(prev_hash + canonical JSON of {chain, kind, actor, payload, at})`, where `prev_hash`
is the previous event's hash in the same chain (64 zeros for the first). `audit.verify` recomputes
every chain in `seq` order and returns the first broken link. `GET /api/audit/verify` and the
dashboard's Audit tab call it.

`test_audit_log_is_append_only_and_tamper_evident` checks that `UPDATE` and `DELETE` are refused,
and that a row rewritten after dropping the trigger is detected at the right `seq`.

## Transactions and locking

`backend/intentguard/db.py`:

- **SQLite:** every transaction starts with `BEGIN IMMEDIATE` (takes the write lock up front),
  WAL journal for file databases, 60 s busy timeout. The benchmark uses shared-cache in-memory
  databases, where transactions are serialized with a process-local lock instead.
- **PostgreSQL:** the intent row is locked with `SELECT … FOR UPDATE` in each unit of work.
- The serialization ablation (`serialize_intent=False`) splits the decision and the attempt
  reservation into two transactions.

PostgreSQL is used by `docker compose` but is not exercised by the automated tests.
