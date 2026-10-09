# Architecture decision records

All decisions now live in one register with one numbering: **[../DECISIONS.md](../DECISIONS.md)**.

The prototype's ADR files that used to be here were merged into it on 2026-10-10 and moved to
[../archive/decisions/](../archive/decisions/), unchanged, for history. Older references such as
"ADR-004" in commit messages or earlier drafts use the old numbers; this table maps them.

| Old file (archived) | Now |
|---|---|
| adr-001 Keep intent, proposal, attempt and effect separate | [ADR-002](../DECISIONS.md#adr-002-four-separate-identities-intent-proposal-attempt-effect) |
| adr-002 One provider idempotency key per intent, with generations | [ADR-001](../DECISIONS.md#adr-001-intent-anchored-idempotency) |
| adr-003 Persist the attempt before calling the provider | [ADR-007](../DECISIONS.md#adr-007-persist-before-external-call) |
| adr-004 Unknown outcomes are reconciled; absence counts only after a window | [ADR-003](../DECISIONS.md#adr-003-treat-timeouts-as-unknown-and-reconcile-before-retry), [ADR-004](../DECISIONS.md#adr-004-absence-window-for-not-found) |
| adr-005 Recovery is state-aware and verified; otherwise escalate | [ADR-024](../DECISIONS.md#adr-024-recovery-is-state-aware-and-verified-otherwise-escalate) |
| adr-006 Enforce key invariants in the database | [ADR-025](../DECISIONS.md#adr-025-enforce-key-invariants-in-the-database) |
| adr-007 A simulated provider behind a provider port | [ADR-009](../DECISIONS.md#adr-009-decoupled-provider-simulator) |
| adr-008 SQLite by default, PostgreSQL supported | [ADR-016](../DECISIONS.md#adr-016-postgresql-as-durable-source-of-truth-redis-optional) |
| adr-009 The agent only proposes; the LLM is an extractor | [ADR-006](../DECISIONS.md#adr-006-agent-is-untrusted-and-isolated) |
| adr-010 One oracle on the provider's ledger | [ADR-010](../DECISIONS.md#adr-010-seeded-benchmark-with-a-single-oracle) |
| adr-011 Ablations are configuration switches on the real engine | [ADR-026](../DECISIONS.md#adr-026-ablations-are-configuration-switches-on-the-real-engine) |
| adr-012 Repository layout | [ADR-027](../DECISIONS.md#adr-027-repository-layout) |

New decisions go into DECISIONS.md with the next free number.
