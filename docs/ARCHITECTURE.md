# Architecture (ARCHITECTURE.md) — IntentGuard Recovery

## 1. System overview

IntentGuard Recovery is a middleware service between an application / AI agent and a payment provider. It owns submission, retry, cancellation and final resolution. The provider's observed effect is the source of truth.

**Core flow:** Authorization → Proposal → Validation → Execution → Observation → Reconciliation → Final Resolution

```
 Operator / App / Support ticket
              │
              ▼
   ┌─────────────────────┐
   │  AI Agent (UNTRUSTED)│  proposes {intent_id, customer_id, order_id, amount, currency, op}
   └──────────┬──────────┘
              ▼
 ┌────────────────────────────────────────────────────────────┐
 │                  IntentGuard Gateway (TRUSTED)             │
 │  decide    checks vs. intent + ledger (locked)             │
 │  reserve   attempt + stable idempotency key → IN_FLIGHT    │
 │  execute   provider call (no DB lock held)                 │
 │  verify    read back provider transaction                  │
 │  absorb    record effect, derive intent state from ledger  │
 │  drive     reconcile · recover · retry · escalate          │
 └───────┬───────────────────────────┬────────────────────────┘
         │                           │
         ▼                           ▼
 ┌──────────────┐          ┌─────────────────────┐
 │  PostgreSQL  │          │ Provider Port       │
 │  ledger+audit│          │  ├ Stripe (test)    │
 └──────────────┘          │  ├ Razorpay (opt.)  │
         ▲                 │  └ paysim (mock)    │
         │                 └─────────┬───────────┘
         │                           │ webhooks (signed)
 ┌───────┴────────┐                  ▼
 │ Exception      │◄──── Reconciliation worker
 │ Investigator   │      (matches orders, payments, refunds, events)
 │ (LLM, advisory)│
 └───────┬────────┘
         ▼
   Review queue ──► Operator Dashboard (React)
```

## 2. Layers

| Layer | Responsibility | Trust |
|-------|----------------|-------|
| **Client layer** | Operator dashboard, integrating apps, AI agents | Untrusted input |
| **API layer** | FastAPI routers, JWT auth, request validation (Pydantic v2), rate limits | Trusted boundary |
| **Gateway engine** | Checks, state machine, idempotency, attempt control | Trusted, deterministic |
| **Recovery layer** | Reconciliation worker, webhook ingestion, state-aware recovery, retry policy | Trusted, deterministic |
| **Exception investigator** | LLM classification + evidence summary; advisory only | Untrusted output, policy-gated |
| **Provider port/adapters** | Common interface over providers; fault injection in sim | Trusted code, untrusted responses |
| **Persistence** | PostgreSQL ledger, append-only audit log | Source of durable truth |
| **Coordination (optional)** | Redis for short-lived locks/queues; PostgreSQL stays authoritative | Non-authoritative |

## 3. Key design rules (invariants)

1. The agent **never** holds provider credentials or a network route to the provider.
2. Only the gateway submits, retries, cancels or finalizes.
3. Decisions and attempts are persisted **before** any external call.
4. Four identities stay separate: **intent** (operator authorization), **proposal** (agent request), **attempt** (one provider call), **effect** (observed at provider). Intent state is *derived* from attempts and effects, never asserted.
5. One stable provider idempotency key per intent generation: `ig-<intent_id>-g<generation>`. Generation increments only after a verified reversal.
6. A timeout yields `UNKNOWN`; no retry until reconciliation finds evidence. If the provider cannot be queried, hold for review.
7. "Not found" is evidence of absence only after `absence_window_s` (eventually consistent search).
8. Internal recovery (restoring agent memory, restarting) is never proof an external effect was reversed.
9. The LLM may classify and summarize; the policy gate decides what is permitted.
10. Audit log is append-only and hash-chained; entries are never rewritten.

## 4. State machine

```
AUTHORIZED ─► PROPOSED ─► VALIDATED ─► EXECUTING ─► COMPLETED
                 │            │            │
              REJECTED     BLOCKED         ├─► UNKNOWN ─► RECONCILING ─┬─► COMPLETED (effect found)
                                           │                            ├─► EXECUTING (controlled retry)
                                           └─► ESCALATED                └─► ESCALATED (discrepancy / provider unreachable)

PENDING (provider) ─► CANCEL_REQUESTED ─► CANCELLED (verified) | ESCALATED
```

The authoritative transition table lives in code (`backend/intentguard/domain.py`, `TRANSITIONS`). This diagram must be regenerated from it, not edited by hand.

## 5. Data flow

### 5.1 Happy path
1. Operator creates authorization → intent `AUTHORIZED`.
2. Agent/app posts proposal.
3. Gateway runs checks under lock; on pass, creates attempt, sets `IN_FLIGHT`.
4. Provider call (stable idempotency key).
5. Gateway reads back the provider transaction, records an `effect`, derives `COMPLETED`.

