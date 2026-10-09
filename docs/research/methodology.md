# Experimental methodology

Code: [`experiments/bench/`](../../experiments/bench/). Results: [results.md](results.md).

## Research question

Does an intent-consistent transaction protocol reduce incorrect and duplicate final financial
outcomes under timeouts, crashes, changed retries and concurrency, while still completing
legitimate requests?

## Hypotheses

Stated before reading the results; each maps to metrics defined below.

| # | Hypothesis | Primary metrics |
|---|---|---|
| H1 | IntentGuard (E) produces fewer duplicate effects than baselines A–D under lost responses, restarts with new request IDs, and concurrent agents | `duplicate_effects`; per-category correct rate |
| H2 | E never executes an agent proposal that differs from the authorization; any unintended effect it leaves comes from the provider, not the agent | `unintended_effects`; categories where E is not correct |
| H3 | E reports no outcome that the provider's ledger contradicts, and leaves no wrong money unflagged | `misreports`, `undetected_wrong_minor` |
| H4 | E's safety does not come at the cost of legitimate work | `completion_pct`, `false_blocks` |
| H5 | Each component either changes a safety metric when removed, or is backed up by another component, so that removing both does | Ablation table |

## Scenarios

`experiments/bench/scenarios.py`. For each seed, 300 scenarios are drawn from 30 categories with fixed
relative weights. **The seed controls the category mix**, not just identifiers, so different seeds
produce different mixes.

| Family | Categories (relative weight) |
|---|---|
| clean | `clean_refund_full` (8), `clean_refund_partial` (5), `multi_intent_same_order` (4), `over_refund_second_intent` (2) |
| agent_error | `agent_amount_x10` (5), `agent_amount_unit_confusion` (3), `agent_near_miss_order_same_customer` (5), `agent_transposed_order_other_customer` (3), `agent_wrong_customer` (2), `agent_wrong_currency` (2) |
| provider_fault | `fault_timeout_before_execution` (5), `fault_lost_response` (6), `fault_outage_503` (4), `fault_slow_settlement` (4), `fault_lost_response_delayed_visibility` (5), `fault_lookup_outage_after_lost_response` (3), `fault_provider_amount_mismatch_pending` (3), `fault_provider_amount_mismatch_completed` (3), `fault_cancel_rejected` (2) |
| runtime | `crash_before_send` (3), `crash_after_send` (5), `restart_changed_retry` (3), `concurrent_agents` (5), `concurrent_agents_lost_response` (2) |
| authorization | `auth_clean` (3), `auth_lost_response` (3), `auth_amount_mismatch_completed` (2), `auth_concurrent` (2), `auth_agent_near_miss_order` (2) |
| governance | `operator_revoked` (2) |

Every scenario builds a small world:

- **Near-miss order IDs.** A primary order, a sibling with the last two digits swapped for the
  *same* customer (`ORD-2041` → `ORD-2014`), and a transposed ID for *another* customer
  (`ORD-2401`). Order values are drawn from ₹1,200 to ₹60,000.
- **Partial refunds.** `clean_refund_partial`, and 35% of the other refund scenarios (except
  `clean_refund_full`), refund 20–80% of the order, so a duplicate is not masked by the provider's
  balance check.
- **A natural-language ticket** rendered from templates, with varied currency formats.
- **Ground truth per intent:** achievable → exactly one matching effect is correct; not
  achievable → no effect is correct.

Provider fault parameters vary per scenario: visibility lag 5, 10, 20, 45 or 90 s (so some lags
exceed the 30 s absence window), settle delays of 20–180 s, wrong-amount factors 0.5, 1.5 or 10,
1–2 outages, 1–8 lookup outages.

## Agent error model and runtime

`experiments/bench/agent.py`, `experiments/bench/runner.py`. The **same agent behaviour is used for every arm.**

- Error modes: ×10 amount, rupee/paisa unit confusion, near-miss order (same customer), transposed
  order (other customer), wrong customer, wrong currency.
- 40% of agent errors are **persistent** (`P_PERSISTENT_ERROR = 0.4`): they repeat on every
  re-proposal. Such intents are marked not achievable; the correct outcome is that nothing executes.
  Transient errors affect only the first proposal.
- Runtime: the agent retries the same request up to 2 times after an error or timeout (2 s
  backoff), re-proposes up to 3 times after a rejection, and after a crash restarts with a **new
  request ID**. In `restart_changed_retry` the restarted proposal is also corrupted.
- Concurrency: 2–4 agent threads work the same intent; the provider adds 3 ms of real latency so
  they overlap.
- Crashes are injected at two points in the engine (`after_attempt_recorded`,
  `after_provider_response`).

## Architectures (arms)

`experiments/bench/arms.py`. Every arm receives the same proposals, talks to the same simulator, and is scored
by the same oracle. Arms differ only in what stands between agent and provider.

