# Open tasks

Real open items only. Completed work, and the earlier prototype's task list, are in git history.
Feature status is tracked in [FEATURES.md](FEATURES.md); this list is what to do next.

## Research

- [ ] **Real-LLM evaluation.** Run `python -m bench run --llm-reviewer` (baseline D with a real
      model) and run the agent endpoint with 2–3 models on generated tickets; measure their error
      rates and whether IntentGuard's guarantees still hold. No such run exists yet.
- [ ] **Investigator evaluation.** Labelled exception cases. Measure classification accuracy, the
      share resolved without a human, cost and latency per resolved exception (token counts are
      already stored per investigation), and the false "permitted" rate, which must be 0
      (TEST_PLAN.md §8).
- [ ] **Provenance metadata for the cited run.** `experiments/results/latest/` records commit
      `283c6bb`, which predates the benchmark code. A rerun from committed code reproduced every
      outcome exactly (2026-10-09), and quick runs stayed identical through the rebuild. Decide
      whether to replace `latest/` with a run from a committed tree so the metadata is clean
      (latency values would change), then update the docs.
- [ ] **Paper finalization.** Verify every entry in `docs/research/references.md` against its
      primary source, finish related work, format for a venue
      (`docs/research/paper/outline.md`).
- [ ] Research extensions (no code yet):
  - approvals expressed as ranges or multiple lines (ADR-031);
  - learning the absence window per provider;
  - multi-step operations with compensation;
  - reducing human reviews without losing detection.

## Engineering

- [ ] **First CI run.** Push `feat/recovery-rebuild` and check that all seven jobs in
      `.github/workflows/ci.yml` pass on GitHub. They were run locally except `docker compose build`,
      because Docker was not running on the development machine.
- [ ] **Real provider sandbox adapter** (Stripe or Razorpay test mode) in
      `backend/intentguard/providers/`, with webhook signature schemes per provider (ADR-012).
- [ ] **Prompt-injection evaluation set**, including injection inside provider responses and
      webhook payloads (SECURITY.md §8 item 5).
- [ ] **Two gateways, one database**: a concurrency test with two gateway processes on PostgreSQL. The
      rate limiter is per process and would need a shared store.
- [ ] **Idempotency-key expiry**: scenarios where a retry happens after the provider forgets the key
      (simulator TTL 24 h).
- [ ] **Dashboard end-to-end tests**: Playwright for the four demo scenarios and the review flow, plus
      axe accessibility checks (the flows were run in headless Chrome by hand; Vitest covers logic only).
- [ ] **Security before any pilot**: MFA for reviewer/admin, a breach-list password check, a gateway
      request size limit, scheduled audit-chain verification with alerting, TLS at the edge
      (SECURITY.md §14).
- [ ] **Monitoring**: alerts for unknown-outcome backlog, review backlog, open discrepancy amounts and
      webhook signature failures (the metrics summary already exposes the numbers).
- [ ] **Multi-tenancy** with `tenant_id` and PostgreSQL RLS (ADR-020), only when a second tenant exists.
- [ ] Nightly CI: extended property tests, 32-agent concurrency, the full benchmark, and a
      reproducibility check (two runs, identical `scenarios.csv`).
