# Paper outline

Working title: *IntentGuard: Intent-Consistent Transaction Execution and Recovery for Financial AI
Agents Under Uncertain Outcomes*. Draft: [manuscript.md](manuscript.md).

Every number in the paper must come from `experiments/results/latest/summary.md` or
`summary.json`. A section whose numbers cannot be traced there is marked **TODO** below.

| § | Section | Content | Evidence | Status |
|---|---|---|---|---|
| — | Abstract | Problem, protocol, headline results | Table 1, ablation table | Numbers checked |
| 1 | Introduction | Four failure modes: proposal drift, uncertain outcomes, changed retries, unverified recovery | — | Drafted |
| 2 | Identity model | Intent / proposal / attempt / effect; state derived from the ledger | `backend/intentguard/domain.py` | Drafted |
| 3 | Related work and contribution | Idempotency keys, sagas, LLM tool-safety review. Claimed contribution: the combination for non-deterministic agent callers | [../references.md](../references.md) | **TODO**: cite verified sources; several entries in references.md are unverified |
| 4 | Protocol | decide → reserve → execute → verify → absorb → drive; checks; states; reconciliation; recovery policy; durability | [../../architecture/](../../architecture/) | Drafted |
| 5 | Experimental method | Simulator, 30 categories in 6 families, agent error model and runtime, arms A–E, ablations, oracle, statistics | [../methodology.md](../methodology.md) | Drafted |
| 6 | Results | Table 1 (baselines vs. E), Table 2 (selected categories), findings 1–6 | `summary.md`; `summary.json` (`categories`, `latency_p95_ms`, `recovered_effects`) | Numbers checked |
| 7 | Ablations | Table 3; overlapping vs. non-overlapping safeguards | `summary.md` ablation table; `backend/tests/test_ablations.py` | Numbers checked |
| 8 | Verification beyond the benchmark | The 42 tests, including property-based safety | [../../testing/test-plan.md](../../testing/test-plan.md) | Drafted |
| 9 | Limitations and threats to validity | Simulator, scripted errors, optimistic D, absence window, SQLite only, latency, provenance | [../limitations.md](../limitations.md) | Drafted |
| 10 | Conclusion | | | Drafted |

## Open items before submission

1. **Real-LLM experiment** — **TODO.** Run `python -m bench run --llm-reviewer` (baseline D with a
   real model) and measure real agent error rates on generated tickets. No such run exists in
   `experiments/results/`, so the paper must not claim anything about real LLM behaviour yet.
2. **Clean provenance metadata.** Outcomes are already reproduced from committed code (see
   [../results.md](../results.md)). Optionally replace `latest/` with a run from a committed tree
   so the metadata records the exact commit; latency values would change.
3. **Related work** — **TODO.** Verify every citation in [../references.md](../references.md)
   against the primary source before it appears in the paper.
4. **PostgreSQL** — exercise it in CI, or keep the limitation.
5. **Venue formatting** — not started.
