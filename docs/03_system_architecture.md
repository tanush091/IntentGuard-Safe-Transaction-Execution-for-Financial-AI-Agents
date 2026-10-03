# 03. System Architecture

## Architecture Overview

IntentGuard sits as an intermediary security gateway and state reconciler between an AI Agent and financial execution backends.

```
                  ┌──────────────────────┐
                  │    HUMAN OPERATOR    │
                  └──────────┬───────────┘
                             │ authorizes (Order, Customer, Amount, Op)
                             ▼
                  ┌──────────────────────┐
                  │ DURABLE INTENT RECORD │
                  └──────────┬───────────┘
                             │ inputs intent context
                             ▼
                  ┌──────────────────────┐
                  │       AI AGENT       │
                  │ (Scripted / LLM Mod) │
                  └──────────┬───────────┘
                             │ structured proposal JSON
                             ▼
         ┌───────────────────────────────────────┐
         │       INTENT-CONSISTENCY GATEWAY       │
         │  - 10-Point Pre-Execution Validation  │
         │  - Idempotency & Concurrency Check   │
         │  - Audit Ledger Appender              │
         └───────────┬───────────────┬───────────┘
                     │               │
            Mismatch │               │ Approved
                     ▼               ▼
               ┌───────────┐   ┌───────────────────────────┐
               │   BLOCK   │   │ RECORD ATTEMPT & DISPATCH │
               └───────────┘   └─────────────┬─────────────┘
                                             │
                                             ▼
                               ┌───────────────────────────┐
                               │   MOCK PAYMENT SERVICE    │
                               │  (Simulated Settlement)   │
                               └─────────────┬─────────────┘
                                             │
                                             ▼
                               ┌───────────────────────────┐
                               │    READ EXTERNAL STATE    │
                               └─────────────┬─────────────┘
                                             │
                       ┌─────────────────────┼─────────────────────┐
                       │                     │                     │
                       ▼                     ▼                     ▼
                 ┌───────────┐         ┌───────────┐         ┌───────────┐
                 │ EXPECTED  │         │  UNKNOWN  │         │ INCORRECT │
                 └─────┬─────┘         └─────┬─────┘         └─────┬─────┘
                       │                     │                     │
                       ▼                     ▼                     ▼
                  [COMPLETED]        ┌───────────────┐     ┌───────────────┐
                                     │  RECONCILE    │     │CANCEL/ESCALATE│
                                     └───────┬───────┘     └───────────────┘
                                             │
                                     ┌───────┴───────┐
                                     │               │
                                     ▼               ▼
                                [COMPLETED]     [RETRY PERMITTED]
```

---

## Component Breakdown

### 1. Human Operator / Upstream Business System
Establishes the immutable boundary of financial authority. Authorizes exact transaction bounds (e.g., Refund for `ORD-204`, Customer `C-17`, Max ₹1,500 INR).

### 2. Durable Intent Record
A persistent database record storing authorized attributes. It acts as the immutable standard against which all subsequent AI actions are audited and enforced.

### 3. AI Agent (Scripted or Optional LLM Adapter)
Processes incoming customer conversations or task instructions. It formulates a structured execution proposal. Crucially, the AI agent **does not possess network credentials, API keys, or direct access** to the payment service.

### 4. Intent-Consistency Safety Gateway
Evaluates the AI agent's proposal against the durable intent record across 10 deterministic validation checks. If any check fails, execution is halted immediately and logged as `BLOCKED`.

### 5. Attempt Ledger & Idempotency Service
Assigns unique attempt numbers and cryptographic/deterministic idempotency keys to each outgoing execution attempt, tracking in-flight requests and preventing concurrent duplicates.

### 6. Mock Payment Service (Isolated Simulation)
A standalone FastAPI service simulating realistic payment provider behaviors: instantaneous success, pending queues, server timeouts, lost responses, and cancellations.

### 7. Active Reconciliation Engine
Invoked whenever an execution attempt returns an indeterminate status (`UNKNOWN` or network timeout). Queries the external provider to observe actual ground truth before permitting any retry.

### 8. State-Aware Recovery Service
Determines whether an erroneous or interrupted transaction can be safely cancelled at the provider, retried with strict idempotency, or escalated to human operators for review.
