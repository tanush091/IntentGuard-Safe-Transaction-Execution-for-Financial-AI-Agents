# IntentGuard: Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes

**Status:** Research manuscript draft. All results are produced by `python -m bench run` and can be reproduced from this repository.
**Results artifact:** `experiments/results/20261005T141650Z/` (also `experiments/results/latest/`)
**Evaluation:** 300 synthetic scenarios per seed × 10 seeds (42–51) × 15 architectures = 45,000 scenario runs

> Correction notice. An earlier draft of this manuscript reported results (98.4% completion,
> 10-seed confidence intervals, ablation table) that were not produced by a measured run: the
> script that generated them wrote fixed values. Those numbers have been withdrawn. Every number
> below is computed from per-scenario results by `bench/report.py`.

---

## Abstract

AI agents with tool access can turn a customer-support conversation into a refund, but a
successful API call does not establish that the *authorized* financial effect occurred. Agents
select near-miss orders, change amounts, and repeat operations after timeouts. After a restart they
may issue a differently shaped request for the same instruction, which client-generated idempotency
keys cannot recognise. We present **IntentGuard**, a protocol in which the agent can only *propose*.
A gateway binds every proposal to a durable operator authorization and owns submission, retries and
recovery. It uses one provider idempotency key per authorization, persists every attempt before
the provider call, verifies effects by reading the provider back, and reconciles unknown outcomes.
It treats "not found" as evidence of no effect only after a provider-visibility window, cancels
unintended effects only when the provider allows it and verifies the cancellation, and otherwise
escalates.

We evaluate on a seeded benchmark of 30 scenario categories (agent errors with near-miss
identifiers, provider faults, crashes, changed retries, concurrent agents, a second transaction
type, and operator revocation). Every architecture receives identical agent behaviour and faults,
and all are scored by one oracle against the provider's ground-truth ledger.
- **IntentGuard** ends 95.6% ± 0.4% of scenarios fully correct, with **zero duplicate effects, zero misreported outcomes and zero undetected wrong money**.
- **Direct access, static validation rules, API idempotency alone, and a pre-execution reviewer** reach 70.5%–84.0%, leave 8.1–15.4 duplicate effects per 300 scenarios, misreport 99–139 outcomes, and leave ₹12.1–15.2 lakh of wrong money undetected.
- **IntentGuard's remaining failures** are exclusively provider-side wrong-amount transactions that the provider no longer allows to be reversed. All are escalated with the exact discrepancy.
- **Ablations show defence in depth.** No single component's removal changes money outcomes much, while removing pairs of overlapping safeguards brings back duplicates (up to 9.8 per 300 scenarios) and misreports (up to 43.6).

---

## 1. Introduction

LLM agents with tool calling can extract a customer, an order and an amount from a ticket and call a
payment provider. In financial systems, automation is not safety. Four failure modes matter:

1. **Proposal drift.** The agent proposes something other than what was authorized: ₹15,000 instead of ₹1,500, `ORD-240` instead of `ORD-204`, rupees read as paise, the wrong currency.
2. **Uncertain outcomes.** After a timeout, the caller cannot tell whether the provider executed the operation. Retrying blindly creates duplicates; giving up blindly loses legitimate work.
3. **Changed retries.** After a crash, an agent re-derives the operation and sends a new request ID. Provider idempotency keyed on the client's request ID treats it as new.
4. **Unverified recovery.** Reporting an effect as "reversed" because a cancel call was issued, or because the agent's internal state was rolled back, is not the same as the provider confirming the reversal.

## 2. Identity model

IntentGuard never conflates four objects:

| Object | Owner | Meaning |
|---|---|---|
| Intent (`intent_id`) | Operator | The authorized business operation: customer, order, operation, amount, currency |
| Proposal | Agent | What the agent asks for; never trusted on its own |
| Attempt (`attempt_id`) | Gateway | One provider API call, persisted *before* the call |
| Effect | Provider | A transaction observed at the provider and attributed to an intent |

