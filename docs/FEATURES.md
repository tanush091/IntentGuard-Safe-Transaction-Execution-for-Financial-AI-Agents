# Feature Reference (FEATURES.md) — IntentGuard Recovery

**How to read the status column**

| Status | Meaning |
|--------|---------|
| ✅ Implemented | Built and covered by tests (research prototype, simulated provider only) |
| 🔶 Partial | Partly built, or built but not yet against a real provider sandbox |
| 🔲 Planned | Product-direction feature; not yet built |

> Statuses were checked against the code and the test suite on 2026-10-10 (branch `feat/recovery-rebuild`):
> - backend: 127 tests, which pass on SQLite and on PostgreSQL 16;
> - dashboard: 19 unit tests, plus the route contract check;
> - the dashboard demo was run in headless Chrome.
>
> The as-built reference is [architecture/](architecture/). Nothing here has been validated with real customers or real funds.

---

## 1. Execution core

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-01 | Durable intent binding (operator authorization → `intent_id`) | ✅ | Operator permission re-checked at proposal time |
| F-02 | Deterministic gateway checks | ✅ | Customer, order, operation, amount (exact match), currency, remaining balance, operator permission, already completed, attempt in progress, held for review, attempt budget, plus the policy checks (kill switch, maximum amount) (`intentguard/checks.py`, pure functions) |
| F-03 | Stable provider idempotency key per intent | ✅ | `ig-<intent>-g<generation>`; generation changes only after verified reversal |
| F-04 | Transaction state machine | ✅ | Legal transitions in `intentguard/domain.py` (`TRANSITIONS`) |
| F-05 | Persist-before-call and crash safety | ✅ | `SUBMITTING` attempts become `UNKNOWN` on restart, then reconciled |
| F-06 | Concurrent-attempt protection | ✅ | Locked decision step (`SELECT … FOR UPDATE` on PostgreSQL); DB-level partial unique index: one counted effect per intent; unique attempt numbers |
| F-07 | One effect row per provider transaction | ✅ | DB constraint |

## 2. Recovery and reconciliation

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-10 | Timeout → `UNKNOWN` handling | ✅ | No immediate retry |
| F-11 | Active reconciliation with absence window | ✅ | Lookup by provider transaction and order reference; provider unreachable → hold for review |
| F-12 | State-aware recovery | ✅ | Pending/hold with wrong amount/order/customer is cancelled **and verified**; completed refund is escalated with unresolved amount |
| F-13 | Background reconciliation worker | ✅ | Runs in the gateway API service |
| F-14 | Controlled retry | ✅ | Only when evidence supports it and attempt budget remains |
| F-15 | Webhook ingestion (signature verify, dedupe, ordering) | ✅ | `POST /webhooks/paysim`: HMAC signature with timestamp tolerance, dedupe by event id, then a **re-fetch** from the provider, so delivery order does not matter (ADR-021). The simulator emits signed events |
| F-16 | Order/payment/refund/event mismatch detection | ✅ | Matching runs (`POST /reconciliation/runs`) and webhooks record MISSING, DUPLICATE, AMOUNT, ORDER and CUSTOMER mismatches; reviewers resolve them |
| F-18 | Operator cancel flow | ✅ | `POST /intents/{id}/cancel`: immediate when nothing is live; otherwise `CANCEL_REQUESTED` → verified provider cancel/void → `CANCELLED`, or `ESCALATED` (ADR-030) |
| F-17 | Remaining-refundable-balance enforcement against provider records | 🔶 | Balance check exists against internal order data; provider-sourced verification planned |

## 3. Governance and audit

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-20 | Append-only hash-chained audit log | ✅ | DB triggers block update/delete |
| F-21 | Audit verification | ✅ | Dashboard shows verification result |
| F-22 | Review queue with open cases | ✅ | Discrepancy amount recorded; resolve action |
| F-23 | Refund policy engine (configurable limits) | ✅ | Per-operator operations and limits; admin-editable policies kept across restarts and audited: maximum amount, attempt budget, absence window, unknown-review delay, separation of duties |
| F-24 | Kill switch (force hold-for-review) | ✅ | Policy `kill_switch`: every new proposal is `HOLD_FOR_REVIEW` (`KILL_SWITCH`) |
| F-25 | Separation of duties | ✅ | The operator who authorized an intent cannot resolve its review case |
| F-26 | Authentication, RBAC, scoped agent tokens | ✅ | See F-74 |

## 4. Agents and AI

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-30 | Offline rule-based ticket → proposal extractor | ✅ | Default fallback |
| F-31 | LLM extraction via `LLM_PROVIDER` | ✅ | Configured through `.env` (loaded by every entry point); strict output validation (`422 INVALID_AGENT_OUTPUT`, never repaired); agent stays outside trust boundary. No recorded run with a real model yet |
| F-32 | `POST /intents/{id}/agent` | ✅ | Extract from ticket, submit through the gateway |
| F-33 | LLM reviewer baseline (Baseline D) | 🔶 | Offline stand-in is optimistic; real LLM run via `--llm-reviewer` |
| F-34 | AI exception investigator (classify + summarize + recommend) | ✅ | `backend/investigator`: redacted evidence bundle, offline rule classifier by default or an LLM with a strict schema, deterministic policy gate; applying re-checks the gate on fresh evidence (ADR-013, ADR-033). Runs on demand for exception states |
| F-35 | Prompt-injection evaluation set | 🔲 | See TEST_PLAN.md §8 |

