# Architecture Decision Records (DECISIONS.md) — IntentGuard Recovery

This is the single decision register: one numbering for every decision. It has three parts:
- **ADR-001 to ADR-010** carry forward the prototype's decisions. The prototype's own files (formerly `docs/decisions/adr-001` to `adr-012`, now in `docs/archive/decisions/`) are merged in here; the [old → new number map](decisions/README.md) keeps old references meaningful.
- **ADR-011 to ADR-023** cover the product direction.
- **ADR-024 onward** are the remaining prototype decisions and the decisions taken while rebuilding the code to this target.

Format: **Status · Context · Decision · Consequences**, plus **Implementation** where it says what the code does.

Status values:
- `Accepted`: decided.
- `Proposed`: needs confirmation.
- `Open`: undecided.
- `Superseded`: replaced by a later decision.

Implementation values: `implemented`, `partial` or `planned`.

---

## ADR-001: Intent-anchored idempotency
**Status:** Accepted · **Implementation:** implemented (`engine._reserve`)
**Context:** After an agent crash or restart, a fresh `request_id` is generated for the same business request. Client-level idempotency treats it as new and can double-refund. A fixed key per intent would make a legitimate retry after a verified reversal replay the reversed transaction.
**Decision:**
- Derive the provider idempotency key from the intent: `ig-<intent_id>-g<generation>`.
- The generation starts at 0 and increments only after a *verified* reversal: a wrong effect verified `CANCELLED` at the provider, or a reviewer's `REFUND_RECOVERED_OUT_OF_BAND`.
- Timeouts and confirmed absences do not change it.

**Consequences:**
- Restarts, concurrent agents and the gateway's own retries all replay the same provider transaction. Agents cannot choose or see the key.
- Correctness depends on the provider honouring idempotency keys with parameter fingerprints, as `paysim` does.
- Removing the key together with dedup, the absence window or reconciliation brings duplicates back ([research/results.md](research/results.md)).

## ADR-002: Four separate identities (intent, proposal, attempt, effect)
**Status:** Accepted · **Implementation:** implemented (`intents`, `agent_proposals` + `gateway_decisions`, `transaction_attempts`, `effects`)
**Context:** Conflating the operator's authorization, the agent's request, a single API call and the observed result hides duplicates and makes recovery ambiguous.
**Decision:** Model them as separate tables, and record every proposal with its decision. Intent state is **derived** from attempts, effects and open review cases (`engine._derive`), never asserted, and is checked against `TRANSITIONS` (`domain.py`).
**Consequences:**
- A proposal can be rejected before any money moves, and a new agent request can never create a new authorization.
- `COMPLETED` means an effect matching the intent was observed, not that an API call returned 200.
- More joins. The explicit transition table and the Hypothesis property test keep the derivation honest.

## ADR-003: Treat timeouts as UNKNOWN and reconcile before retry
**Status:** Accepted · **Implementation:** implemented (`engine._reconcile`)
**Context:** A timeout is not proof of failure; the provider may have executed.
**Decision:**
- A timeout leaves the attempt `UNKNOWN` and the intent `UNKNOWN`.
- Reconciliation looks up known references by id and searches the order, attributing results by intent, attempt or idempotency key.
- The result is: complete, a controlled retry under the same key, or escalation.

**Consequences:** Removes the lost-response duplicate. Adds latency and requires provider query capability.

## ADR-004: Absence window for "not found"
**Status:** Accepted · **Implementation:** implemented (`absence_window_s` 30 s, `unknown_review_after_s` 300 s; both admin policies)
**Context:** Provider search is eventually consistent; an immediate "not found" can be wrong.
**Decision:**
- "Not found" counts as evidence of no effect only from a successful search at least `absence_window_s` after the attempt. Only then does the attempt become `RECONCILED` and the gateway retry, under the same key.
- If the provider cannot be queried at all, the intent goes to review after `unknown_review_after_s` instead of retrying.

**Consequences:** Safer but slower recovery for genuinely failed requests. The window is an assumption about the provider; the ablations measure what happens when it is wrong.

## ADR-005: Provider state is the source of truth
**Status:** Accepted · **Implementation:** implemented (read-back verification; webhooks re-fetch, ADR-021)
**Context:** API responses and internal memory can be wrong or stale.
**Decision:** Final outcome is whatever verified provider state shows. Internal recovery (agent memory reset, restart) is never evidence of reversal.
**Consequences:** Every completion requires a read-back. Dashboards show uncertain states as "Verifying", never as failed.

