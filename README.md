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

**Measured result** (10 seeds × 300 scenarios,
[`experiments/results/latest/summary.md`](experiments/results/latest/summary.md)): the full
protocol ends 95.6% ± 0.4% of scenarios correct with 0.0 duplicate effects, 0.0 misreported
outcomes and ₹0 undetected wrong money. Direct access, fixed rules, API idempotency alone and a
pre-execution reviewer reach 70.5% to 84.0%. Details and caveats:
[docs/research/results.md](docs/research/results.md),
[docs/research/limitations.md](docs/research/limitations.md).

## Quickstart

```bash
python -m pip install -r backend/requirements.txt && npm --prefix frontend install
```

Then, in three terminals from the repository root:

```bash
cd backend && python -m uvicorn provider_api.main:app --port 8001   # mock payment provider
cd backend && python -m uvicorn gateway_api.main:app --port 8000    # IntentGuard gateway
npm --prefix frontend run dev                                        # dashboard: http://localhost:3000
```

On Windows, `scripts\start.bat` does all of this. With Docker: `docker compose up --build`
(gateway on PostgreSQL). Gateway API docs: http://127.0.0.1:8000/docs. More:
[docs/operations/running.md](docs/operations/running.md); four guided scenarios:
[docs/operations/demo.md](docs/operations/demo.md).

```bash
cd backend && python -m pytest                                        # 42 tests
cd experiments && python -m bench run --seeds 2 --scenarios 60 --out results/quick   # quick benchmark
```

`make install | test | run-provider | run-gateway | run-frontend | bench-quick | bench-full | up | down`
wraps the same commands.

## Repository layout

```
backend/
  intentguard/      protocol core: domain model and state machine, gateway checks, engine,
                    ledger models, hash-chained audit log, provider adapters, ticket->proposal agents
  gateway_api/      FastAPI gateway (:8000) with background reconciliation worker and crash recovery
  provider_api/     FastAPI mock payment provider (:8001)
  paysim/           payment-provider simulator with fault injection
  tests/            42 pytest tests
  Dockerfile        one image for both services
experiments/
  bench/            benchmark: seeded scenarios, agent error model, baselines, ablations, oracle, report
  results/latest/   the measured run the documentation cites
frontend/           React dashboard (:3000)
docs/               documentation; start at docs/README.md
scripts/            start.bat / stop.bat (Windows)
Makefile  docker-compose.yml  .github/workflows/ci.yml
```

## Documentation

Start at [docs/README.md](docs/README.md). Key pages:
[architecture](docs/architecture/overview.md) ·
[state machine](docs/architecture/state-machine.md) ·
[reconciliation](docs/architecture/reconciliation.md) ·
[API](docs/architecture/api.md) ·
[threat model](docs/security/threat-model.md) ·
[methodology](docs/research/methodology.md) ·
[paper draft](docs/research/paper/manuscript.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [RULES.md](RULES.md) and the open work in
[TASKS.md](TASKS.md). Licence: [LICENSE](LICENSE).