## 5. Providers

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-40 | Provider simulator (`paysim`) | ✅ | Pending settlement, state-dependent cancellation, idempotency fingerprints, eventually consistent search, fault injection, persistent state |
| F-41 | Mock provider HTTP service (`provider_api`) | ✅ | `/v1/refunds`, `/v1/authorizations`, `/v1/orders`, `/v1/faults` (simulator mode only), `/v1/ledger`; signed webhooks to the gateway |
| F-42 | In-process provider mode | ✅ | `PAYMENT_PROVIDER=inprocess` |
| F-43 | Secondary workflow: payment authorization hold + cancellation | ✅ | Used to evaluate transferability |
| F-44 | Real provider test-mode adapter (Stripe or Razorpay) | 🔲 | Behind the provider port (ADR-012) |
| F-45 | Multi-provider common interface | 🔲 | Phase 4 |

## 6. Fault injection

| Fault | Status |
|-------|--------|
| Timeout before execution | ✅ |
| Timeout after execution (lost response) | ✅ |
| Service outage | ✅ |
| Delayed status (pending → completed) | ✅ |
| Failed cancellation | ✅ |
| Corrupt/mismatched amount at provider | ✅ |
| Gateway crash at two engine crash points | ✅ |
| Agent restart with new request ID | ✅ |
| Duplicate / out-of-order webhooks | ✅ (`WEBHOOK_DUPLICATE`, `WEBHOOK_DELAY`) |

## 7. Dashboard (React)

| ID | Feature | Status |
|----|---------|--------|
| F-50 | Live metrics | ✅ |
| F-51 | Intent timelines | ✅ |
| F-52 | Review queue with resolve action | ✅ |
| F-53 | Audit verification view | ✅ |
| F-54 | Experiment results view (`/api/experiments/latest`) | ✅ |
| F-55 | Prescribed demo scenarios (unauthorized amount, lost response, restart, incorrect completed effect) | ✅ One-click cards on the Overview page, each on a fresh simulator order |
| F-56 | Investigator panel, mismatch view, recovery analytics | ✅ Panel and mismatch view; 🔶 analytics are the metrics summary only |
| F-57 | Login / role-based UI / admin pages | ✅ Login, role-gated navigation and actions, Admin page (users, service tokens, policies, providers) |
| F-58 | Dark/light theme, responsive to 390 px, reduced motion | ✅ |

## 8. Benchmark and research

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-60 | Seeded scenario generator | ✅ | 30 categories in 6 families: clean, agent error, provider fault, runtime, payment authorization, governance |
| F-61 | Realistic agent error model | ✅ | ×10 amounts, rupee/paisa confusion, wrong currency, near-miss IDs (ORD-2041/2014/2401); transient or persistent |
| F-62 | Baselines and real ablations | ✅ | Config switches on the engine, including combined ablations |
| F-63 | Single ground-truth oracle | ✅ | Reads provider ledger after a 900 s settlement horizon (`bench/scoring.py`) |
| F-64 | Multi-seed runs with statistics and report | ✅ | `python -m bench run --seeds 10 --start-seed 42 --scenarios 300`; outputs `summary.md`, `summary.json`, `scenarios.csv` |
| F-65 | Real concurrency and crash injection in benchmark | ✅ | Threads; two crash points |
| F-66 | PostgreSQL benchmark / concurrency run | 🔶 | The whole test suite, including the concurrency and crash tests, runs on PostgreSQL in CI; no benchmark run uses PostgreSQL |
| F-67 | Cost and LLM-token accounting per resolved exception | 🔶 | Each investigation stores its model and token counts; aggregation per resolved exception is planned |
| F-68 | CI safety gate on the benchmark | ✅ | A quick run fails the build on any duplicate effect, undetected wrong money or misreport by the full protocol |

## 9. Platform and operations

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-70 | Docker Compose stack with PostgreSQL | ✅ | `docker compose up --build` |
| F-71 | Windows start/stop scripts | ✅ | `start.bat`, `stop.bat` |
| F-72 | Test suite | ✅ | 127 backend tests: spec behaviour table, ablations, concurrency (2/4/8 agents), crash, Hypothesis property tests, HTTP end-to-end, auth, RBAC, API contract, webhooks, investigator, operations. Plus 19 dashboard unit tests and the route contract check |
| F-73 | CI pipeline | ✅ | ruff; backend on SQLite and PostgreSQL; OpenAPI drift; dashboard tests, contract and build; benchmark safety gate; gitleaks, pip-audit, `npm audit`; image build |
| F-74 | JWT auth, RBAC, scoped agent tokens | ✅ | argon2id passwords with lockout, HS256 access tokens, rotating refresh tokens (HttpOnly cookie for browsers), roles and capabilities, intent- or customer-scoped agent tokens ≤ 300 s, revocable. See SECURITY.md |
| F-75 | Multi-tenancy with RLS | 🔲 | ADR-020 |
| F-76 | Repeatable local start | ✅ | `start.bat` creates `.env` with generated secrets, installs missing or stale dependencies, and moves a database from an earlier schema aside as a backup |
| F-77 | MFA for reviewer/admin; hosted deployment with TLS | 🔲 | SECURITY.md |

## 10. Known limitations (carry into any external description)
- Provider is a simulator modelled on documented behaviour, not a real provider sandbox.
- Agent errors come from an explicit error model.
- Baseline D's offline reviewer reuses the deterministic extractor and is optimistic.
- Experiments use SQLite (shared-cache in-memory). PostgreSQL is covered by the test suite in CI, but no benchmark run uses it.
- Latency numbers are in-process and say nothing about production performance.
- Results and impact claims are simulation-based; no customer deployment exists.
