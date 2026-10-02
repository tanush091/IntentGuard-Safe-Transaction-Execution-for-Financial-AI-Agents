# 14. Ablation Study Framework

## Component Isolation and Failure Attribution

To evaluate the contribution of each individual subsystem within IntentGuard, we systematically disable one major component at a time and execute identical scenario sweeps.

---

## 1. Ablation Configurations

| Ablation ID | Removed Component | Hypothesized Failure Mode Exposed |
| :--- | :--- | :--- |
| **Ablation 1** | Remove Safety Gateway (`no_gateway`) | Hallucinated amounts, orders, and unauthorized operations pass directly to the provider. |
| **Ablation 2** | Remove Reconciliation (`no_reconciliation`) | `UNKNOWN` outcomes cannot be resolved; blind retries cause duplicate payouts. |
| **Ablation 3** | Remove Durable Intent Record (`no_intent_record`) | System cannot verify semantic bounds; loses baseline for recovery decisions. |
| **Ablation 4** | Remove Duplicate Detection (`no_duplicate_detection`) | Replay attacks, restarted agents, and concurrent runs cause multiple financial settlements. |
| **Ablation 5** | Remove State-Aware Recovery (`no_recovery`) | Incorrect effects cannot be cancelled; unresolved discrepancies remain in limbo. |
| **Ablation 6** | Remove Provider-State Verification (`no_provider_verification`) | System relies on agent self-reports; false successes go undetected. |

---

## 2. Experimental Procedure
1. Initialize the 250-scenario benchmark suite with fixed seed `42`.
2. Execute the full IntentGuard protocol as the control benchmark.
3. Iteratively execute Ablations 1 through 6 against the exact same scenario list.
4. Record metrics (Safety Violations, Duplicate Rate, False Block Rate, Task Completion) across all configurations.
5. Export comparative matrices to `experiments/results/ablation_summary.json` and generate bar charts for publication.