## ADR-006: Agent is untrusted and isolated
**Status:** Accepted · **Implementation:** implemented (service tokens, `POST /intents/{id}/agent`)
**Context:** Agents hallucinate and can be prompt-injected (for example through ticket text).
**Decision:**
- The agent gets no provider credentials or network route. It can only call the proposal endpoint with a scoped, short-lived token.
- The LLM is an extractor without tools. Ticket text is turned into fields by a deterministic rule extractor (default), or by an LLM when `LLM_PROVIDER` is set.
- Every proposal goes through the same checks.

**Consequences:**
- Safe by construction; integration needs a gateway round trip.
- Demos, tests and the benchmark run offline. The LLM path is covered by output-validation tests, but no recorded benchmark run uses a real model yet.

## ADR-007: Persist before external call
**Status:** Accepted · **Implementation:** implemented
**Context:** A crash between call and record loses track of an in-flight attempt. Holding a database lock across a slow provider call would serialize everything behind the network.
**Decision:**
- Decide and reserve in one locked transaction that commits the attempt as `SUBMITTING`, with the key and a 15 s lease, before calling the provider.
- Provider calls run with no lock held; results are absorbed in a second locked transaction.
- On startup, `SUBMITTING` attempts from other process incarnations, or past their lease, become `UNKNOWN` and are reconciled.

**Consequences:** A crash at either injection point (`after_attempt_recorded`, `after_provider_response`) is recovered with exactly one effect (tested). There are two transactions per submission; the window between them is covered by the stable key and the state gate.

## ADR-008: Append-only hash-chained audit log
**Status:** Accepted · **Implementation:** implemented (`audit_logs`, `GET /audit/verify`)
**Context:** Auditors need history that cannot be quietly edited.
**Decision:**
- Hash-chain audit entries per intent, plus a system chain, with `UNIQUE(chain_id, prev_hash)` so a chain cannot fork.
- Block UPDATE/DELETE with database triggers on both SQLite and PostgreSQL.
- Expose a verify endpoint.

**Consequences:** Tamper-evident, not tamper-proof: a privileged attacker who drops the trigger is caught by verification, not prevented. *Planned:* external anchoring of the head hash.

## ADR-009: Decoupled provider simulator
**Status:** Accepted · **Implementation:** implemented (`paysim`, `provider_api`, `PaymentProvider` port)
**Context:** Realistic failure testing needs real network boundaries and controllable faults, and the project must never touch real money.
**Decision:**
- Keep the simulator (`paysim`) as a separate HTTP service, with an in-process mode for the benchmark and fast tests.
- Put all providers behind the `PaymentProvider` port, with the adapters `HttpProvider` and `InProcessProvider`.
- The simulator supports pending settlement, state-dependent cancellation, idempotency with parameter checks, eventually consistent search, signed webhooks and injectable faults.

**Consequences:** Faithful fault injection; real adapters plug into the same port. The simulator's behaviour is modelled and has not been validated against a real sandbox.

## ADR-010: Seeded benchmark with a single oracle
**Status:** Accepted · **Implementation:** implemented (`experiments/bench`)
**Context:** Self-reported bookkeeping makes baselines look better or worse arbitrarily, and the earlier prototype's published numbers were written by a script, not measured.
**Decision:**
- Seeds control the scenario mix (30 categories in 6 families), not just identifiers.
- Every arm gets one scripted agent runtime and error model.
- One oracle (`experiments/bench/scoring.py`) reads the provider ledger after a 900 s horizon. An arm's own bookkeeping only detects misreports.

**Consequences:** Fair, reproducible comparison with bootstrap CIs over seeds. Results are cited only from measured runs (ADR-023). Aggregates depend on the category weights, so per-category tables are reported too.

---

## ADR-011: Position as "execution assurance", not a refund chatbot
**Status:** Accepted
**Context:** AI refund tools, reconciliation platforms and gateway-native retries already exist (competitor claims unverified).
**Decision:** Product focus is the gap between *requesting* a transaction and *proving its final outcome*: authorization + durable state + provider verification + evidence-backed recovery.
**Consequences:** Narrower pitch; must demonstrate measurable reliability rather than feature breadth.

## ADR-012: Initial target market and first provider
**Status:** Open · **Implementation:** planned
**Context:** Options are Indian merchants (Razorpay test integration, if available) or global SaaS/e-commerce (Stripe test mode, mature docs on idempotency and events).
**Decision:** *Pending.* Default recommendation: build the first real adapter against whichever sandbox is accessible today, behind the provider port, and choose the market after design-partner conversations.
**Consequences:** Provider port keeps the choice reversible.

