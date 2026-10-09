# Results

Every number on this page is copied from
[`experiments/results/latest/summary.md`](../../experiments/results/latest/summary.md)
(run `20261005T141650Z`, also kept as
[`experiments/results/20261005T141650Z/`](../../experiments/results/20261005T141650Z/)). Nothing
here is computed by hand. How the numbers are produced: [methodology.md](methodology.md).
What they do not show: [limitations.md](limitations.md).

**Setup.** 10 seeds (42–51) × 300 scenarios per seed; the scenario mix is sampled per seed.
Values are the mean per seed with a 95% bootstrap CI over seeds (± half-width). Counts are per 300
scenarios. All arms receive identical agent behaviour and provider faults and are scored by the
same oracle against the provider's ground-truth ledger. Latency is in milliseconds, measured
in-process.

**Provenance.** The run metadata records commit `283c6bb`, which does not contain the benchmark
code; the run was made from a working tree that was committed afterwards as `2bbb6a9`.
**Reproduction check (2026-10-09).** A full rerun (same seeds and settings) from the committed,
restructured code (`54398b2`) produced an identical `scenarios.csv` (every per-scenario row the
same) and identical means and confidence intervals for every metric except latency. Latency is
wall-clock time and differed, as expected on a machine under different load. The rerun was
written to a scratch directory; `latest/` was not replaced.

## Baselines vs. IntentGuard

| Architecture | Correct scenarios | Legitimate completion | Unsafe scenarios | Duplicate effects | Unintended effects | Wrong money moved | Undetected wrong money | Misreported outcomes | False blocks | Human reviews | Mean submit latency |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A: direct provider access | 74.5% ± 0.8% | 84.2% ± 1.0% | 76.5 ± 2.6 | 14.4 ± 2.2 | 63.2 ± 2.8 | ₹1,519,275 ± ₹205,596 | ₹1,519,275 ± ₹205,596 | 138.5 ± 5.5 | 0.0 | 0.0 | 0.90 ± 0.06 |
| B: fixed validation rules | 70.5% ± 0.9% | 79.9% ± 1.1% | 75.1 ± 2.7 | 14.4 ± 2.2 | 61.8 ± 3.1 | ₹1,213,275 ± ₹226,707 | ₹1,213,275 ± ₹226,707 | 132.4 ± 6.1 | 13.4 ± 2.6 | 0.0 | 0.54 ± 0.07 |
| C: API idempotency alone | 76.6% ± 1.0% | 84.2% ± 1.0% | 70.3 ± 2.9 | 8.1 ± 2.1 | 63.2 ± 2.8 | ₹1,485,395 ± ₹207,673 | ₹1,485,395 ± ₹207,673 | 99.3 ± 4.4 | 0.0 | 0.0 | 1.03 ± 0.07 |
| D: pre-execution reviewer | 84.0% ± 1.4% | 89.9% ± 1.2% | 48.1 ± 4.1 | 15.4 ± 2.4 | 33.8 ± 4.1 | ₹1,404,836 ± ₹199,899 | ₹1,404,836 ± ₹199,899 | 112.9 ± 6.4 | 0.0 | 0.0 | 0.91 ± 0.06 |
| E: IntentGuard (full protocol) | 95.6% ± 0.4% | 95.3% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹550,892 ± ₹191,442 | ₹0 | 0.0 | 0.0 | 13.3 ± 1.1 | 39.07 ± 2.23 |

## Ablations (IntentGuard with components removed)