Intent state is *derived* from attempts and effects and checked against an explicit transition
relation (`intentguard/domain.py`). A new agent attempt can never create a new authorization.

## 3. Related work and claimed contribution

Provider idempotency keys (e.g. Stripe's `Idempotency-Key`) deduplicate requests that reuse a key.
Saga-style compensation reverses completed steps. LLM tool-safety work typically adds pre-execution
review. None of these is new here. The contribution claimed and tested is narrower: **a
combination for non-deterministic agent callers in which (i) idempotency is anchored to the
authorization rather than the request, (ii) "absent at the provider" is treated as evidence only
after a visibility window, (iii) compensation is state-aware and verified, and (iv) all claims are
derived from provider observations.** Section 6 measures where this combination differs from each
simpler alternative, and the ablations show which parts overlap.

## 4. Protocol

```
decide   (locked)   evaluate checks against the durable authorization and ledger; record the decision
reserve  (same tx)  record an attempt with key ig-<intent>-g<generation>; intent -> IN_FLIGHT
execute  (no lock)  call the provider with intent_id/attempt_id metadata
verify   (no lock)  read the transaction back from the provider
absorb   (locked)   record the effect (INTENDED / DUPLICATE / MISMATCH); derive the intent state
drive               reconcile unknown outcomes; recover discrepancies; retry only on verified absence
```

**Checks.** Operator active and permitted for the operation and amount (re-checked at proposal time).
Operation, customer, order, currency and amount equal to the intent. Amount within the order's
remaining balance across *all* intents. Intent not already fulfilled, not in flight, not held for
review, and within its attempt budget.

**States.** `AUTHORIZED, IN_FLIGHT, PENDING_SETTLEMENT, OUTCOME_UNKNOWN, RETRYABLE, DISCREPANCY, NEEDS_REVIEW, COMPLETED, REVOKED, CLOSED`.
A completed intent can be reopened (`COMPLETED → DISCREPANCY`) if a late-visible duplicate is found
during the post-completion watch.

**Reconciliation.** An attempt without a response is `UNKNOWN`, never "failed". The gateway reads
known transactions by ID (strongly consistent) and searches the order's transactions
(eventually consistent), attributing results by `intent_id`, `attempt_id` or idempotency key. An
`UNKNOWN` attempt becomes `NO_EFFECT` only if a successful search happens at least
`absence_window_s` (30 s) after the attempt. Only then does the gateway retry, under the same key.
If the provider cannot be queried, the intent escalates to review after 300 s instead of being
retried.

**Recovery policy.**

| Observed unintended effect | Action |
|---|---|
| Refund `PENDING` | cancel → read back → `CANCELLED` verified, or escalate |
| Refund `COMPLETED` | escalate with discrepancy amount; never reported as reversed |
| Authorization hold `PENDING`/`COMPLETED` | void → read back → verified, or escalate |
| Cancel rejected / cannot be verified after 3 tries | escalate |

After a verified reversal the key generation increments, so a retry executes afresh instead of
replaying the reversed transaction.

**Durability.** Attempts are written before the provider call. After a restart, attempts left
`SUBMITTING` by a previous process become `UNKNOWN` and are reconciled. The database enforces at most
one live intended effect per intent (partial unique index) and an append-only, per-intent
hash-chained audit log (triggers reject `UPDATE`/`DELETE`; `audit.verify` detects rewritten history).

## 5. Experimental method

**Provider.** `paysim` models: refunds that settle from `PENDING` to `COMPLETED`; cancellation only
while a refund is pending; authorization holds that can be voided while live; idempotency keys with
parameter fingerprints (reuse with different parameters is rejected); per-order balance and
ownership checks; and order search that is eventually consistent while lookup by ID is consistent.
Faults: outage (503), timeout before execution, lost response after execution, slow settlement,
delayed visibility, provider-side amount mismatch, rejected cancellation, and lookup outage.
Time is simulated, so behaviour is deterministic per seed.

**Scenarios.** For each seed, 300 scenarios are drawn from 30 categories with fixed relative
weights, so the mix differs between seeds. The categories fall into six families: clean, agent
error, provider fault, runtime, authorization, and governance. Every scenario builds a small world
with near-miss order IDs (e.g. `ORD-2041` / `ORD-2014` for the same customer, `ORD-2401` for
another customer) and a natural-language ticket. Agent errors are drawn from an explicit error
model; 40% of them are *persistent*, repeating on re-proposal. Scenarios with persistent errors are
marked not achievable: the correct outcome is that nothing executes.

**Agent runtime (identical for all arms).** The agent submits a proposal. It retries the same request
up to twice after an error or timeout (with 2 s backoff), re-proposes up to three times after a
rejection, and on a crash restarts with a new request ID. In `restart_changed_retry` the restarted
proposal is also corrupted. Concurrent scenarios run 2–4 agent threads on the same intent.

**Arms.**
- **A: direct access.** The agent calls the provider; no key.
- **B: fixed validation rules.** Order exists and belongs to the customer, currency matches the order, amount ≤ ₹50,000 agent cap, and the amount fits the order balance as tracked locally.
- **C: API idempotency alone.** The agent's request ID is the provider idempotency key.
- **D: pre-execution reviewer.** The reviewer re-extracts the operation from the ticket and requires an exact match. *Offline it uses the same deterministic extractor that generates correct proposals, so it is an optimistic stand-in for an LLM reviewer.* `--llm-reviewer` uses a real LLM.
- **E: IntentGuard.**
- **Ablations.** E with components disabled through `ProtocolConfig`, singly and in overlapping pairs.

**Oracle.** After a 900 s settlement horizon, each scenario is scored from the provider's
ground-truth ledger, identically for every arm (`bench/scoring.py`). A scenario is *correct* if
every achievable intent has exactly one matching live effect, non-achievable intents have none, and
nothing unintended is live. An arm's own bookkeeping is used only to count *misreports*
(claiming success with no intended effect, or failure while one exists) and whether it raised a
flag. Values are means per seed with 95% bootstrap confidence intervals over the 10 seeds; counts
are per 300 scenarios.

## 6. Results

### Table 1: Baselines vs. IntentGuard (10 seeds × 300 scenarios)

| Architecture | Correct scenarios | Legitimate completion | Unsafe scenarios | Duplicate effects | Unintended effects | Wrong money moved | Undetected wrong money | Misreported outcomes | False blocks | Human reviews | Mean submit latency (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A: direct provider access | 74.5% ± 0.8% | 84.2% ± 1.0% | 76.5 ± 2.6 | 14.4 ± 2.2 | 63.2 ± 2.8 | ₹1,519,275 ± ₹205,596 | ₹1,519,275 ± ₹205,596 | 138.5 ± 5.5 | 0.0 | 0.0 | 0.90 ± 0.06 |
| B: fixed validation rules | 70.5% ± 0.9% | 79.9% ± 1.1% | 75.1 ± 2.7 | 14.4 ± 2.2 | 61.8 ± 3.1 | ₹1,213,275 ± ₹226,707 | ₹1,213,275 ± ₹226,707 | 132.4 ± 6.1 | 13.4 ± 2.6 | 0.0 | 0.54 ± 0.07 |
| C: API idempotency alone | 76.6% ± 1.0% | 84.2% ± 1.0% | 70.3 ± 2.9 | 8.1 ± 2.1 | 63.2 ± 2.8 | ₹1,485,395 ± ₹207,673 | ₹1,485,395 ± ₹207,673 | 99.3 ± 4.4 | 0.0 | 0.0 | 1.03 ± 0.07 |
| D: pre-execution reviewer | 84.0% ± 1.4% | 89.9% ± 1.2% | 48.1 ± 4.1 | 15.4 ± 2.4 | 33.8 ± 4.1 | ₹1,404,836 ± ₹199,899 | ₹1,404,836 ± ₹199,899 | 112.9 ± 6.4 | 0.0 | 0.0 | 0.91 ± 0.06 |
| **E: IntentGuard** | **95.6% ± 0.4%** | **95.3% ± 0.4%** | **13.3 ± 1.1** | **0.0** | **13.3 ± 1.1** | ₹550,892 ± ₹191,442 | **₹0** | **0.0** | **0.0** | 13.3 ± 1.1 | 39.07 ± 2.23 |

### Table 2: Correct-scenario rate in selected categories (all seeds pooled)

| Category | A | C | D | E |
|---|---|---|---|---|
| near-miss order, same customer | 38% | 38% | 100% | 100% |
| lost response after execution | 81% | 100% | 81% | 100% |
| lost response + delayed visibility | 86% | 100% | 86% | 100% |
| crash after send (restart, new request ID) | 81% | 81% | 81% | 100% |
| restart with changed proposal | 55% | 55% | 75% | 100% |
| concurrent agents | 79% | 79% | 79% | 100% |
| provider wrong amount, still pending | 0% | 0% | 0% | 100% |
| operator revoked before execution | 0% | 0% | 0% | 100% |

Baseline rates in duplicate-prone categories are above 0% because the provider's own balance check
rejects a second *full* refund. Duplicates surface mainly for partial refunds.

### Findings

1. **Changed retries defeat request-scoped idempotency.** C removes in-session duplicates from lost responses (100% correct there) but does no better than A after a restart or with concurrent agents (81% and 79%). Anchoring the key to the intent closes both (E: 100%).
2. **Pre-execution review is not post-execution safety.** Even an optimistic reviewer (D) that catches every agent error still leaves 15.4 duplicates and ₹14.0 lakh of wrong money per 300 scenarios, because it cannot see timeouts, restarts, concurrency or provider behaviour.
3. **Static rules cost completions and still miss near misses.** B blocks 13.4 legitimate requests per 300 scenarios (the per-operation cap) yet still executes near-miss orders that belong to the same customer.
4. **What IntentGuard does not fix.** E's 13.3 unsafe scenarios per 300 are all provider-side wrong amounts that can no longer be reversed: completed refunds (87 scenarios pooled, ₹50.5 lakh) and rejected cancellations (46 scenarios, ₹4.6 lakh). Every one is escalated with its discrepancy (undetected wrong money: ₹0), and none is reported as reversed. The 15.0 effects per 300 scenarios that E *did* reverse were all verified.
5. **Honest outcome reporting.** Baselines misreport 99–139 outcomes per 300 scenarios, mostly reporting success for an executed wrong operation. E misreports none.
6. **Cost.** E adds about 38 ms mean (93 ms p95) per submission in this in-process SQLite setup, and asks a human to review 13.3 cases per 300 scenarios.

## 7. Ablations

### Table 3: IntentGuard with components removed

| Variant | Correct scenarios | Unsafe scenarios | Duplicate effects | Unintended effects | Undetected wrong money | Misreported outcomes | Human reviews |
|---|---|---|---|---|---|---|---|
| Full protocol | 95.6% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹0 | 0.0 | 13.3 ± 1.1 |
| − intent binding | 87.0% ± 1.4% | 36.8 ± 4.4 | 0.0 | 36.8 ± 4.4 | ₹0 | 0.0 | 40.3 ± 3.6 |
| − effect dedup | 95.6% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹0 | 0.0 | 13.3 ± 1.1 |
| − reconciliation | 95.6% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹0 | 0.0 | 13.3 ± 1.1 |
| − absence window | 95.6% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹0 | 0.0 | 13.3 ± 1.1 |
| − stable idempotency key | 95.3% ± 0.4% | 14.0 ± 1.2 | 0.7 ± 0.6 | 13.3 ± 1.1 | ₹0 | 5.1 ± 1.2 | 14.0 ± 1.2 |
| − state-aware recovery | 95.6% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹550,892 ± ₹191,442 | 0.0 | 0.0 |
| − serialization | 95.6% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹0 | 0.0 | 13.3 ± 1.1 |
| − dedup − stable key | 92.6% ± 0.9% | 22.1 ± 2.8 | 9.8 ± 2.9 | 13.3 ± 1.1 | ₹0 | 5.1 ± 1.2 | 22.1 ± 2.8 |
| − absence window − stable key | 94.9% ± 0.4% | 15.2 ± 1.1 | 1.9 ± 0.8 | 13.3 ± 1.1 | ₹6,050 ± ₹4,813 | 11.4 ± 2.6 | 13.3 ± 1.1 |
| − reconciliation − stable key | 93.3% ± 0.4% | 20.1 ± 1.2 | 6.8 ± 1.1 | 13.3 ± 1.1 | ₹140 ± ₹170 | 43.6 ± 3.1 | 19.9 ± 1.0 |

**Interpretation.** The protocol is redundant by design, and the ablations make that visible.

- **Defences that overlap.** The intent-anchored idempotency key, the state/ledger gate, reconciliation and the absence window each defend against duplicates. Removing any one alone leaves money outcomes unchanged, because the provider replays the stable key. Removing the key *together with* any one of the others brings back duplicates (1.9–9.8 per 300 scenarios) and misreports (5.1–43.6).
- **Components without overlap.** Intent binding has no overlapping safeguard: without it, unsafe scenarios nearly triple (13.3 → 36.8). State-aware recovery is the only source of *detection*: without it, the full ₹5.5 lakh of wrong money goes undetected, and the system reports the intents as completed while wrong refunds remain live.
- **Serialization** shows no aggregate effect in this benchmark because the stable key absorbs the race. The deterministic two-agent race in `tests_intentguard/test_ablations.py` shows that, with the key also removed, both agents pass the gate and two refunds execute.

## 8. Verification beyond the benchmark

The test suite (42 tests) includes:
- one test per row of the specification's behaviour table;
- a test per ablation showing the behaviour change it causes;
- 2/4/8 concurrent agents producing exactly one effect;
- gateway crashes at both injection points;
- Hypothesis property tests over random faults, wrong proposals, crashes and restarts, checking that no unescalated duplicate or unintended effect exists, that `COMPLETED` is always true at the provider, and that the audit chain verifies;
- end-to-end HTTP tests through the real provider API.

## 9. Limitations and threats to validity

1. **Simulated provider.** Behaviour is modelled on documented provider semantics, not validated against a provider sandbox.
2. **Scripted agent errors.** Error types and rates come from an explicit model, not from observed LLM behaviour. An evaluation with real LLM agents is future work (`--llm-reviewer` and the gateway's agent endpoint support it).
3. **Optimistic baseline D.** Offline, it shares the extractor that defines correct proposals, which overstates what an LLM reviewer would catch.
4. **Absence window.** It is a protocol parameter. If the provider's visibility lag exceeds it *and* the stable key is unavailable, duplicates can occur (Table 3). Scenarios with lags longer than the window are included.
5. **Storage.** Experiments run on SQLite. PostgreSQL code paths (row locks, triggers) exist but were not exercised by the automated tests.
6. **Latency.** Figures are in-process wall-clock times and do not predict production latency.
7. **Provenance.** This run was produced from a working tree that had not been committed at the time (`git_commit` 283c6bb plus local changes). Rerun after committing for a clean provenance record.

## 10. Conclusion

When the agent is untrusted and the network is unreliable, safety comes from what the gateway can
*observe and verify*, not from what the agent or the API response claims. Binding proposals to
durable authorizations, anchoring idempotency to the authorization, reconciling before retrying,
and verifying every reversal eliminated duplicates, misreports and undetected wrong money in this
benchmark. The irreducible remainder is effects that the provider no longer lets anyone reverse.
Those are escalated, never hidden.