## ADR-013: LLM interprets exceptions; code decides execution
**Status:** Accepted · **Implementation:** implemented (`backend/investigator/`)
**Context:** LLM confidence is poorly calibrated; free-form tool choice by an LLM risks unauthorized money movement.
**Decision:**
- The LLM (a) classifies and summarizes ambiguous cases, and (b) proposes one action from a fixed enum.
- A deterministic policy gate decides whether that action is permitted in the current state.
- No confidence threshold is used as a safety control. Output that fails the strict schema is rejected, not repaired.

**Consequences:** Bounded blast radius; investigator value must be measured (accuracy, cost, human time saved) rather than assumed. See ADR-033 for how a recommendation is applied.

## ADR-014: Exception-only LLM use
**Status:** Accepted · **Implementation:** partial
**Context:** Most cases are resolved by deterministic reconciliation; LLM calls add cost and latency.
**Decision:** Invoke the investigator only after deterministic recovery returns `ESCALATE`/`UNKNOWN` beyond the retry budget, or when evidence is inconsistent. Offline rule extractor remains the default fallback for agent extraction.
**Consequences:** Lower cost; benchmark must report cost per resolved exception.
**Implementation note:** investigations run on demand, and only for intents in an exception state (`409 NOT_AN_EXCEPTION` otherwise). An offline rule classifier is the default. Automatic invocation, and reporting cost per resolved exception, are planned.

## ADR-015: No orchestration framework in v1
**Status:** Accepted · **Implementation:** implemented
**Context:** LangChain/CrewAI/AutoGen add abstraction without solving the core problem.
**Decision:** Plain Python service + explicit state machine + one constrained LLM call.
**Consequences:** Fewer dependencies and clearer failure modes; revisit if workflows become genuinely multi-step.

## ADR-016: PostgreSQL as durable source of truth; Redis optional
**Status:** Accepted · **Implementation:** implemented (no Redis)
**Context:** Need transactional guarantees, partial unique indexes, RLS and triggers; need short-lived coordination for jobs.
**Decision:**
- PostgreSQL is authoritative in deployment (`docker-compose.yml` runs PostgreSQL 16). There the engine locks the intent row with `SELECT ... FOR UPDATE`.
- SQLite (every transaction `BEGIN IMMEDIATE`) is the zero-setup default for local runs, tests and the benchmark.
- Redis/Celery only when background throughput requires it, and never as the system of record.

**Consequences:** The full test suite runs against PostgreSQL in CI (`backend-postgres` job). All 127 tests pass on PostgreSQL 16; the race ablation's outcome differs by database (ADR-025). Benchmark results are measured on SQLite.

## ADR-017: Effectively-once, not exactly-once
**Status:** Accepted
**Context:** A local database cannot guarantee exactly-once effects across distributed systems.
**Decision:** Claim and document "effectively-once where provider guarantees support it", combined with durable state, verification and controlled recovery. Do not market universal exactly-once.
**Consequences:** More defensible with technical reviewers and investors.

## ADR-018: JWT access tokens + rotating refresh tokens; agent tokens scoped
**Status:** Accepted · **Implementation:** implemented (details in ADR-032)
**Context:** Humans and agents need different privileges and lifetimes.
**Decision:** 15-minute access JWT (agents ≤ 5 minutes, intent-scoped), opaque rotating refresh tokens stored hashed, access token in memory on the client.
**Consequences:** Short blast radius on theft; requires refresh logic in the frontend. Details in SECURITY.md.

## ADR-019: API contract as the repo boundary
**Status:** Accepted · **Implementation:** implemented, with a route-table check instead of a generated client
**Context:** Backend and frontend may live in separate repos.
**Decision:** `API.md` plus generated OpenAPI is the single contract; backend publishes it, frontend generates a typed client from it. Decisions (`REJECT`, `DUPLICATE`) are HTTP 200 payloads, not HTTP errors.
**Consequences:** Contract changes need coordinated PRs; additive-only changes are non-breaking.
**Implementation note:** the schema is exported to `docs/api/openapi.json`. CI fails when it drifts from the code (`scripts/export_openapi.py --check`) and when a route in the dashboard's single route table (`frontend/src/api/endpoints.js`) is missing from it (`npm run check:contract`). A generated typed client is not used: the dashboard is plain JavaScript.

