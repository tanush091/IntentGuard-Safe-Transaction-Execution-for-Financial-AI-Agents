# Contributing to IntentGuard

Thank you for contributing to **IntentGuard: Intent-Consistent Transaction Execution and Recovery
for Financial AI Agents Under Uncertain Outcomes**.

## Research prototype safety notice

- **Never** introduce real payment credentials, real banking API connections or live payment SDKs
  (e.g. Stripe or Razorpay live keys, UPI endpoints).
- All financial operations **must** target the simulator (`backend/paysim/`, served by
  `backend/provider_api/`).
- Keep benchmark runs reproducible from their seeds, and never report a number that is not in
  `experiments/results/latest/summary.md` or `summary.json`.

## Where things go

| Change | Location |
|---|---|
| States, decisions, transitions, cancellation policy | `backend/intentguard/domain.py` |
| Proposal checks (pure functions) | `backend/intentguard/checks.py` |
| Protocol behaviour (decide, reserve, execute, reconcile, recover, review) | `backend/intentguard/engine.py` |
| Tables and database constraints | `backend/intentguard/models.py`, `db.py`; audit log in `audit.py` |
| Provider adapters | `backend/intentguard/providers/` |
| Ticket → proposal extraction | `backend/intentguard/agents/` |
| Gateway HTTP API and settings | `backend/gateway_api/` |
| Mock provider HTTP API / simulator | `backend/provider_api/`, `backend/paysim/` |
| Tests | `backend/tests/` |
| Benchmark | `experiments/bench/` |
| Dashboard | `frontend/src/` |
| Documentation | `docs/` (see [docs/README.md](docs/README.md)) |

Read [RULES.md](RULES.md) before changing protocol code.

## Code standards

1. Python 3.12+, type annotations, Pydantic v2 models at the HTTP boundary, SQLAlchemy 2.0.
2. Keep business logic in the engine and checks; route handlers only translate HTTP.
3. A new safeguard gets a `ProtocolConfig` switch and an ablation test.
4. Commit messages: conventional and imperative (e.g. `feat: reconcile lost responses by idempotency key`,
   `test: cover revoke from RETRYABLE`).

## Before opening a pull request

```bash
cd backend && python -m pytest          # 42 tests must pass
npm --prefix frontend run build         # dashboard must build
```

CI (`.github/workflows/ci.yml`) runs both. Update the matching page in `docs/` when behaviour
changes.

## Team roles

- **U V Tanush** (`tanush091`): project architecture, gateway and payment simulator, core framework
- **Narla Sindhuja** (`NarlaSindhuja-5` / `narlasindhuja45@gmail.com`): safety protocol, reconciliation and recovery, experimental methodology and benchmark validation

The earlier branch strategy is in [docs/archive/git_workflow.md](docs/archive/git_workflow.md)
(written for the earlier prototype).
