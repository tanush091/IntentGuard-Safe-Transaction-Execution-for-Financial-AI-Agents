# IntentGuard: Intent-Consistent Transaction Execution and Recovery for Financial AI Agents

> **Research prototype.** Everything runs against a simulated payment provider with synthetic
> customers, orders and money. It never connects to a real payment system. Do not put real
> payment credentials anywhere in this repository.

An AI agent can read a support ticket and propose a refund, but a successful API call does not
mean the *authorized* operation happened. The agent may pick a near-miss order, change the amount,
or repeat the refund after a timeout or a restart. IntentGuard sits between the agent and the
payment provider. It binds every proposal to a durable operator authorization, owns submission
and retries, verifies what actually happened at the provider, and then completes, retries,
cancels or escalates based on what it observed.

Around the protocol, the gateway now runs the *IntentGuard Recovery* product surface described in
[docs/API.md](docs/API.md):
- login with roles (operator, reviewer, admin) and short-lived, scoped agent tokens;
- signed provider webhooks;
- reconciliation runs and mismatch detection;
- an advisory exception investigator behind a deterministic policy gate;
- a review queue and a hash-chained audit log;
- a React operations dashboard with one-click demo scenarios.

**Measured result** (10 seeds × 300 scenarios,
[`experiments/results/latest/summary.md`](experiments/results/latest/summary.md)): the full
protocol ends 95.6% ± 0.4% of scenarios correct with 0.0 duplicate effects, 0.0 misreported
outcomes and ₹0 undetected wrong money. Direct access, fixed rules, API idempotency alone and a
pre-execution reviewer reach 70.5% to 84.0%. Details and caveats:
[docs/research/results.md](docs/research/results.md),
[docs/research/limitations.md](docs/research/limitations.md).

## Quickstart

**Windows:** run `start.bat` in the repository root. It does the following, and `stop.bat` stops everything:
1. creates `.env` with locally generated secrets;
2. installs missing or outdated dependencies;
3. starts the mock provider (:8001), the gateway (:8000) and the dashboard (http://localhost:3000);
4. opens the dashboard.

**Manually:**

```bash
python -m pip install -r backend/requirements.txt && npm --prefix frontend install
python scripts/init_env.py                                           # .env with JWT_SECRET, WEBHOOK_SECRET
```

Then, in three terminals from the repository root:

```bash
cd backend && python -m uvicorn provider_api.main:app --port 8001   # mock payment provider
cd backend && python -m uvicorn gateway_api.main:app --port 8000    # IntentGuard gateway
npm --prefix frontend run dev                                        # dashboard: http://localhost:3000
```

**Docker:** `docker compose up --build` runs the gateway on PostgreSQL and serves the dashboard at http://localhost:3000.

**Signing in.** The demo accounts all use the password `intentguard-demo`:
- `asha@intentguard.test` (operator);
- `meera@intentguard.test` (reviewer);
- `admin@intentguard.test` (admin).

The four guided scenarios are one click each on the Overview page ([docs/operations/demo.md](docs/operations/demo.md)). Gateway API docs: http://127.0.0.1:8000/docs. More: [docs/operations/running.md](docs/operations/running.md).

```bash
cd backend && python -m pytest -q                                     # 127 tests (~1 min)
cd frontend && npm test && npm run check:contract                     # dashboard tests, API contract
cd experiments && python -m bench run --seeds 2 --scenarios 60 --out results/quick   # quick benchmark
```

`make install | test | run-provider | run-gateway | run-frontend | bench-quick | bench-full | up | down`
wraps the same commands.

## Repository layout

```
backend/
  intentguard/      protocol core: domain model and state machine, gateway checks, engine,
                    ledger models, hash-chained audit log, provider adapters, ticket->proposal agents
  gateway_api/      FastAPI gateway (:8000): auth, roles, webhooks, reconciliation runs, admin,
                    background worker and crash recovery
  investigator/     advisory exception investigator and its deterministic policy gate
  provider_api/     FastAPI mock payment provider (:8001) with signed webhooks
  paysim/           payment-provider simulator with fault injection
  tests/            127 pytest tests (SQLite; PostgreSQL in CI)
  Dockerfile        one image for both services
experiments/
  bench/            benchmark: seeded scenarios, agent error model, baselines, ablations, oracle, report
  results/latest/   the measured run the documentation cites
frontend/           React dashboard (:3000)
docs/               documentation; start at docs/README.md (target spec at the root, as-built in subfolders)
scripts/            launchers, init_env, check_db, export_openapi, check_bench_safety
start.bat stop.bat  Makefile  docker-compose.yml  .github/workflows/ci.yml
```

## Documentation

Start at [docs/README.md](docs/README.md).

- Target spec: [PRD](docs/PRD.md) · [features](docs/FEATURES.md) · [architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [design](docs/DESIGN.md) · [security](docs/SECURITY.md) · [test plan](docs/TEST_PLAN.md) · [decisions](docs/DECISIONS.md).
- As built:
[architecture](docs/architecture/overview.md) ·
[state machine](docs/architecture/state-machine.md) ·
[reconciliation](docs/architecture/reconciliation.md) ·
[API](docs/architecture/api.md) ·
[threat model](docs/security/threat-model.md) ·
[methodology](docs/research/methodology.md) ·
[paper draft](docs/research/paper/manuscript.md).

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md), [docs/RULES.md](docs/RULES.md) and the open work in
[docs/TASKS.md](docs/TASKS.md). Licence: [LICENSE](LICENSE).