### 5.2 Lost response
1–4 as above; response lost → attempt `UNKNOWN` → reconcile: query by provider txn ID, then by order reference → compare customer, amount, currency, operation → effect found → `COMPLETED`. No second call.

### 5.3 Restart / new request ID
Same business request arrives with a new `request_id` → mapped to existing intent → `DUPLICATE` decision; no new attempt.

### 5.4 Discrepancy
Provider shows an effect not matching authorization → record `DISCREPANCY`, open `review_case` with unresolved amount; pending items are cancelled and verified, completed items are escalated.

### 5.5 Exception investigation
Ambiguous case → evidence bundle (provider responses, webhook events, ledger rows) → LLM returns `{classification, summary, recommended_action}` → policy gate checks action ∈ permitted set for the current state → execute or escalate.

### 5.6 Webhooks
Signed provider event → verify signature → dedupe by event ID → store → order by provider timestamp/sequence → feed reconciliation. Out-of-order and repeated delivery are expected.

## 6. Data model (summary)

| Table | Purpose |
|-------|---------|
| `users` | operators, reviewers, admins, service principals; role |
| `authorizations` / `intents` | operator authorization, limits, `approval_status`, derived state, generation |
| `agent_proposals` | every proposal incl. `request_id` |
| `gateway_decisions` | decision + reason code per proposal |
| `transaction_attempts` | one row per provider call; `provider_request_id`, status |
| `effects` | observed provider effects (unique per provider transaction) |
| `webhook_events` | raw verified events, dedupe key |
| `review_cases` | discrepancy, reason, status, resolution |
| `investigations` | LLM classification, evidence refs, recommended action, policy verdict |
| `audit_logs` | append-only, hash-chained |

DB-level guarantees: at most one live intended effect per intent (partial unique index); one effect row per provider transaction; audit table protected by triggers against UPDATE/DELETE.

## 7. Deployment topology

| Component | Dev | Production-like |
|-----------|-----|-----------------|
| Gateway API | uvicorn :8000 | container behind TLS proxy |
| Provider | paysim API :8001 | real provider **test mode** |
| Database | SQLite | PostgreSQL (e.g. Supabase) |
| Worker | in-process thread | separate process; Redis optional |
| Frontend | Vite dev :3000 | static build (e.g. Vercel) |

## 8. Repository layout

The system coordinates across a backend and a frontend; the contract between them is `API.md`.

### Monorepo (current plan)
```
intentguard/
├── backend/
│   ├── intentguard/        # protocol core: domain, checks, engine, ledger, audit, ports, agents
│   ├── gateway_api/        # FastAPI gateway + reconciliation worker
│   ├── provider_api/       # mock provider HTTP service
│   ├── paysim/             # provider simulator + fault injection
│   ├── adapters/           # (new) stripe_test/, razorpay_test/
│   ├── investigator/       # (new) LLM classifier, evidence builder, policy gate
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/            # typed client generated from API.md / OpenAPI
│   │   ├── components/
│   │   ├── pages/          # Overview, Intents, Review, Audit, Experiments
│   │   ├── hooks/
│   │   └── styles/         # tokens from DESIGN.md
│   └── package.json
├── experiments/
│   ├── bench/
│   └── results/
├── docs/                   # these documents live here
├── deploy/
├── scripts/
└── .github/workflows/
```

### Split-repo option
If backend and frontend become separate repositories, `API.md` (plus the generated OpenAPI file) is the only coordination surface; version it and publish it from the backend repo.

## 9. Technology stack

| Concern | Choice |
|---------|--------|
| Backend | Python, FastAPI, Pydantic v2 |
| ORM / DB | SQLAlchemy 2.0; SQLite (dev), PostgreSQL (prod) |
| Jobs | Background worker; Redis + Celery only when needed |
| LLM | Lightweight LLM API (Gemini / OpenAI / Ollama) behind one interface; offline rule extractor as default fallback |
| Frontend | React + Vite |
| Tests | pytest, Hypothesis, seeded benchmark |
| Containers | Docker Compose |

No orchestration framework in v1; a plain service, an explicit state machine and a constrained LLM call are sufficient.

## 10. Quality attributes

| Attribute | Approach |
|-----------|----------|
| Safety | Deterministic gate; LLM advisory; provider-verified outcomes |
| Durability | Persist-before-call; crash recovery marks `SUBMITTING` attempts `UNKNOWN` on startup |
| Auditability | Hash-chained append-only log; evidence reference on every recovery action |
| Observability | Metrics summary endpoint, per-intent timeline, live console |
| Honest limits | Effectively-once where provider semantics support it; no universal exactly-once claim |
