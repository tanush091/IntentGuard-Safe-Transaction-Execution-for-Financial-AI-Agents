> **Archived.** Merged into the single register [docs/DECISIONS.md](../../DECISIONS.md) on 2026-10-10; see the [old → new number map](../../decisions/README.md). Kept unchanged for history; names in this file are the prototype's.

# ADR-012: Repository layout

**Status:** Accepted (2026-10-09, branch `chore/restructure`)

## Context
The repository mixed the current build with an unused earlier prototype (`src/`, an older
`backend/`, `mock-payment-service/`, `tests/`) whose published numbers were not measured, and kept
current packages, tests and benchmark at the root.

## Decision
- Delete the earlier prototype (history remains in git).
- `backend/` holds the Python services and protocol: `intentguard/`, `gateway_api/`, `provider_api/`, `paysim/`, `tests/`, `requirements.txt`, `pytest.ini`, and one `Dockerfile` used for both services.
- `experiments/bench/` holds the benchmark, next to `experiments/results/`. It adds `backend/` to `sys.path`, so it runs from `experiments/` with `python -m bench` and needs no install step.
- `frontend/` is unchanged. `scripts/` holds the Windows launchers.
- `docs/` is organised by audience; superseded documents are kept in `docs/archive/` with a banner.

## Consequences
- Commands changed: tests and services run from `backend/`, the benchmark from `experiments/` (or via the root `Makefile`).
- `make bench-quick` writes to `experiments/results/quick/` so it never replaces the cited results in `latest/`.