| Arm | What stands between agent and provider |
|---|---|
| **A: direct provider access** | Nothing. No idempotency key, no checks |
| **B: fixed validation rules** | Order exists and belongs to the customer; currency matches the order; amount ≤ ₹50,000 agent cap; amount fits the order balance as tracked locally by the arm |
| **C: API idempotency alone** | The agent's `request_id` is sent as the provider idempotency key |
| **D: pre-execution reviewer** | A reviewer re-extracts the operation from the ticket and requires an exact match. Offline it uses the same deterministic extractor that defines correct proposals, so it is an **optimistic stand-in** for an LLM reviewer. `--llm-reviewer` uses a real LLM. It has no record of what already executed |
| **E: IntentGuard** | The full protocol (`ProtocolConfig()` defaults) |

### Ablations

IntentGuard with components switched off through `ProtocolConfig`, singly and in overlapping
pairs:

| Arm | Configuration |
|---|---|
| − intent binding | `intent_binding=False` |
| − effect dedup | `effect_dedup=False` |
| − reconciliation | `reconciliation=False` |
| − absence window | `absence_window_s=0` |
| − stable idempotency key | `stable_idempotency_key=False` |
| − state-aware recovery | `state_aware_recovery=False` |
| − serialization | `serialize_intent=False` |
| − dedup − stable key | `effect_dedup=False, stable_idempotency_key=False` |
| − absence window − stable key | `absence_window_s=0, stable_idempotency_key=False` |
| − reconciliation − stable key | `reconciliation=False, stable_idempotency_key=False` |

`ProtocolConfig` also has `readback_verification`; it is not ablated in the benchmark.

That is 15 arms in total: 4 baselines, E, and 10 ablations.

## Oracle

`experiments/bench/scoring.py`. After a **900 s simulated settlement horizon** (the runner advances the clock
to each arm's next due time so background work completes), each scenario is scored from the
**provider's ground-truth ledger** (`sim.all_transactions()`, ignoring search visibility),
identically for every arm.

- *Intended effect:* a live (`PENDING`/`COMPLETED`) transaction matching an achievable intent
  exactly (operation, order, customer, settled amount, currency).
- *Duplicate effect:* a second or later intended effect for the same intent.
- *Unintended effect:* any other live transaction on the scenario's orders, including effects of
  intents that should not execute.
- *Correct scenario:* every achievable intent has exactly one intended effect, non-achievable
  intents have none, and nothing unintended is live.

An arm's own bookkeeping is used only to count **misreports** (claims `COMPLETED` with no intended
effect, or `FAILED`/`NOT_EXECUTED` while one exists), whether it **flagged** a problem (a review
case or `DISCREPANCY`), and unresolved intents.

## Metrics

From `metric_definitions` in `summary.json`:

| Metric | Better | Definition |
|---|---|---|
| Correct scenarios (`correct_pct`) | higher | Every achievable intent fulfilled exactly once, nothing unintended live |
| Legitimate completion (`completion_pct`) | higher | Achievable intents with their intended effect at the horizon |
| Unsafe scenarios (`unsafe_scenarios`) | lower | Scenarios ending with any duplicate or unintended live money movement |
| Duplicate effects (`duplicate_effects`) | lower | Extra live effects for an intent beyond the first |
| Unintended effects (`unintended_effects`) | lower | Live effects matching no achievable intent |
| Wrong money moved (`wrong_money_minor`) | lower | Amount of duplicate + unintended effects still live at the horizon |
| Undetected wrong money (`undetected_wrong_minor`) | lower | Wrong money in scenarios where the system raised no flag |
| Reversed effects (`recovered_effects`) | higher | Transactions created and then cancelled/voided |
| Misreported outcomes (`misreports`) | lower | Claims success with no intended effect, or failure while one exists |
| False blocks (`false_blocks`) | lower | Achievable intents left unfulfilled after a correct proposal was rejected |
| Unresolved at horizon (`unresolved_intents`) | lower | Intents still reported in progress at the horizon |
| Human reviews (`review_cases`) | lower | Cases escalated to a human (the cost of safety) |
| Mean / p95 submit latency (`latency_mean_ms`, `latency_p95_ms`) | lower | Wall-clock time per agent submission, in-process provider |

## Seeds and statistics

- Seeds 42–51 (10 seeds) × 300 scenarios × 15 arms = 45,000 scenario runs.
- Each arm × seed cell is one job in a process pool (`--workers`, default CPU count − 1), with its
  own shared-cache in-memory SQLite database and simulator, on a simulated clock.
- Metrics are computed per seed; tables report the **mean over seeds** with a **95% bootstrap
  confidence interval over the 10 per-seed values** (10,000 resamples, percentile method), shown
  as ± half-width. Counts are per 300 scenarios. Per-category tables pool all seeds.

## Reproducing

```bash
cd experiments
python -m bench run --seeds 10 --start-seed 42 --scenarios 300   # full run (the recorded run took 795 s)
python -m bench run --seeds 2 --scenarios 60 --out results/quick  # quick check (~30 s)
python -m bench run --llm-reviewer                                # baseline D with a real LLM
python -m bench list-arms
```

`make bench-full` and `make bench-quick` run the same commands from the repository root. Output:
`experiments/results/<run_id>/` and `<out>/latest/` with `summary.md`, `summary.json` (served at
`/api/experiments/latest`) and `scenarios.csv` (one row per arm × seed × scenario). A run without
`--out` replaces `experiments/results/latest/`, the run the documentation cites.
