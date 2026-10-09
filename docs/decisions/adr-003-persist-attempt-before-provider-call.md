# ADR-003: Persist the attempt before calling the provider; no provider I/O under a lock

**Status:** Accepted

## Context
If the gateway crashes after calling the provider but before recording the call, money may have
moved with no trace in the ledger. Holding a database lock across a slow provider call would
serialize everything behind the network.

## Decision
`decide` and `reserve` run in one locked transaction that commits an attempt with status
`SUBMITTING`, the key and a lease, before `execute`. Provider calls (create, read-back, search,
cancel) run with no lock held; results are absorbed in a second locked transaction. Each gateway
process has an `incarnation`; on startup, `SUBMITTING` attempts from other incarnations become
`UNKNOWN` and are reconciled, as do attempts past their lease (15 s).

## Consequences
- A crash at either injection point (`after_attempt_recorded`, `after_provider_response`) is recovered with exactly one effect (tested).
- Two transactions per submission instead of one; the window between them is covered by the stable key and the state gate.
