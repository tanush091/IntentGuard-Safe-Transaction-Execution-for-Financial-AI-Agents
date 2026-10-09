# Product Requirements Document (PRD.md) — IntentGuard Recovery

> **Status:** Draft v1. Evolves the existing IntentGuard research prototype into a product direction.
> Market, competitor and pricing statements are **unvalidated hypotheses** until confirmed with design partners.

## 1. Product

**IntentGuard Recovery** — a payment execution, recovery and reconciliation layer that sits between a company's application or AI agent and its payment provider.

**One-line promise:** Every payment operation is authorized, tracked, verified and safely recovered when possible; unresolved exceptions are escalated with the evidence needed to resolve them.

**Core principle:** The LLM *interprets* exceptions. It never decides whether money is safe to move. Deterministic code and verified provider state control execution.

## 2. Problem

| # | Problem | Business impact |
|---|---------|-----------------|
| P1 | Payments and refunds get stuck in uncertain states (provider timeout, unknown result) | Customer complaints, manual investigation, duplicate-operation risk |
| P2 | Naive retries after a timeout create duplicate effects | Duplicate refunds/charges, inconsistent records, costly escalations |
| P3 | Reconciliation across provider records, webhooks, orders and ledgers is manual | Slow resolution, operational cost, incomplete audit trail |
| P4 | AI support agents can mis-read intent (wrong order, inflated amount) when given payment tools | Unauthorized or excessive financial effects |

A timeout is **not** proof of failure. A successful API response is **not** proof the authorized operation happened.

## 3. Goals and non-goals

### Goals
1. Prevent duplicate and unauthorized financial effects.
2. Verify the real provider-side outcome before declaring success, retrying, cancelling or escalating.
3. Recover automatically where provider semantics make it safe; escalate otherwise.
4. Keep AI agents outside the trust boundary (no credentials, no direct provider route).
5. Produce an append-only, verifiable audit trail with evidence for every decision.
6. Measure everything against a baseline without IntentGuard.

### Non-goals (v1)
- Guaranteeing "exactly-once" execution across arbitrary providers. The realistic target is **effectively-once where provider guarantees support it**, plus durable state, verification and controlled recovery.
- Real production banking rails or handling live card data.
- A general-purpose multi-agent framework (no LangChain/CrewAI/AutoGen in v1).
- Multi-currency FX conversion (must match authorized currency).
- End-user (customer) login. Users are operators, reviewers and admins.

## 4. Target users

| User | Need |
|------|------|
| **Operator** (support/finance ops) | Authorize refunds/payments, see status, resolve stuck cases |
| **Reviewer / compliance** | Work the review queue; verify audit integrity |
| **Developer / platform engineer** | Integrate agents and apps through the gateway API; run in sandbox |
| **AI agent (service principal)** | Submit proposals only; never touches the provider |
| **Admin** | Manage users, policies, provider connections |

**Initial market hypothesis:** mid-sized e-commerce and SaaS companies with frequent refunds or recurring payments. Indian merchants vs. global SaaS is an open decision (see DECISIONS.md, ADR-012).

## 5. Illustrative scenarios (not verified deployments)

1. **Timeout after execution.** ₹5,000 payment processed, response lost. System verifies provider state, records the verified outcome, creates no second charge.
2. **Refund with unknown result.** ₹3,000 refund times out. System checks refund status and remaining refundable balance, reconciles if confirmed, otherwise escalates with an AI-prepared evidence summary.
3. **AI agent mistake.** Agent proposes ₹4,000 refund for a customer with one ₹1,500 charge. Gateway blocks it deterministically; provider sees nothing.

## 6. Functional requirements

### P0 — Execution core
| ID | Requirement |
|----|-------------|
| F-01 | **Durable intent binding**: every operation anchored to an operator-created authorization (`intent_id`). |
| F-02 | **Deterministic validation**: customer, order, operation, amount, currency, remaining balance, operator permission, attempt budget. |
| F-03 | **Idempotent execution**: stable provider idempotency key per intent (`ig-<intent>-g<generation>`), unaffected by new agent request IDs or restarts. |
| F-04 | **Transaction state machine**: explicit legal transitions; terminal states immutable. |
| F-05 | **Timeout recovery**: timeout → `UNKNOWN` → reconcile before any retry. |
| F-06 | **Persist-before-call**: decision and attempt stored durably before any provider call. |

### P1 — Recovery and policy
| ID | Requirement |
|----|-------------|
| F-10 | **Active reconciliation**: query provider by transaction ID and order reference; "not found" counts as absence only after a configurable window (eventual consistency). |
| F-11 | **Webhook reconciliation**: handle delayed, duplicated and out-of-order provider events; verify signatures. |
| F-12 | **State-aware recovery**: cancel pending items and *verify* cancellation; completed effects cannot be reversed, only escalated. |
| F-13 | **Refund policy engine**: limits, authorization, remaining refundable balance. |
| F-14 | **Review queue**: open cases with discrepancy amount and evidence; operator resolve action. |
| F-15 | **AI exception investigator**: classify ambiguous cases and summarize evidence; recommendation must be one of a permitted, policy-checked action set. |

