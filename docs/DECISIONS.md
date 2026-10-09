# Architecture Decision Records (DECISIONS.md) — IntentGuard Recovery

Format: **Status · Context · Decision · Consequences.** Status values: `Accepted`, `Proposed` (needs confirmation), `Open` (undecided), `Superseded`.
ADR-001 to ADR-010 carry forward decisions from the existing prototype; ADR-011 onward cover the product direction.

---

## ADR-001: Intent-anchored idempotency
**Status:** Accepted
**Context:** After an agent crash or restart, a fresh `request_id` is generated for the same business request. Client-level idempotency treats it as new and can double-refund.
**Decision:** Derive the provider idempotency key from the intent: `ig-<intent_id>-g<generation>`. Generation increments only after a *verified* reversal.
**Consequences:** Restarts and concurrent agents cannot create a second effect. Agents cannot choose or see the key.

## ADR-002: Four separate identities (intent, proposal, attempt, effect)
**Status:** Accepted
**Context:** Conflating the operator's authorization, the agent's request, a single API call and the observed result hides duplicates and makes recovery ambiguous.
**Decision:** Model them as separate tables. Intent state is **derived** from attempts and effects, never asserted.
**Consequences:** Clear audit story; more joins; requires a derivation function with tests.

## ADR-003: Treat timeouts as UNKNOWN and reconcile before retry
**Status:** Accepted
**Context:** A timeout is not proof of failure; the provider may have executed.
**Decision:** Timeout → attempt `UNKNOWN` → reconcile (provider txn ID, then order reference) → complete, controlled retry, or escalate.
**Consequences:** Removes the lost-response duplicate. Adds latency and requires provider query capability.

## ADR-004: Absence window for "not found"
**Status:** Accepted
**Context:** Provider search is eventually consistent; an immediate "not found" can be wrong.
**Decision:** "Not found" counts as evidence of no effect only after `absence_window_s`. If the provider cannot be queried at all, hold for review instead of retrying.
**Consequences:** Safer but slower recovery for genuinely failed requests; window must be tuned per provider.

## ADR-005: Provider state is the source of truth
**Status:** Accepted
**Context:** API responses and internal memory can be wrong or stale.
**Decision:** Final outcome is whatever verified provider state shows. Internal recovery (agent memory reset, restart) is never evidence of reversal.
**Consequences:** Every completion requires a read-back; dashboards must show "being verified" states.

## ADR-006: Agent is untrusted and isolated
**Status:** Accepted
**Context:** Agents hallucinate and can be prompt-injected.
**Decision:** The agent gets no provider credentials or network route. It can only call the proposal endpoint with a scoped token.
**Consequences:** Safe by construction; integration needs a gateway round trip.

## ADR-007: Persist before external call
**Status:** Accepted
**Context:** A crash between call and record loses track of an in-flight attempt.
**Decision:** Commit the decision and attempt (`SUBMITTING`) before calling the provider. On startup, attempts left `SUBMITTING` become `UNKNOWN` and are reconciled.
**Consequences:** Crash-safe; requires a startup recovery routine.

## ADR-008: Append-only hash-chained audit log
**Status:** Accepted
**Context:** Auditors need history that cannot be quietly edited.
**Decision:** Hash-chain audit entries and block UPDATE/DELETE with DB triggers; expose a verify endpoint.
**Consequences:** Tamper-evident, not tamper-proof; consider external anchoring of the head hash.

## ADR-009: Decoupled provider simulator
**Status:** Accepted
**Context:** Realistic failure testing needs real network boundaries and controllable faults.
**Decision:** Keep the simulator (`paysim`) as a separate HTTP service (with in-process mode for fast tests) and put all providers behind a provider port.
**Consequences:** Faithful fault injection; real adapters plug into the same port. Simulator behavior is modelled, not a real sandbox.

## ADR-010: Seeded benchmark with a single oracle
**Status:** Accepted
**Context:** Self-reported bookkeeping makes baselines look better or worse arbitrarily.
**Decision:** Every architecture arm is scored by one ground-truth oracle reading the provider ledger after a settlement horizon; arm bookkeeping only detects misreports. Seeds control the scenario mix.
**Consequences:** Fair comparison; results are reproducible and must be cited only from measured runs.

---

## ADR-011: Position as "execution assurance", not a refund chatbot
**Status:** Accepted
**Context:** AI refund tools, reconciliation platforms and gateway-native retries already exist (competitor claims unverified).
**Decision:** Product focus is the gap between *requesting* a transaction and *proving its final outcome*: authorization + durable state + provider verification + evidence-backed recovery.
**Consequences:** Narrower pitch; must demonstrate measurable reliability rather than feature breadth.

