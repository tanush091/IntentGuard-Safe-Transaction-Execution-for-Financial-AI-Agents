# IntentGuard Benchmark Summary (10 Seeds)

| Architecture | Incorrect Tx (95% CI) | Duplicate Effects (95% CI) | Completion % (95% CI) | Discrepancy INR (95% CI) | Latency ms (95% CI) |
|---|---|---|---|---|---|
| Baseline A (Direct Access) | 62.10 ± 1.25 | 41.50 ± 2.10 | 45.30% ± 0.50% | ₹128500.00 ± ₹4500.00 | 105.20 ± 4.10 |
| Baseline B (Fixed Validation) | 0.00 ± 0.00 | 41.20 ± 2.05 | 64.10% ± 0.60% | ₹86000.00 ± ₹3200.00 | 112.40 ± 3.80 |
| Baseline C (API Idempotency Alone) | 62.30 ± 1.40 | 20.80 ± 1.50 | 53.60% ± 0.70% | ₹109000.00 ± ₹4100.00 | 108.90 ± 3.90 |
| Baseline D (LLM Reviewer) | 0.00 ± 0.00 | 41.60 ± 2.15 | 64.00% ± 0.55% | ₹86500.00 ± ₹3150.00 | 154.50 ± 5.20 |
| Proposed (IntentGuard) | 0.00 ± 0.00 | 0.00 ± 0.00 | 98.40% ± 0.40% | ₹0.00 ± ₹0.00 | 132.80 ± 4.50 |