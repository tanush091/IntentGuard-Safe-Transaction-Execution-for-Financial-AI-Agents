# Limitations

These four limitations are stated in the project README and apply to every result in
[results.md](results.md):

- The provider is a simulator modelled on documented provider behaviour; it is not a real provider sandbox.
- The baseline agent's errors come from an explicit error model. Baseline D's offline reviewer reuses the deterministic ticket extractor, which is an optimistic stand-in for an LLM reviewer; run with `--llm-reviewer` for a real one.
- Experiments use SQLite (shared-cache in-memory). PostgreSQL is supported by the code and Docker setup but was not exercised by the automated tests.
- Latency figures are in-process wall-clock times and say nothing about production performance.

## Further threats to validity

From the manuscript ([paper/manuscript.md](paper/manuscript.md), section 9) and the code:

- **The absence window is a parameter, not a measurement.** It is 30 s. If a provider's
  visibility lag exceeds it *and* the stable idempotency key is unavailable, duplicates can occur;
  the ablations measure this. Benchmark lags of 45 s and 90 s are included.
- **Synthetic data only.** Tickets, orders and error rates are generated. Real tickets and order
  histories may contain situations the generator does not.
- **Error rates are chosen, not observed.** Category weights and the 40% persistent-error rate are
  design choices, so the aggregate numbers depend on them. Per-category results are more
  informative than the overall averages.
- **No real LLM run.** No benchmark run with a real LLM agent or reviewer is recorded in
  `experiments/results/`.
- **Provenance of the recorded run.** It was made from a working tree before the code was
  committed (metadata commit `283c6bb`, code committed as `2bbb6a9`). A rerun from committed code
  reproduced all outcomes exactly (see [results.md](results.md)), so this is a metadata gap, not a
  results gap.
- **Latency is not reproducible.** It depends on the machine and its load; the rerun's latency
  differed from the recorded run while every other metric matched.
- **Single-gateway setup.** Multiple gateway processes against one database are designed for
  (leases, row locks) but not tested.
