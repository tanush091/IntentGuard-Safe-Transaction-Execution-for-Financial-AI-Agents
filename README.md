# IntentGuard — Intent-Consistent Transaction Execution and Recovery for Financial AI Agents

> Research prototype. Everything runs against a simulated payment provider with synthetic
> customers, orders and money. It never connects to a real payment system.

An AI agent can read a support ticket and propose a refund, but a successful API call does not
mean the *authorized* operation happened: the agent may pick a near-miss order, change the amount,
or repeat the refund after a timeout or a restart. IntentGuard sits between the agent and the
payment provider. It binds every proposal to a durable operator authorization, owns submission and
retries, verifies what actually happened at the provider, and then completes, retries, cancels or
escalates based on the observed state.

**Research question.** Does this protocol reduce incorrect and duplicate final financial outcomes
under timeouts, crashes, changed retries and concurrency, while still completing legitimate requests?
The answer, with measured numbers, is in [`experiments/results/latest/summary.md`](experiments/results/latest/summary.md).

---

## Architecture

```
operator ──authorize──▶ Intent (durable)            agent ──proposal──▶ ┐
                                                                        ▼
                ┌──────────────────────── IntentGuard engine ─────────────────────────┐
                │ decide   checks vs. intent + ledger (locked)  ─▶ REJECTED / DUPLICATE│
                │ reserve  attempt + stable idempotency key, intent → IN_FLIGHT        │
                │ execute  provider call (no lock held)                                │
                │ verify   read back the provider transaction                          │
                │ absorb   record effect, derive intent state from the ledger          │
                │ drive    reconcile unknown outcomes · recover discrepancies · retry  │
                └─────────────────────────────┬───────────────────────────────────────┘
                                              ▼
                              payment provider (paysim, over HTTP or in-process)
```

| Package | Role |
|---|---|
| [`intentguard/`](intentguard/) | The protocol core: domain model and state machine, gateway checks, engine, ledger models, hash-chained audit log, provider port and adapters, ticket→proposal agents |
| [`paysim/`](paysim/) | Payment-provider simulator: pending settlement, state-dependent cancellation, idempotency keys with parameter fingerprints, eventually consistent search, fault injection, persistent state |
| [`gateway_api/`](gateway_api/) | FastAPI service for the gateway, with a background reconciliation worker and crash recovery on startup |
| [`provider_api/`](provider_api/) | FastAPI service exposing paysim as a mock provider (`/v1/refunds`, `/v1/authorizations`, `/v1/faults`, `/v1/ledger`) |
| [`bench/`](bench/) | Benchmark: seeded scenario generator, agent error model, baselines and ablations, ground-truth oracle, statistics and report |
| [`frontend/`](frontend/) | React dashboard: live metrics, intent timelines, review queue, audit verification, experiment results |
| [`tests_intentguard/`](tests_intentguard/) | Specification, ablation, concurrency, crash, property-based safety, component and HTTP tests |

### Core ideas

- **Four identities kept separate**: the operator's *intent*, the agent's *proposal*, the gateway's *attempt* (one provider call), and the *effect* actually observed at the provider. Intent state is derived from attempts and effects, never asserted.
- **Gateway checks** (pure functions, [`intentguard/checks.py`](intentguard/checks.py)): customer, order, operation, amount, currency, remaining order balance, operator permission (re-checked at proposal time), already fulfilled, attempt in progress, held for review, attempt budget.
- **Stable provider idempotency key per intent** (`ig-<intent>-g<generation>`), so a restarted or concurrent agent with a new request ID cannot create a second effect. The generation changes only after a verified reversal.
- **Reconciliation with an absence window**: after a timeout the attempt is `UNKNOWN`. "Not found at the provider" counts as evidence of no effect only after `absence_window_s`, because provider search is eventually consistent. If the provider cannot be queried, the intent is held for review rather than retried.
- **State-aware recovery**: a pending refund, or an authorization hold, with the wrong amount, order or customer is cancelled *and the cancellation is verified*. A completed refund cannot be reversed, so it is escalated with the unresolved amount. Nothing is ever reported as reversed without the provider confirming it.
- **Database-level guarantees**: at most one live intended effect per intent (partial unique index), one effect row per provider transaction, and an append-only, hash-chained audit log enforced by triggers.
- **Crash safety**: attempts are persisted before the provider call. After a restart, attempts left `SUBMITTING` by the previous process become `UNKNOWN` and are reconciled.