## ADR-020: Multi-tenancy via `tenant_id` and PostgreSQL RLS
**Status:** Proposed · **Implementation:** planned
**Context:** SaaS direction needs isolation between customers.
**Decision:** Add `tenant_id` to all tables, filter at the repository layer, enforce with RLS as defense in depth.
**Consequences:** Migration effort and test matrix for cross-tenant access; defer until a second tenant exists, but design schema now.

## ADR-021: Provider webhooks are hints, state is re-fetched
**Status:** Accepted · **Implementation:** implemented (`POST /webhooks/paysim`)
**Context:** Webhooks can be forged, repeated, delayed or out of order.
**Decision:**
1. Verify the signature (`Paysim-Signature: t=…,v1=<HMAC-SHA256>`, with timestamp tolerance).
2. Dedupe by event ID.
3. Store the event.
4. Re-fetch the provider object before changing state.

**Consequences:** Extra API calls; stronger correctness. A transaction no intent accounts for is flagged as a `MISSING` mismatch, never adopted.

## ADR-022: Frontend stack is React + Vite with a token-driven design system
**Status:** Accepted · **Implementation:** implemented (React 18, Vite 7, tokens in `frontend/src/styles/tokens.css`)
**Context:** The repo's current dashboard is React; earlier docs described vanilla JS.
**Decision:** React + Vite, tokens in CSS variables (see DESIGN.md).
**Consequences:** Legacy vanilla-JS docs are superseded.

## ADR-023: Do not cite legacy benchmark numbers
**Status:** Accepted
**Context:** The legacy prototype's benchmark numbers were fixed values written by a script, not measured.
**Decision:** Only measured outputs under `experiments/results/` may appear in docs, papers or pitches.
**Consequences:** Pitch material must be regenerated from real runs.

---

## ADR-024: Recovery is state-aware and verified; otherwise escalate
**Status:** Accepted · **Implementation:** implemented (`engine.recover`, `domain.cancellation_policy`) · *from prototype ADR-005*
**Context:** A provider can execute the wrong amount, or an agent mistake can slip through under an ablation. Some effects can be reversed (pending refunds, authorization holds) and some cannot (completed refunds). Reporting a reversal because a cancel call was issued is a false claim.
**Decision:**
- Cancel a pending refund or void a hold, then read the transaction back. Record a reversal only if it is `CANCELLED`.
- A completed refund, a rejected cancel, or a cancel that cannot be verified after 3 tries opens a review case with the amount at stake.
- The intent stays `DISCREPANCY` until nothing unintended is live.
- The operator cancel flow (`CANCEL_REQUESTED`, ADR-030) uses the same verified path.

**Consequences:** Wrong money that cannot be reversed is never hidden: undetected wrong money is ₹0 for the full protocol in the recorded run. Some cases need a human; that is the measured cost (human reviews per 300 scenarios).

## ADR-025: Enforce key invariants in the database
**Status:** Accepted · **Implementation:** implemented · *from prototype ADR-006*
**Context:** Application checks can have bugs and races. The properties that matter most should not depend on them alone: at most one counted effect per intent, and an unalterable history.
**Decision:**
- A partial unique index on `effects(intent_id)` where `counts_toward_intent`.
- `effects.provider_ref` is unique, and `(intent_id, attempt_no)` is unique.
- `audit_logs` is append-only through triggers (SQLite `audit_no_update`/`audit_no_delete`, PostgreSQL `audit_no_modify`) and hash-chained (ADR-008).
- A database created by an earlier schema version is refused at startup (`SchemaMismatch`). `scripts/check_db.py` moves such a local SQLite file aside as a backup instead of deleting it.

**Consequences:**
- A logic error that would create a second counted effect fails at commit instead of moving money silently.
- On PostgreSQL the attempt-number constraint also stops the race that the serialization ablation opens; on SQLite the database-wide write lock orders it instead (`test_ablations.py`).
- Tampering is detectable, not preventable by a privileged attacker.

## ADR-026: Ablations are configuration switches on the real engine
**Status:** Accepted · **Implementation:** implemented (`ProtocolConfig`) · *from prototype ADR-011*
**Context:** An ablation that re-implements the protocol without a component measures the re-implementation, not the component.
**Decision:** Each safeguard is a boolean or parameter in `ProtocolConfig`: `intent_binding`, `effect_dedup`, `reconciliation`, `absence_window_s`, `stable_idempotency_key`, `state_aware_recovery` and `serialize_intent`. `readback_verification` is also a switch but is not ablated. Ablation arms run the same engine with one switch, or two overlapping switches, turned off.
**Consequences:** Overlapping safeguards show up as "no change alone, regression together", reported as defence in depth. The engine carries ablation-only code paths (blind cancel, permissive transitions), marked as such in the code.

