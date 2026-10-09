# Product requirements

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

| User | Needs |
|---|---|
| Operator (support lead, billing) | Approve a specific refund or hold, and know the money moved exactly once |
| AI agent | Turn a ticket into a structured proposal; it is never trusted to move money itself |
| Reviewer | See the cases the system cannot settle on its own, with the exact discrepancy, and resolve them |
| Auditor / finance | Check that the record of decisions and effects has not been rewritten |
| Researcher | Reproduce the comparison against simpler architectures and see what each safeguard contributes |

## Goals

| # | Goal | How it is measured |
|---|---|---|
| G1 | No duplicate financial effect for one authorization, including after timeouts, crashes, restarts with new request IDs and concurrent agents | `duplicate_effects` in the benchmark; concurrency and crash tests |
| G2 | No effect that does not match the authorization (order, customer, amount, currency, operation) is executed by the gateway | `unintended_effects`; protocol-spec tests |
| G3 | Never report an outcome the provider does not confirm; every wrong effect that cannot be reversed is escalated with its amount | `misreports`, `undetected_wrong_minor`; property tests P3–P4 |
| G4 | Still complete legitimate requests | `completion_pct`, `false_blocks` |
| G5 | Results are reproducible from a seed and scored the same way for every architecture | `python -m bench run`; one oracle in `experiments/bench/scoring.py` |

The measured outcome against these goals is in [../research/results.md](../research/results.md).

## Scope

- **Operations:** refunds (primary) and payment-authorization holds (secondary, to test that the
  protocol transfers to a second transaction type).
- **Gateway:** durable operator authorizations (intents), proposal checks, attempt ledger with a
  stable provider idempotency key per intent, read-back verification, reconciliation of unknown
  outcomes, state-aware recovery, human review cases, hash-chained audit log, background worker,
  crash recovery on startup. HTTP API in `backend/gateway_api/`.
- **Agent endpoint:** extracts a proposal from the intent's ticket with a deterministic rule
  extractor, or with an LLM (OpenAI, Ollama or Gemini) when `LLM_PROVIDER` is set in the
  environment. The agent never talks to the provider.
- **Provider simulator** (`backend/paysim/`, served by `backend/provider_api/`): pending
  settlement, state-dependent cancellation, idempotency keys with parameter fingerprints,
  eventually consistent search, per-order balance checks, eight injectable faults, state persisted
  across restarts.
- **Dashboard** (`frontend/`, React + Vite): live metrics, intents and timelines, review queue,
  audit verification, latest experiment results.
- **Benchmark** (`experiments/bench/`): seeded scenarios, baselines A–D, the full protocol, ten
  ablations, one ground-truth oracle.
- **Tests:** 42 pytest tests in `backend/tests/`.

## Non-goals

- Real payment rails, real credentials or real money. The provider is a simulator only.
- User authentication and role enforcement. The API has none; it is a research prototype.
- Currency conversion. A proposal must match the authorized currency exactly.
- Approvals expressed as ranges ("up to ₹2,000") or multi-line refunds. An intent is one exact amount.
- Multi-step workflows (cancel order, then refund, then voucher) and their compensation.
- Production performance claims. Latency figures are local, in-process measurements.
- Validated multi-gateway deployment and PostgreSQL in automated tests (the code supports both;
  neither is exercised by the test suite; see [../research/limitations.md](../research/limitations.md)).
