> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../../README.md) for the current documentation.

# 08 — Research Paper Outline

## Title
IntentGuard: Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes

## Abstract
Briefly state:
- problem
- proposed protocol
- experimental setting
- major measured outcomes
- limitations

## 1. Introduction
Explain why financial AI agents require stronger execution guarantees than ordinary API automation.

## 2. Problem Definition
Define:
- authorization
- proposal
- attempt
- external effect
- uncertain outcome
- duplicate effect

## 3. Related Work
Discuss:
- transaction processing
- distributed systems
- API idempotency
- agent reliability
- compensation/recovery
- tool-use safety
- financial transaction controls

Clearly distinguish existing concepts from the proposed combination and evaluation.

## 4. System Design
Present:
- architecture
- authorization model
- state machine
- effects ledger
- reconciliation algorithm
- recovery policies

## 5. Experimental Method
Describe:
- synthetic data
- scenario generator
- fault injection
- baselines
- metrics
- fixed seeds
- repetitions

## 6. Results
Report:
- safety
- duplicate prevention
- legitimate completion
- recovery
- monetary discrepancy
- latency

## 7. Ablation
Show which components contribute to measured outcomes.

## 8. Failure Analysis
Discuss cases that were:
- prevented
- recovered
- unresolved

## 9. Limitations
Examples:
- simulated payment provider
- synthetic customers
- limited transaction types
- dependency on provider observability
- no claim of production financial compliance

## 10. Conclusion
Summarize measured evidence without overstating novelty or production readiness.