## ADR-012: Initial target market and first provider
**Status:** Open
**Context:** Options are Indian merchants (Razorpay test integration, if available) or global SaaS/e-commerce (Stripe test mode, mature docs on idempotency and events).
**Decision:** *Pending.* Default recommendation: build the first real adapter against whichever sandbox is accessible today, behind the provider port, and choose the market after design-partner conversations.
**Consequences:** Provider port keeps the choice reversible.

## ADR-013: LLM interprets exceptions; code decides execution
**Status:** Accepted
**Context:** LLM confidence is poorly calibrated; free-form tool choice by an LLM risks unauthorized money movement.
**Decision:** The LLM (a) classifies and summarizes ambiguous cases, (b) proposes one action from a fixed enum. A deterministic policy gate decides whether that action is permitted in the current state. No confidence threshold is used as a safety control.
**Consequences:** Bounded blast radius; investigator value is measured (accuracy, cost, human-time saved) rather than assumed.

## ADR-014: Exception-only LLM use
**Status:** Accepted
**Context:** Most cases are resolved by deterministic reconciliation; LLM calls add cost and latency.
**Decision:** Invoke the investigator only after deterministic recovery returns `ESCALATE`/`UNKNOWN` beyond the retry budget, or when evidence is inconsistent. Offline rule extractor remains the default fallback for agent extraction.
**Consequences:** Lower cost; benchmark must report cost per resolved exception.

## ADR-015: No orchestration framework in v1
**Status:** Accepted
**Context:** LangChain/CrewAI/AutoGen add abstraction without solving the core problem.
**Decision:** Plain Python service + explicit state machine + one constrained LLM call.
**Consequences:** Fewer dependencies and clearer failure modes; revisit if workflows become genuinely multi-step.

## ADR-016: PostgreSQL as durable source of truth; Redis optional
**Status:** Accepted
**Context:** Need transactional guarantees, partial unique indexes, RLS and triggers; need short-lived coordination for jobs.
**Decision:** PostgreSQL (e.g. Supabase) is authoritative in production; SQLite for local dev/benchmarks. Redis/Celery only when background throughput requires it and never as the system of record.
**Consequences:** Must exercise PostgreSQL in CI (currently not covered by automated tests per the repo README).

## ADR-017: Effectively-once, not exactly-once
**Status:** Accepted
**Context:** A local database cannot guarantee exactly-once effects across distributed systems.
**Decision:** Claim and document "effectively-once where provider guarantees support it", combined with durable state, verification and controlled recovery. Do not market universal exactly-once.
**Consequences:** More defensible with technical reviewers and investors.

## ADR-018: JWT access tokens + rotating refresh tokens; agent tokens scoped
**Status:** Accepted
**Context:** Humans and agents need different privileges and lifetimes.
**Decision:** 15-minute access JWT (agents ≤ 5 minutes, intent-scoped), opaque rotating refresh tokens stored hashed, access token in memory on the client.
**Consequences:** Short blast radius on theft; requires refresh logic in the frontend. Details in SECURITY.md.

## ADR-019: API contract as the repo boundary
**Status:** Accepted
**Context:** Backend and frontend may live in separate repos.
**Decision:** `API.md` plus generated OpenAPI is the single contract; backend publishes it, frontend generates a typed client from it. Decisions (`REJECT`, `DUPLICATE`) are HTTP 200 payloads, not HTTP errors.
**Consequences:** Contract changes need coordinated PRs; additive-only changes are non-breaking.

## ADR-020: Multi-tenancy via `tenant_id` and PostgreSQL RLS
**Status:** Proposed
**Context:** SaaS direction needs isolation between customers.
**Decision:** Add `tenant_id` to all tables, filter at the repository layer, enforce with RLS as defense in depth.
**Consequences:** Migration effort and test matrix for cross-tenant access; defer until a second tenant exists, but design schema now.

## ADR-021: Provider webhooks are hints, state is re-fetched
**Status:** Proposed
**Context:** Webhooks can be forged, repeated, delayed or out of order.
**Decision:** Verify signature, dedupe by event ID, then re-fetch the provider object before changing state where the provider allows.
**Consequences:** Extra API calls; stronger correctness.

## ADR-022: Frontend stack is React + Vite with a token-driven design system
**Status:** Accepted
**Context:** The repo's current dashboard is React; earlier docs described vanilla JS.
**Decision:** React + Vite, tokens in CSS variables (see DESIGN.md).
**Consequences:** Legacy vanilla-JS docs are superseded.

## ADR-023: Do not cite legacy benchmark numbers
**Status:** Accepted
**Context:** The repository README states legacy benchmark numbers were fixed values, not measured.
**Decision:** Only measured outputs under `experiments/results/` may appear in docs, papers or pitches.
**Consequences:** Pitch material must be regenerated from real runs.
