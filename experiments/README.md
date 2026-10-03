# Empirical Benchmark and Ablation Framework

This directory houses the reproducible empirical evaluation suite for **IntentGuard: Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes**.

## Directory Layout
- `scenarios/`: 250 synthetic scenarios across 12 failure categories generated with deterministic random seeds.
- `runners/`: Benchmark execution harnesses, latency profilers, and multi-seed sweep orchestrators.
- `baselines/`: 4 comparative baseline implementations (Direct Agent, Fixed Validation, Idempotency Alone, LLM Reviewer).
- `results/`: Raw JSON and CSV exports of benchmark and ablation evaluations.

## Running the Evaluation Suite
```powershell
python scripts/run_experiments.py --seed 42 --scenarios 250
```
