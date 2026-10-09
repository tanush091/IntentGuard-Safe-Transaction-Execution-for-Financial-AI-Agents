# Product requirements (as built)

This page states the problem, users, goals and scope of the research prototype in this
repository, as the code implements them today. The product direction (IntentGuard Recovery) is
specified in [../PRD.md](../PRD.md); [../FEATURES.md](../FEATURES.md) lists every feature with
its status. Where the two differ, the target documents describe what is planned and this page what
exists.

## Problem

An AI agent can read a support ticket and propose a refund. A successful API call does not show
that the *authorized* operation happened:

1. **Proposal drift.** The agent proposes something other than what was approved: ₹15,000
   instead of ₹1,500, `ORD-240` instead of `ORD-204`, rupees read as paise, the wrong customer or
   currency.
2. **Uncertain outcomes.** After a timeout the caller cannot tell whether the provider executed
   the operation. A blind retry can pay twice; giving up can drop a legitimate refund.
3. **Changed retries.** After a crash or restart the agent re-derives the operation and sends a
   new request ID. Idempotency keyed on the client's request ID treats it as a new payment.
4. **Unverified recovery.** Issuing a cancel call, or rolling back the agent's own state, is not
   the same as the provider confirming the reversal.

## Users

| User | Role in the code | Needs |
|---|---|---|
| Operator (support lead, billing) | `operator` | Authorize a specific refund or hold within a limit, and know the money moved exactly once |
| Reviewer (finance, compliance) | `reviewer` | See the cases the system cannot settle on its own, with the exact discrepancy and evidence, resolve them, and verify the audit chain |
| Admin | `admin` | Manage users, agent tokens, policies and the provider connection |
| AI agent | `agent` (service principal) | Turn a ticket into a structured proposal; it is never trusted to move money and never talks to the provider |
| Researcher | none (command line) | Reproduce the comparison against simpler architectures and see what each safeguard contributes |

Roles and what each may do: [overview.md](overview.md#roles).

## Goals

| # | Goal | How it is measured or tested |
|---|---|---|
| G1 | No duplicate financial effect for one authorization, including after timeouts, crashes, restarts with new request IDs and concurrent agents | `duplicate_effects` in the benchmark; concurrency and crash tests; property P1 |
| G2 | No effect that does not match the authorization (order, customer, amount, currency, operation) is executed by the gateway | `unintended_effects`; protocol-spec tests; property P2 |
| G3 | Never report an outcome the provider does not confirm; every wrong effect that cannot be reversed is escalated with its amount | `misreports`, `undetected_wrong_minor`; properties P3–P4; recovery tests |
| G4 | Still complete legitimate requests | `completion_pct`, `false_blocks` |
| G5 | Results are reproducible from a seed and scored the same way for every architecture | `python -m bench run`; one oracle in `experiments/bench/scoring.py` |
| G6 | Keep the agent outside the trust boundary | Scoped, short-lived agent tokens; role tests (`test_api_rbac.py`); the AI investigator only recommends and a deterministic gate decides (`test_investigator.py`) |
| G7 | A tamper-evident record of every decision and state change | Hash-chained audit log with append-only triggers; `GET /api/audit/verify`; property P5 |

The measured outcome against G1–G5 is in [../research/results.md](../research/results.md). The CI
quick benchmark fails on any duplicate effect, undetected wrong money or misreport of the full
protocol ([../testing/test-plan.md](../testing/test-plan.md#benchmark-safety-gate)).

## Scope

- **Operations:** refunds (primary) and payment-authorization holds (secondary, to test that the
  protocol transfers to a second transaction type). Cancellation is an operator action on an
  intent, not a separate operation.
- **Gateway** (`backend/gateway_api/`, engine in `backend/intentguard/`): durable operator
  authorizations (intents), deterministic proposal checks, an attempt ledger with a stable provider
  idempotency key per intent, read-back verification, reconciliation of unknown outcomes with an
  absence window, state-aware recovery, operator cancellation verified at the provider, human
  review cases with five resolutions, a hash-chained audit log, a background worker and crash
  recovery on startup. HTTP API under `/api`, described by `docs/api/openapi.json`.
- **Security:** email and password login (argon2id, lockout, rate limits), short-lived JWT access
  tokens with rotating refresh tokens (HttpOnly cookie for browsers), roles `operator`,
  `reviewer`, `admin`, and scoped, revocable agent service tokens. Admin policies: kill switch,
  maximum amount, separation of duties, attempt budget, absence window, unknown-review timeout.
- **Agent endpoint:** extracts a proposal from the intent's ticket with a deterministic rule
  extractor, or with an LLM (OpenAI-compatible, Ollama or Gemini) when `LLM_PROVIDER` is set.
  LLM output is validated against a strict schema and rejected, not repaired.
- **AI exception investigator** (`backend/investigator/`): classifies an exception, summarizes the
  evidence and recommends one action from a fixed set. A deterministic policy gate decides whether
  the action may run, and re-checks on fresh evidence when it is applied. Offline rules by default.
- **Reconciliation runs and webhooks:** matching runs compare the gateway's ledger with the
  provider order by order and record mismatches for a reviewer; they change nothing. Signed
  provider webhooks are verified, deduplicated and treated as hints (the gateway re-reads the
  transaction).
- **Provider simulator** (`backend/paysim/`, served by `backend/provider_api/`): pending
  settlement, state-dependent cancellation, idempotency keys with parameter fingerprints,
  eventually consistent search, per-order balance checks, ten injectable faults (eight on provider
  calls, two on webhook delivery), signed webhooks, state persisted across restarts.
- **Dashboard** (`frontend/`, React and Vite): login and role-based pages, live metrics, the four
  demo scenarios as one-click cards, intents with pipeline and timeline, exceptions with the AI
  investigator, review queue, reconciliation runs and mismatches, audit search and verification,
  latest experiment results, administration.
- **Benchmark** (`experiments/bench/`): seeded scenarios, baselines A–D, the full protocol E, ten
  ablations, one ground-truth oracle.
- **Tests and CI:** 127 pytest tests in `backend/tests/` (also run against PostgreSQL in CI), 19
  Vitest tests, a route contract check, a quick-benchmark safety gate, secret and dependency scans.
  See [../testing/test-plan.md](../testing/test-plan.md).

## Non-goals

- Real payment rails, real credentials or real money. The provider is a simulator only; no real
  provider adapter exists (planned in the target documents).
- Customer-facing login. Users are operators, reviewers and admins.
- Multi-tenancy. There is one merchant per deployment; row-level security is planned, not built.
- Currency conversion. A proposal must match the authorized currency exactly.
- Approvals expressed as ranges ("up to ₹2,000") or multi-line refunds. An intent is one exact
  amount, and a smaller proposed amount is rejected too.
- Multi-step workflows (cancel order, then refund, then voucher) and their compensation.
- Production performance claims. Latency figures are local, in-process measurements.
- Validated multi-gateway deployment. No test runs two gateway processes against one database,
  and rate limits are kept in process memory
  ([../research/limitations.md](../research/limitations.md)).