| Architecture | Correct scenarios | Legitimate completion | Unsafe scenarios | Duplicate effects | Unintended effects | Wrong money moved | Undetected wrong money | Misreported outcomes | False blocks | Human reviews | Mean submit latency |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E: IntentGuard (full protocol) | 95.6% ± 0.4% | 95.3% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹550,892 ± ₹191,442 | ₹0 | 0.0 | 0.0 | 13.3 ± 1.1 | 39.07 ± 2.23 |
| IntentGuard − intent binding | 87.0% ± 1.4% | 89.6% ± 0.8% | 36.8 ± 4.4 | 0.0 | 36.8 ± 4.4 | ₹643,316 ± ₹186,795 | ₹0 | 0.0 | 0.0 | 40.3 ± 3.6 | 45.18 ± 1.13 |
| IntentGuard − effect dedup | 95.6% ± 0.4% | 95.3% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹550,892 ± ₹191,442 | ₹0 | 0.0 | 0.0 | 13.3 ± 1.1 | 43.59 ± 1.66 |
| IntentGuard − reconciliation | 95.6% ± 0.4% | 95.3% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹550,892 ± ₹191,442 | ₹0 | 0.0 | 0.0 | 13.3 ± 1.1 | 36.01 ± 0.92 |
| IntentGuard − absence window | 95.6% ± 0.4% | 95.3% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹550,892 ± ₹191,442 | ₹0 | 0.0 | 0.0 | 13.3 ± 1.1 | 35.57 ± 1.47 |
| IntentGuard − stable idempotency key | 95.3% ± 0.4% | 95.3% ± 0.4% | 14.0 ± 1.2 | 0.7 ± 0.6 | 13.3 ± 1.1 | ₹554,512 ± ₹192,902 | ₹0 | 5.1 ± 1.2 | 0.0 | 14.0 ± 1.2 | 27.17 ± 1.38 |
| IntentGuard − state-aware recovery | 95.6% ± 0.4% | 96.0% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹550,892 ± ₹191,442 | ₹550,892 ± ₹191,442 | 0.0 | 0.0 | 0.0 | 39.06 ± 2.11 |
| IntentGuard − serialization | 95.6% ± 0.4% | 95.3% ± 0.4% | 13.3 ± 1.1 | 0.0 | 13.3 ± 1.1 | ₹550,892 ± ₹191,442 | ₹0 | 0.0 | 0.0 | 13.3 ± 1.1 | 42.81 ± 2.88 |
| IntentGuard − dedup − stable key | 92.6% ± 0.9% | 95.3% ± 0.4% | 22.1 ± 2.8 | 9.8 ± 2.9 | 13.3 ± 1.1 | ₹600,697 ± ₹198,774 | ₹0 | 5.1 ± 1.2 | 0.0 | 22.1 ± 2.8 | 42.65 ± 2.50 |
| IntentGuard − absence window − stable key | 94.9% ± 0.4% | 95.3% ± 0.4% | 15.2 ± 1.1 | 1.9 ± 0.8 | 13.3 ± 1.1 | ₹556,942 ± ₹193,470 | ₹6,050 ± ₹4,813 | 11.4 ± 2.6 | 0.0 | 13.3 ± 1.1 | 38.66 ± 0.75 |
| IntentGuard − reconciliation − stable key | 93.3% ± 0.4% | 95.3% ± 0.4% | 20.1 ± 1.2 | 6.8 ± 1.1 | 13.3 ± 1.1 | ₹585,932 ± ₹191,054 | ₹140 ± ₹170 | 43.6 ± 3.1 | 0.0 | 19.9 ± 1.0 | 45.36 ± 3.07 |

## Correct-scenario rate by scenario family (all seeds pooled)

