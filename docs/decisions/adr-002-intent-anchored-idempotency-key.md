# ADR-002: One provider idempotency key per intent, with generations

**Status:** Accepted (supersedes the earlier `idem_{intent_id}` scheme in the archived DECISIONS.md)

## Context
Provider idempotency keys deduplicate requests that reuse a key. If the key comes from the agent's
request ID, a crashed and restarted agent, or a second concurrent agent, sends a different key and
the provider executes again. A fixed key per intent, however, would make a legitimate retry after
a verified reversal replay the reversed transaction.

## Decision
Every attempt carries `ig-<intent_id>-g<key_generation>` (`engine._reserve`). The generation
starts at 0 and is bumped only after a wrong effect from one of the intent's attempts is verified
`CANCELLED` at the provider, or a reviewer resolves `MANUALLY_REMEDIATED`. Timeouts and confirmed
absences do not change it.

## Consequences
- Restarts, concurrent agents and the gateway's own retries all replay the same provider transaction.
- The key also backs up other safeguards: removing it together with dedup, the absence window or reconciliation brings duplicates back (see `docs/research/results.md`).
- Correctness depends on the provider honouring idempotency keys with parameter fingerprints, as `paysim` does.
