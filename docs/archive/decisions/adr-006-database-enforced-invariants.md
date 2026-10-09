# ADR-006: Enforce key invariants in the database

**Status:** Accepted

## Context
Application checks can have bugs and races. The two properties that matter most, at most one live
intended effect per intent and an unalterable history, should not depend on them alone.

## Decision
- Partial unique index `uq_one_live_intended_effect` on `effects(intent_id)` where `counts_toward_intent`.
- `effects.provider_ref` unique; `(intent_id, attempt_no)` unique.
- `audit_events` append-only via triggers (SQLite `audit_no_update`/`audit_no_delete`, PostgreSQL `audit_no_modify`), hash-chained per intent, `UNIQUE(chain_id, prev_hash)` so a chain cannot fork. `audit.verify` recomputes the chains.

## Consequences
- A logic error that would create a second intended effect fails at commit instead of moving money silently.
- Tampering is detectable (`GET /api/audit/verify`), not preventable by a privileged attacker.
- PostgreSQL versions of the triggers and index are not covered by automated tests.
