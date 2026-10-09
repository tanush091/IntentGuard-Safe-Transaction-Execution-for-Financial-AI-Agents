# Development rules

## Before writing code

- Read the target spec for the area you are changing ([API.md](API.md), [ARCHITECTURE.md](ARCHITECTURE.md),
  [SECURITY.md](SECURITY.md), [DESIGN.md](DESIGN.md)). Then read the as-built pages:
  [architecture/overview.md](architecture/overview.md) and
  [architecture/state-machine.md](architecture/state-machine.md). Check the relevant ADRs in
  [DECISIONS.md](DECISIONS.md).
- Check the existing models in `backend/intentguard/models.py` before adding a table or column. A schema
  change bumps `SCHEMA_VERSION`. An older database is then refused at startup, and `scripts/check_db.py`
  moves a local one aside as a backup.
- Never put credentials or keys in source files. Gateway settings come from
  `backend/gateway_api/settings.py` and `.env` (template: `.env.example`; `scripts/init_env.py` generates
  the secrets).

## Financial safety invariants

1. **The agent never reaches the provider.** Only the engine (`backend/intentguard/engine.py`)
   calls a `PaymentProvider`. Agents (`backend/intentguard/agents/`), the investigator
   (`backend/investigator/`) and API handlers produce proposals or recommendations; they never import a
   provider adapter or `paysim`.
2. **Persist before the provider call.** An attempt is committed as `SUBMITTING`, with its key, before
   `provider.create` runs. No provider I/O while a database lock is held.
3. **Intent-anchored idempotency.** The provider key is `ig-<intent_id>-g<key_generation>`, never
   the agent's request ID. Only a verified reversal or a `REFUND_RECOVERED_OUT_OF_BAND` resolution bumps
   the generation.
4. **Unknown is not failure.** A timeout or 5xx leaves the attempt `UNKNOWN`. Absence counts only
   after a successful search at least `absence_window_s` after the attempt. No blind retries.
5. **Observed effects are the truth.** Intent state is derived from attempts, effects and open review
   cases (`engine._derive`). Never report `COMPLETED`, "cancelled" or "reversed" without the provider's
   read-back. Webhook payloads are hints: re-fetch before changing state.
6. **Every state change is legal.** Changes go through `_set_state` and `TRANSITIONS`. If you change
   `TRANSITIONS`, regenerate `architecture/state-machine.md`, `diagrams/state-machine.mmd` and the
   diagram in `ARCHITECTURE.md` §4.
7. **The audit log is append-only.** Never update or delete `audit_logs`; write through `audit.append`
   (or `IntentGuard.record_audit` outside an intent transaction).
8. **Ablations stay real.** A safeguard you add gets a `ProtocolConfig` switch and a test in
   `backend/tests/test_ablations.py` showing it changes behaviour.
9. **The LLM is advisory.** Model output passes a strict schema or is rejected, never repaired. Only the
   deterministic policy gate decides what may run.
10. **Simulator-only stays simulator-only.** Anything that injects faults or bypasses the provider goes
    under `/api/dev/*` behind `SIMULATOR_MODE`.

## API contract

- An endpoint change updates [API.md](API.md) in the same change, then re-exports the schema with
  `python scripts/export_openapi.py`. CI fails if `docs/api/openapi.json` drifts from the code.
- The dashboard calls the gateway only through the route table in `frontend/src/api/endpoints.js`;
  `npm run check:contract` fails when a route is missing from the schema.
- Decisions (`REJECT`, `DUPLICATE`, …) are HTTP 200 bodies. Errors use the envelope in API.md §1.4.

## Results and documentation

- Cite only numbers that exist in `experiments/results/latest/summary.md` or `summary.json`. Never
  type benchmark numbers by hand.
- A benchmark run without `--out` replaces `experiments/results/latest/`. Use
  `--out results/quick` for checks.
- The uppercase docs at `docs/` root are the target spec; the subfolders describe the code as built.
  When you change an endpoint, a state, a check or a table, update the as-built page in the same
  change, and the target spec if the behaviour differs from it. Mark anything not built as *planned*.

## Testing

- Before committing, run:
  - `cd backend && python -m pytest -q` (127 tests, about a minute);
  - `cd frontend && npm test && npm run check:contract && npm run build`;
  - `ruff check .`.

  Do not mark work done with failing tests.
- To run the suite against PostgreSQL, set `TEST_DATABASE_URL` to a dedicated database whose name
  contains `test`; it is wiped before every test.
- New behaviour needs a test; cover the failure and fault paths, not only the happy path.
- Windows consoles: avoid printing characters such as `₹` from scripts without setting UTF-8 output.

## Git

- Conventional commit prefixes: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `perf:`, `ci:`.
- Small, focused commits; don't modify unrelated files.
