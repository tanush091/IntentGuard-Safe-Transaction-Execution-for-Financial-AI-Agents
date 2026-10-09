# Open tasks

Real open items only. Completed work, and the earlier prototype's task list, are in git history.

## Research

- [ ] **Real-LLM evaluation.** Run `python -m bench run --llm-reviewer` (baseline D with a real
      model) and run the agent endpoint with 2–3 models on generated tickets; measure their error
      rates and whether IntentGuard's guarantees still hold. No such run exists yet.
- [ ] **Provenance metadata for the cited run.** `experiments/results/latest/` records commit
      `283c6bb`, which predates the benchmark code. A rerun from committed code reproduced every
      outcome exactly (2026-10-09). Decide whether to replace `latest/` with a run from a committed
      tree so the metadata is clean (latency values would change), then update the docs.
- [ ] **Paper finalization.** Verify every entry in `docs/research/references.md` against its
      primary source, finish related work, format for a venue
      (`docs/research/paper/outline.md`).
- [ ] Research extensions (no code yet): approvals expressed as ranges or multiple lines; learning
      the absence window per provider; multi-step operations with compensation; reducing human
      reviews without losing detection.

## Engineering

- [ ] **Exercise PostgreSQL in CI**: run the test suite against a PostgreSQL service container
      (row locks, the PL/pgSQL audit trigger, the partial unique index).
- [ ] **Read LLM and provider settings from `.env`.** `LLM_*`, `OPENAI_*`, `GEMINI_API_KEY`,
      `OLLAMA_BASE_URL` and `PAYSIM_*` are read with `os.getenv`, so values in `.env` are ignored;
      only the gateway's own settings load `.env`.
- [ ] **Missing tests**: the gateway's `BALANCE_EXCEEDED` check, `revoke`, and the
      `CONFIRMED_COMPLETED`, `CONFIRMED_NO_EFFECT` and `CLOSED_UNFULFILLED` review resolutions.
- [ ] **Two gateways, one database**: a concurrency test with two gateway processes.
- [ ] **Idempotency-key expiry**: scenarios where a retry happens after the provider forgets the key (simulator TTL 24 h).
- [ ] **Authentication and roles**: operators approve, reviewers resolve, agents only propose. The APIs currently have no authentication.
- [ ] **Re-render `docs/diagrams/intentguard_architecture.png`**: the `.mmd` and `.html` sources were updated to the new paths, but the PNG still shows the old ones.
- [ ] **Real provider sandbox adapter** (e.g. Stripe or Razorpay test mode) in `backend/intentguard/providers/`.
- [ ] Dashboard UI tests (CI only checks that the frontend builds).
- [ ] Monitoring: metrics and alerts for unknown outcomes, review backlog and open discrepancy amounts.