State machine: [`intentguard/domain.py`](intentguard/domain.py) (`TRANSITIONS`).

---

## Running it

```bash
pip install -r requirements.txt

# terminal 1 — mock provider
python -m uvicorn provider_api.main:app --port 8001
# terminal 2 — gateway (seeds demo operators/orders: ORD-204, ORD-240, ORD-2041 …)
python -m uvicorn gateway_api.main:app --port 8000
# terminal 3 — dashboard on http://localhost:3000
cd frontend && npm install && npm run dev
```

On Windows, `start.bat` launches all three. `docker compose up --build` runs the same stack with PostgreSQL.
Set `PAYMENT_PROVIDER=inprocess` to run the gateway without the provider service.

Agent endpoint: `POST /api/intents/{id}/agent` extracts a proposal from the intent's ticket, using
the offline rule extractor or an LLM when `LLM_PROVIDER` is set (see `.env.example`).
Structured proposals go to `POST /api/intents/{id}/proposals`. API docs: http://localhost:8000/docs.

## Tests

```bash
python -m pytest            # 42 tests, about 1 minute
```

Includes one test per row of the specification's behaviour table; a test per ablation proving the
component changes behaviour in the scenario it exists for (including a deterministic two-agent race);
concurrency (2/4/8 agents → exactly one effect); gateway crashes at both crash points; Hypothesis
property tests over random faults, wrong proposals, crashes and restarts; and end-to-end HTTP tests
through the real provider API.

## Reproducing the experiment

```bash
python -m bench run --seeds 10 --start-seed 42 --scenarios 300   # ~15 min on 8 cores
python -m bench run --seeds 2 --scenarios 60                     # quick check
python -m bench run --llm-reviewer                               # baseline D with a real LLM
```

Output goes to `experiments/results/<run_id>/` and `experiments/results/latest/`:
`summary.md` (tables), `summary.json` (served at `/api/experiments/latest` and shown in the
dashboard), and `scenarios.csv` (one row per arm × seed × scenario).

How the benchmark avoids the usual traps:

- **The seed controls the scenario mix**, not just the IDs. There are 30 categories in 6 families: clean, agent error, provider fault, runtime (crash/restart/concurrency), payment authorization, governance.
- **Near-miss identifiers** (ORD-2041 / ORD-2014 / ORD-2401, with the same or a different customer) and realistic agent errors (×10 amounts, rupee/paisa confusion, wrong currency). Errors are either transient or persistent.
- **Identical agent behaviour for every arm.** The agent runtime retries on errors and re-proposes after rejections, the same way for all architectures.
- **One oracle for every arm**, reading the provider's ground-truth ledger after a 900 s settlement horizon ([`bench/scoring.py`](bench/scoring.py)). An arm's own bookkeeping is used only to detect *misreports*.
- **Real ablations** are configuration switches on the engine ([`intentguard/config.py`](intentguard/config.py)). They include combined ablations, because several safeguards back each other up.
- **Real concurrency** (threads) and real crash injection at two points in the engine.

## Limitations

- The provider is a simulator modelled on documented provider behaviour; it is not a real provider sandbox.
- The baseline agent's errors come from an explicit error model. Baseline D's offline reviewer reuses the deterministic ticket extractor, which is an optimistic stand-in for an LLM reviewer; run with `--llm-reviewer` for a real one.
- Experiments use SQLite (shared-cache in-memory). PostgreSQL is supported by the code and Docker setup but was not exercised by the automated tests.
- Latency figures are in-process wall-clock times and say nothing about production performance.

## Legacy code

`src/`, `backend/`, `mock-payment-service/`, `tests/`, `run_benchmark.py`, `run_multiple_seeds.py`,
`benchmark_results*.json`, `benchmark_summary.md`, `failure_analysis.md` and `pytest_output.txt` belong to the earlier
prototype and are no longer used. Their published numbers were not produced by a measured run
(`run_multiple_seeds.py` wrote fixed values) and must not be cited. They can be deleted.
