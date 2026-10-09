# Feature Reference (FEATURES.md) — IntentGuard Recovery

**How to read the status column**

| Status | Meaning |
|--------|---------|
| ✅ Implemented | Described as working in the repository README (research prototype, simulated provider) |
| 🔶 Partial | Exists in the prototype but not yet against a real provider sandbox, or not exercised in automated tests |
| 🔲 Planned | Product-direction feature; not yet built |

> The "Implemented" rows reflect the repository README at time of writing. **Verify against the code and test suite before citing them externally.** Nothing here has been validated with real customers or real funds.

---

## 1. Execution core

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-01 | Durable intent binding (operator authorization → `intent_id`) | ✅ | Operator permission re-checked at proposal time |
| F-02 | Deterministic gateway checks | ✅ | Customer, order, operation, amount, currency, remaining balance, operator permission, already fulfilled, attempt in progress, held for review, attempt budget (`intentguard/checks.py`, pure functions) |
| F-03 | Stable provider idempotency key per intent | ✅ | `ig-<intent>-g<generation>`; generation changes only after verified reversal |
| F-04 | Transaction state machine | ✅ | Legal transitions in `intentguard/domain.py` (`TRANSITIONS`) |
| F-05 | Persist-before-call and crash safety | ✅ | `SUBMITTING` attempts become `UNKNOWN` on restart, then reconciled |
| F-06 | Concurrent-attempt protection | ✅ | Locked decision step; DB-level partial unique index: one live intended effect per intent |
| F-07 | One effect row per provider transaction | ✅ | DB constraint |

## 2. Recovery and reconciliation

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-10 | Timeout → `UNKNOWN` handling | ✅ | No immediate retry |
| F-11 | Active reconciliation with absence window | ✅ | Lookup by provider transaction and order reference; provider unreachable → hold for review |
| F-12 | State-aware recovery | ✅ | Pending/hold with wrong amount/order/customer is cancelled **and verified**; completed refund is escalated with unresolved amount |
| F-13 | Background reconciliation worker | ✅ | Runs in the gateway API service |
| F-14 | Controlled retry | ✅ | Only when evidence supports it and attempt budget remains |
| F-15 | Webhook ingestion (signature verify, dedupe, ordering) | 🔲 | Planned for real-provider phase |
| F-16 | Order/payment/refund/event mismatch detection | 🔲 | Planned (MISSING, DUPLICATE, AMOUNT, ORDER, CUSTOMER) |
| F-17 | Remaining-refundable-balance enforcement against provider records | 🔶 | Balance check exists against internal order data; provider-sourced verification planned |

## 3. Governance and audit

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-20 | Append-only hash-chained audit log | ✅ | DB triggers block update/delete |
| F-21 | Audit verification | ✅ | Dashboard shows verification result |
| F-22 | Review queue with open cases | ✅ | Discrepancy amount recorded; resolve action |
| F-23 | Refund policy engine (configurable limits) | 🔶 | Core limits enforced; admin-editable policies planned |
| F-24 | Kill switch (force hold-for-review) | 🔲 | Planned |

## 4. Agents and AI

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-30 | Offline rule-based ticket → proposal extractor | ✅ | Default fallback |
| F-31 | LLM extraction via `LLM_PROVIDER` | ✅ | Configured through `.env`; output validated; agent stays outside trust boundary |
| F-32 | `POST /intents/{id}/agent` | ✅ | Extract from ticket, submit through the gateway |
| F-33 | LLM reviewer baseline (Baseline D) | 🔶 | Offline stand-in is optimistic; real LLM run via `--llm-reviewer` |
| F-34 | AI exception investigator (classify + summarize + recommend) | 🔲 | Advisory only; policy-gated (ADR-013) |
| F-35 | Prompt-injection evaluation set | 🔲 | See TEST_PLAN.md §8 |

## 5. Providers

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-40 | Provider simulator (`paysim`) | ✅ | Pending settlement, state-dependent cancellation, idempotency fingerprints, eventually consistent search, fault injection, persistent state |
| F-41 | Mock provider HTTP service (`provider_api`) | ✅ | `/v1/refunds`, `/v1/authorizations`, `/v1/faults`, `/v1/ledger` |
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
| Duplicate / out-of-order webhooks | 🔲 |

## 7. Dashboard (React)

| ID | Feature | Status |
|----|---------|--------|
| F-50 | Live metrics | ✅ |
| F-51 | Intent timelines | ✅ |
| F-52 | Review queue with resolve action | ✅ |
| F-53 | Audit verification view | ✅ |
| F-54 | Experiment results view (`/api/experiments/latest`) | ✅ |
| F-55 | Prescribed demo scenarios (unauthorized amount, lost response, restart, incorrect completed effect) | 🔶 (confirm against current UI) |
| F-56 | Investigator panel, mismatch view, recovery analytics | 🔲 |
| F-57 | Login / role-based UI / admin pages | 🔲 |

## 8. Benchmark and research

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-60 | Seeded scenario generator | ✅ | 30 categories in 6 families: clean, agent error, provider fault, runtime, payment authorization, governance |
| F-61 | Realistic agent error model | ✅ | ×10 amounts, rupee/paisa confusion, wrong currency, near-miss IDs (ORD-2041/2014/2401); transient or persistent |
| F-62 | Baselines and real ablations | ✅ | Config switches on the engine, including combined ablations |
| F-63 | Single ground-truth oracle | ✅ | Reads provider ledger after a 900 s settlement horizon (`bench/scoring.py`) |
| F-64 | Multi-seed runs with statistics and report | ✅ | `python -m bench run --seeds 10 --start-seed 42 --scenarios 300`; outputs `summary.md`, `summary.json`, `scenarios.csv` |
| F-65 | Real concurrency and crash injection in benchmark | ✅ | Threads; two crash points |
| F-66 | PostgreSQL benchmark / concurrency run | 🔲 | Code supports it; not exercised by automated tests |
| F-67 | Cost and LLM-token accounting per resolved exception | 🔲 | Needed for investigator evaluation |

## 9. Platform and operations

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-70 | Docker Compose stack with PostgreSQL | ✅ | `docker compose up --build` |
| F-71 | Windows start/stop scripts | ✅ | `start.bat`, `stop.bat` |
| F-72 | Test suite | ✅ | 42 tests per README: spec behaviour table, ablations, concurrency (2/4/8 agents), crash, Hypothesis property tests, HTTP end-to-end |
| F-73 | CI pipeline | 🔲 | Backend tests + frontend build + secret scan |
| F-74 | JWT auth, RBAC, scoped agent tokens | 🔲 | See SECURITY.md |
| F-75 | Multi-tenancy with RLS | 🔲 | ADR-020 |

## 10. Known limitations (carry into any external description)
- Provider is a simulator modelled on documented behaviour, not a real provider sandbox.
- Agent errors come from an explicit error model.
- Baseline D's offline reviewer reuses the deterministic extractor and is optimistic.
- Experiments use SQLite (shared-cache in-memory); PostgreSQL is supported but not covered by automated tests.
- Latency numbers are in-process and say nothing about production performance.
- Results and impact claims are simulation-based; no customer deployment exists.