### P2 — Scale-out
| ID | Requirement |
|----|-------------|
| F-20 | Multi-provider adapters behind a common port. |
| F-21 | Operations dashboard: stuck payments, recovered cases, mismatches, audit evidence. |
| F-22 | Recovery analytics: auto-resolved rate, time to resolution, human-intervention rate, cost per resolved exception. |
| F-23 | Secondary workflow: payment authorization hold and cancellation. |

## 7. Phasing

| Phase | Scope | Exit criteria |
|-------|-------|---------------|
| **0 – Prototype (done per repo README)** | Protocol core, simulated provider, gateway API, benchmark, React dashboard | Seeded benchmark reproducible; test suite green |
| **1 – Execution core on a real sandbox** | One provider in test mode (e.g. Stripe test mode, or a Razorpay test integration if available), idempotent gateway, durable ledger, authz checks | Duplicate-effect rate zero in failure-injection suite |
| **2 – Recovery + AI investigator** | Timeout/webhook recovery, review queue, constrained LLM classifier | Auto-recovery on supported scenarios; every decision cites evidence |
| **3 – Reconciliation + dashboard + metrics** | Order/payment/refund matching, timelines, analytics, failure-injection report | End-to-end demo; measured results vs baseline |
| **4 – Expansion (conditional)** | Additional providers, enterprise policies, integrations | Only after Phase 3 reliability is demonstrated and design partners exist |

Timelines are intentionally not committed; a three-week MVP slice (execution core → recovery → reconciliation/dashboard) is a planning aid, not a guarantee.

## 8. Success metrics

| Metric | Definition | Target (initial) |
|--------|------------|------------------|
| Duplicate operations | Unintended duplicate completed effects | **0** across timeouts, restarts, concurrency |
| Unauthorized effects | Executed operations not matching authorization | **0** |
| Verification accuracy | Reported final state equals provider ground truth | 100% in benchmark |
| Recovery rate | Eligible simulated failures resolved with no human | Measured, report with CI |
| Human intervention | Share of cases needing an operator | Measured |
| Discrepancy escalation | Detected provider discrepancies with an open review case | 100% |
| Legitimate completion | Valid requests completed | Measured; must not collapse versus baselines |
| Resolution time | Failure detection → verified outcome | Measured |
| Cost | LLM + infra per transaction and per resolved exception | Measured |

All targets are evaluated against baselines (no protection, fixed validation, idempotency only, LLM reviewer) using a seeded benchmark and one ground-truth oracle. A fixed LLM confidence threshold is **not** an acceptable safety mechanism.

## 9. Competitive landscape (unverified)

Prior research named the following as partially overlapping; this has not been independently validated here:

| Existing | Overlap |
|----------|---------|
| Spreedly Recover | Failed-transaction retry and gateway-outage routing |
| Kosh.ai | AI reconciliation and exception management |
| Stripe | Idempotency keys, payment-state tracking, webhooks |
| StackOne | AI-agent refund workflows |

**Differentiation hypothesis:** a provider-independent *execution-assurance* layer that couples authorization, durable state, provider verification, evidence-backed recovery and exception-only LLM use. Whether any product offers this full combination has **not** been established.

## 10. Commercial hypotheses (to validate)

- Developer tier: sandbox and basic execution APIs.
- Growth tier: monitoring, automated recovery, reconciliation, usage-based pricing.
- Enterprise tier: multiple providers, custom policies, advanced audit, SLAs.

No prices are proposed. Validate with a small number of design partners first (support workload, payment volume, willingness to pay).

## 11. Risks

| Risk | Mitigation |
|------|------------|
| Dependence on provider observability | Document per-provider capabilities; escalate when state cannot be queried |
| Crowded market | Narrow positioning on verified execution and recovery |
| LLM misclassification | LLM output constrained to a permitted action set; deterministic policy gate; escalate on low evidence |
| Overclaiming guarantees | Use "effectively-once where provider semantics permit" wording everywhere |
| Compliance exposure with real money | Sandbox-only until security and payment-compliance review |

## 12. Open questions
1. Primary product direction to own first: execution reliability, AI reconciliation, autonomous refunds, or full platform?
2. First provider (Stripe test mode vs Razorpay test)?
3. Initial market (Indian businesses vs global SaaS/e-commerce)?
4. Is Redis/Celery needed in Phase 1, or is a PostgreSQL-backed worker sufficient?