## ADR-027: Repository layout
**Status:** Accepted · **Implementation:** implemented (2026-10-09) · *from prototype ADR-012*
**Context:** The repository mixed the current build with an unused earlier prototype whose published numbers were not measured.
**Decision:**
- Delete the earlier prototype; history remains in git.
- `backend/` holds `intentguard/`, `gateway_api/`, `investigator/`, `provider_api/`, `paysim/` and `tests/`.
- `experiments/bench/` holds the benchmark and runs from `experiments/` with `python -m bench`.
- `frontend/` holds the dashboard, and `scripts/` the launchers and checks.
- `docs/` holds the target specs at its root and the as-built reference in subfolders; superseded documents go to `docs/archive/`.

**Consequences:** Tests and services run from `backend/` and the benchmark from `experiments/`. Quick benchmark runs never write to the cited `experiments/results/latest/`.

## ADR-028: Adopt the API.md vocabulary in the code
**Status:** Accepted · **Implementation:** implemented (commit 2432352)
**Context:** The prototype's names (`OUTCOME_UNKNOWN`, `NEEDS_REVIEW`, `APPROVED`, `REVOKED`, …) differed from the product docs. Two vocabularies invite mistakes at the API boundary.
**Decision:** Rename states, decisions, reason codes, attempt statuses, review resolutions and simulator fault kinds to the API.md names. The rename is bijective for every existing state. Benchmark category and arm names are not renamed.
**Consequences:** One vocabulary from database to dashboard. The rename is behaviour-preserving: a quick benchmark run (1,800 scenario rows) is identical cell for cell to the run before it, and again after every later rebuild stage. The research documents use the new names.

## ADR-029: Proposal status is per proposal; DISCREPANCY and CLOSED stay intent states
**Status:** Accepted · **Implementation:** implemented
**Context:** An earlier draft of API.md listed `PROPOSED`, `VALIDATED`, `REJECTED` and `BLOCKED` among the intent states. An intent can receive several proposals: a rejected one, then an allowed one, then a duplicate. The draft also had no state for "a live effect does not match and is being remediated", or for "a reviewer closed it without the authorized effect".
**Decision:**
- `PROPOSED`/`VALIDATED`/`REJECTED`/`BLOCKED` are `ProposalStatus` values on each proposal. ALLOW→VALIDATED, REJECT→REJECTED, and HOLD_FOR_REVIEW or DUPLICATE→BLOCKED.
- The intent state set is `AUTHORIZED, IN_FLIGHT, EXECUTING, UNKNOWN, RECONCILING, DISCREPANCY, CANCEL_REQUESTED, ESCALATED, COMPLETED, CANCELLED, CLOSED`.

**Consequences:** A rejected proposal leaves the intent `AUTHORIZED`, so a later correct proposal can still execute. The dashboard pipeline shows proposal outcomes separately from the intent state.

## ADR-030: Cancellation is an action on an intent, not an operation
**Status:** Accepted · **Implementation:** implemented (`POST /intents/{id}/cancel`, `engine.cancel`)
**Context:** An earlier draft listed `AUTHORIZATION_CANCEL` as an operation. A cancellation is always about an existing authorization's effect. A separate cancel intent would need its own authorization, binding and remediation, and could race the intent it cancels.
**Decision:** The operations are `REFUND` and `PAYMENT_AUTHORIZATION`. Cancelling is an operator action on the intent:
- with nothing live, the intent is `CANCELLED` at once;
- a pending refund or a hold goes `CANCEL_REQUESTED`, then a verified provider cancel/void (ADR-024), then `CANCELLED`, or `ESCALATED` if the provider refuses;
- a completed refund is `409 NOT_CANCELLABLE`, and an attempt still in progress is `409 ATTEMPT_IN_PROGRESS`.

**Consequences:** The cancel request is serialized with the intent's other activity under the same row lock. "Cancelled" is reported only after the provider shows it.

