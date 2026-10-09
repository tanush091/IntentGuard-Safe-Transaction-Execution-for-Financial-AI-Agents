> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

# 06 — Research Methodology

## Research Question
Can an intent-consistent transaction protocol reduce incorrect and duplicate final financial outcomes under uncertain outcomes while preserving legitimate-task completion?

## Hypotheses

### H1
Intent binding and deterministic validation reduce unauthorized transaction effects.

### H2
Provider-side reconciliation reduces duplicate effects caused by lost responses and changed retries.

### H3
State-aware recovery reduces incorrect cancellation and retry decisions.

### H4
The complete protocol maintains acceptable legitimate-task completion while improving safety.

## Benchmark
Use approximately 200–300 synthetic scenarios.

Include:
- normal valid refunds
- wrong amounts
- wrong orders
- similar order IDs
- partial refunds
- timeout before execution
- timeout after execution
- service outages
- delayed provider state
- agent crashes
- gateway restarts
- changed retries
- concurrent agents
- failed cancellations

Use fixed seeds for reproducibility.

## Baselines

### Baseline A
Agent → Payment Service

### Baseline B
Agent → Fixed Validation → Payment Service

### Baseline C
Agent → Idempotency → Payment Service

### Baseline D
Agent → LLM Reviewer → Payment Service

### Proposed
Agent → Intent Gateway → Payment Service → Reconciliation

## Metrics
- incorrect completed transactions
- duplicate financial effects
- legitimate-task completion rate
- false-block rate
- unresolved monetary discrepancy
- recovery success rate
- transaction latency

## Safety Properties
1. A refund cannot exceed its authorization.
2. A refund cannot target an unauthorized order.
3. One intent produces at most one permitted completed financial effect.
4. UNKNOWN never causes an uncontrolled immediate retry.
5. Provider state determines the final external-effect assessment.
6. Transaction history remains auditable.

## Ablation Studies
Remove one major component at a time:
- intent binding
- state machine
- reconciliation
- effects ledger
- duplicate protection
- recovery policy

Compare the resulting safety and completion metrics.