| Architecture | agent_error | authorization | clean | governance | provider_fault | runtime |
|---|---|---|---|---|---|---|
| A: direct provider access | 60.2% | 73.4% | 100.0% | 0.0% | 69.7% | 80.9% |
| B: fixed validation rules | 57.1% | 67.9% | 95.9% | 1.8% | 66.0% | 75.5% |
| C: API idempotency alone | 60.2% | 73.4% | 100.0% | 0.0% | 76.1% | 80.9% |
| D: pre-execution reviewer | 100.0% | 84.1% | 100.0% | 0.0% | 69.7% | 83.7% |
| E: IntentGuard (full protocol) | 100.0% | 100.0% | 100.0% | 100.0% | 86.2% | 100.0% |
| IntentGuard − intent binding | 60.2% | 93.3% | 100.0% | 100.0% | 86.2% | 100.0% |
| IntentGuard − effect dedup | 100.0% | 100.0% | 100.0% | 100.0% | 86.2% | 100.0% |
| IntentGuard − reconciliation | 100.0% | 100.0% | 100.0% | 100.0% | 86.2% | 100.0% |
| IntentGuard − absence window | 100.0% | 100.0% | 100.0% | 100.0% | 86.2% | 100.0% |
| IntentGuard − stable idempotency key | 100.0% | 100.0% | 100.0% | 100.0% | 85.5% | 100.0% |
| IntentGuard − state-aware recovery | 100.0% | 100.0% | 100.0% | 100.0% | 86.2% | 100.0% |
| IntentGuard − serialization | 100.0% | 100.0% | 100.0% | 100.0% | 86.2% | 100.0% |
| IntentGuard − dedup − stable key | 100.0% | 100.0% | 100.0% | 100.0% | 85.5% | 83.7% |
| IntentGuard − absence window − stable key | 100.0% | 100.0% | 100.0% | 100.0% | 84.3% | 100.0% |
| IntentGuard − reconciliation − stable key | 100.0% | 100.0% | 100.0% | 100.0% | 79.8% | 98.8% |

## Where the full protocol is not correct

Categories in which IntentGuard ended a scenario in a non-correct state (all seeds pooled).

| Category | Scenarios | Correct | Unsafe | Wrong money | Human reviews |
|---|---|---|---|---|---|
| fault_cancel_rejected | 46 | 0.0% | 46 | ₹457,492 | 46 |
| fault_provider_amount_mismatch_completed | 87 | 0.0% | 87 | ₹5,051,426 | 87 |

## Reading the tables

- **Duplicates.** IntentGuard (E) has 0.0 duplicate effects; the baselines have 8.1 to 15.4 per
  300 scenarios.
- **Misreports and undetected wrong money.** E has 0.0 misreported outcomes and ₹0 undetected
  wrong money. For every baseline, undetected wrong money equals wrong money moved: none of them
  flags anything.
- **What E does not fix.** E's remaining unsafe scenarios (13.3 per 300) all fall in two
  categories: `fault_provider_amount_mismatch_completed` (87 scenarios, ₹5,051,426) and
  `fault_cancel_rejected` (46 scenarios, ₹457,492), where the provider itself moved a wrong
  amount and does not allow a reversal. Every one ended in a human review (87 and 46 reviews).
- **Completion.** E's legitimate completion is 95.3% ± 0.4%, against 79.9% to 89.9% for the
  baselines, with 0.0 false blocks. B is the only arm with false blocks (13.4 ± 2.6).
- **Cost.** E's mean submit latency is 39.07 ± 2.23 ms against 0.54 to 1.03 ms for the baselines,
  and it opens 13.3 ± 1.1 human reviews per 300 scenarios.
- **Ablations.** Removing intent binding raises unsafe scenarios from 13.3 ± 1.1 to 36.8 ± 4.4.
  Removing state-aware recovery leaves the same wrong money (₹550,892 ± ₹191,442) but all of it
  undetected, with 0.0 human reviews. Removing effect dedup, reconciliation, the absence window
  or serialization alone leaves every metric except latency unchanged from the full protocol.
  Removing effect dedup, the absence window or reconciliation *together with* the stable key
  brings back duplicate effects (9.8 ± 2.9, 1.9 ± 0.8 and 6.8 ± 1.1 respectively) and misreports
  (5.1 ± 1.2, 11.4 ± 2.6 and 43.6 ± 3.1). Serialization together with the stable key is not
  measured by the benchmark; `test_serialization_off_lets_concurrent_agents_both_pass_the_gate`
  covers that combination.
- **Families.** E is 100.0% correct in every family except provider_fault (86.2%).

The full metric definitions are at the end of `summary.md` and in [methodology.md](methodology.md#metrics).