## ADR-031: The amount must match the authorization exactly
**Status:** Accepted · **Implementation:** implemented (`checks.py`)
**Context:** The reason codes `AMOUNT_EXCEEDS_AUTHORIZATION` and `AMOUNT_BELOW_AUTHORIZATION` could suggest that amounts up to the authorized one are acceptable. A smaller amount is also an agent error (e.g. unit confusion), and an "up to" rule would let one authorization be drained in pieces.
**Decision:** A proposal's amount must equal the authorized amount. Partial refunds are separate authorizations; each is checked against the order's remaining balance (`EXCEEDS_REMAINING_BALANCE`). An amount with more decimals than its currency allows is `422 INVALID_AMOUNT`, never rounded.
**Consequences:** Simple, auditable binding. *Planned research extension:* authorizations expressed as ranges or several lines.

## ADR-032: Authentication implementation
**Status:** Accepted · **Implementation:** implemented (`backend/gateway_api/security.py`, `routers/auth.py`)
**Context:** ADR-018 fixes token lifetimes and scopes. The implementation needed concrete choices that hold up in a single-process prototype.
**Decision:**
- **Access tokens:** HS256 JWTs with an algorithm allow-list. `iss`, `aud`, `sub`, `exp`, `iat` and `jti` are required, with 30 s leeway. The secret comes from `JWT_SECRET` (at least 32 bytes; `scripts/init_env.py` generates one); without it, a random per-process secret is used.
- **Passwords:** argon2id, at least 12 characters. Five failures lock the account for 15 minutes. Logins and API calls are rate limited in memory.
- **Refresh tokens:** opaque and stored hashed. They rotate on every use; a reused token revokes its whole family.
  - Browsers: an HttpOnly `SameSite=Strict` cookie on `/api/auth` plus the `X-IntentGuard-CSRF: 1` header. A browser never receives the token in a response body.
  - API clients: the token in the body.
- **Agents:** service tokens scoped to intent or customer ids, at most 300 s, revocable by `jti`. Agents cannot log in.

**Consequences:** No external identity provider is needed for the prototype. The in-memory limiter holds per process only (*planned:* a shared store for several gateway processes). *Planned:* MFA for reviewer/admin, and asymmetric signing if other services must verify tokens.

## ADR-033: Applying an investigator recommendation re-checks the gate and never writes state
**Status:** Accepted · **Implementation:** implemented (`investigator/service.apply_investigation`)
**Context:** Time passes between an investigation and an operator applying its recommendation, and the evidence may change.
**Decision:**
- Applying rebuilds the evidence bundle and re-runs the policy gate (`409 POLICY_REFUSED` if it now refuses). A recommendation is applied at most once (`409 ALREADY_APPLIED`).
- Actions call the engine's own operations: `MARK_COMPLETED` re-fetches the matching effects from the provider, `WAIT_AND_RECHECK` schedules a check, `CONTROLLED_RETRY` retries under the same key, `CANCEL_PENDING` runs verified recovery, and `ESCALATE` opens a review case.

**Consequences:** The investigator can never make the gateway report an outcome the provider does not show.

## ADR-034: Simulator-only endpoints sit behind SIMULATOR_MODE
**Status:** Accepted · **Implementation:** implemented
**Context:** Demos need fault injection, the simulator ledger, fresh orders and an on-demand worker tick. None of these may exist in a deployment that talks to a real provider.
**Decision:**
- `/api/dev/*` (faults, ledger, demo orders, worker tick) and the simulator's `/v1/faults` answer `404` unless `SIMULATOR_MODE=true`. The default is off; `docker-compose.yml` and the launcher turn it on for the simulated stack.
- `POST /dev/orders` creates numeric demo orders (`ORD-9xxxxxxx`) in both the gateway and the simulator, so the dashboard's demo scenarios can be repeated.

**Consequences:** The dashboard's demo cards say when `SIMULATOR_MODE` is off. Production configuration must leave it off.

## ADR-035: CI quality gates
**Status:** Accepted · **Implementation:** implemented (`.github/workflows/ci.yml`)
**Context:** The guarantees here are easy to erode silently: a schema drift, a PostgreSQL-only bug, a benchmark regression, a leaked secret.
**Decision:** CI runs:
- ruff;
- the backend suite on SQLite and on PostgreSQL 16;
- the OpenAPI drift check;
- Vitest, the route contract check, the build and `npm audit`;
- a quick benchmark that fails if the full protocol shows any duplicate effect, undetected wrong money or misreported outcome (`scripts/check_bench_safety.py`);
- gitleaks over the full history, and pip-audit;
- `docker compose build`.

**Consequences:** A safety regression in the protocol fails the build, not just a unit test. The quick benchmark checks the invariants, not the published numbers, which come only from full runs (ADR-023).
