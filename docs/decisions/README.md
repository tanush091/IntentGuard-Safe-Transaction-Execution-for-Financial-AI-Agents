# Architecture decision records

One file per decision. Decisions from the earlier prototype are kept in
[../archive/DECISIONS.md](../archive/DECISIONS.md).

| ADR | Decision |
|---|---|
| [ADR-001](adr-001-separate-intent-proposal-attempt-effect.md) | Keep intent, proposal, attempt and effect separate |
| [ADR-002](adr-002-intent-anchored-idempotency-key.md) | One provider idempotency key per intent, with generations |
| [ADR-003](adr-003-persist-attempt-before-provider-call.md) | Persist the attempt before calling the provider; no provider I/O under a lock |
| [ADR-004](adr-004-unknown-outcomes-and-absence-window.md) | Unknown outcomes are reconciled; absence counts only after a window |
| [ADR-005](adr-005-state-aware-verified-recovery.md) | Recovery is state-aware and verified; otherwise escalate |
| [ADR-006](adr-006-database-enforced-invariants.md) | Enforce key invariants in the database |
| [ADR-007](adr-007-simulated-provider-behind-a-port.md) | A simulated provider behind a provider port |
| [ADR-008](adr-008-sqlite-default-postgresql-supported.md) | SQLite by default, PostgreSQL supported |
| [ADR-009](adr-009-agent-as-untrusted-extractor.md) | The agent only proposes; the LLM is an extractor |
| [ADR-010](adr-010-benchmark-single-oracle.md) | One oracle on the provider's ledger, identical agent behaviour for every arm |
| [ADR-011](adr-011-ablations-as-configuration-switches.md) | Ablations are configuration switches on the real engine |
| [ADR-012](adr-012-repository-layout.md) | Repository layout |
