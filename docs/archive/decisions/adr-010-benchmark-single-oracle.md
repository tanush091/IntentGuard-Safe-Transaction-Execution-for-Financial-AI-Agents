> **Archived.** Merged into the single register [docs/DECISIONS.md](../../DECISIONS.md) on 2026-10-10; see the [old → new number map](../../decisions/README.md). Kept unchanged for history; names in this file are the prototype's.

# ADR-010: One oracle on the provider's ledger, identical agent behaviour for every arm

**Status:** Accepted

## Context
Comparisons between architectures are misleading if each arm grades itself, if arms see different
agent behaviour, or if the seed changes only identifiers. The earlier prototype's published
numbers were written by a script, not measured.

## Decision
- The seed controls the scenario *mix* (30 categories, 6 families), not just IDs.
- One scripted agent runtime and error model, identical for every arm.
- One oracle (`experiments/bench/scoring.py`) reads the provider's ground-truth ledger after a 900 s horizon; an arm's own bookkeeping is used only to detect misreports and flags.
- Results are written by `python -m bench run` with run metadata; documentation cites only `experiments/results/latest/summary.md` and `summary.json`.

## Consequences
- Reproducible, comparable numbers with bootstrap CIs over seeds.
- Aggregate numbers depend on the chosen category weights; per-category tables are reported too.
