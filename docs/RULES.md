# Development rules

## Before writing code

- Read [docs/architecture/overview.md](docs/architecture/overview.md),
  [docs/architecture/state-machine.md](docs/architecture/state-machine.md) and the relevant
  [ADRs](docs/decisions/).
- Check the existing models in `backend/intentguard/models.py` before adding a table or column.
- Never put credentials or keys in source files. Gateway settings come from
  `backend/gateway_api/settings.py` and `.env` (template: `.env.example`).

## Financial safety invariants

1. **The agent never reaches the provider.** Only the engine (`backend/intentguard/engine.py`)
   calls a `PaymentProvider`. Agents (`backend/intentguard/agents/`) and API handlers produce
   proposals; they never import a provider adapter or `paysim`.
2. **Persist before the provider call.** An attempt is committed as `SUBMITTING`, with its key, before
   `provider.create` runs. No provider I/O while a database lock is held.
3. **Intent-anchored idempotency.** The provider key is `ig-<intent_id>-g<key_generation>`, never
   the agent's request ID. Only a verified reversal or a `MANUALLY_REMEDIATED` resolution bumps the
   generation.
4. **Unknown is not failure.** A timeout or 5xx leaves the attempt `UNKNOWN`. Absence counts only
   after a successful search at least `absence_window_s` after the attempt. No blind retries.
5. **Observed effects are the truth.** Intent state is derived from attempts and effects
   (`engine._derive`). Never report `COMPLETED` or "reversed" without the provider's read-back.
6. **Every state change is legal.** Changes go through `_set_state` and `TRANSITIONS`. If you change
   `TRANSITIONS`, regenerate `docs/architecture/state-machine.md` and `docs/diagrams/state-machine.mmd`.
7. **The audit log is append-only.** Never update or delete `audit_events`; write through `audit.append`.
8. **Ablations stay real.** A safeguard you add gets a `ProtocolConfig` switch and a test in
   `backend/tests/test_ablations.py` showing it changes behaviour.

## Results and documentation

- Cite only numbers that exist in `experiments/results/latest/summary.md` or `summary.json`. Never
  type benchmark numbers by hand.
- A benchmark run without `--out` replaces `experiments/results/latest/`. Use
  `--out results/quick` (or `make bench-quick`) for checks.
- Keep the docs in step with the code: if you change an endpoint, a state, a check or a table,
  update the page in `docs/architecture/` in the same change.

## Testing

- Run `cd backend && python -m pytest` (42 tests) and `npm --prefix frontend run build` before
  committing. Do not mark work done with failing tests.
- New behaviour needs a test; cover the failure and fault paths, not only the happy path.
- Windows consoles: avoid printing characters such as `₹` from scripts without setting UTF-8 output.

## Git

- Conventional commit prefixes: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `perf:`.
- Small, focused commits; don't modify unrelated files.
