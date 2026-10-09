# ADR-007: A simulated provider behind a provider port

**Status:** Accepted (refines "Decoupled Mock Payment Service" in the archive)

## Context
The project must never touch real money, yet needs realistic provider behaviour: pending
settlement, state-dependent cancellation, idempotency with parameter checks, eventually consistent
search, and failures on demand. The benchmark needs the same behaviour deterministically and fast.

## Decision
`paysim` implements the provider with an injectable clock and eight fault kinds. The engine
depends only on the `PaymentProvider` protocol (`providers/base.py`), with two adapters:
`HttpProvider` (to `provider_api`, a separate FastAPI service) and `InProcessProvider` (direct,
used by the benchmark and most tests).

## Consequences
- Real network behaviour (504 lost responses, 503 outages) in the running stack; deterministic simulated time in the benchmark.
- A real provider sandbox can be added as another adapter without changing the engine.
- Results are only as realistic as the simulator; it has not been validated against a real sandbox.
