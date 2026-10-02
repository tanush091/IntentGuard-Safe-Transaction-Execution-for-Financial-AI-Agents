# 13. Baseline Architectures

## Comparative Architectures for Empirical Benchmarking

To demonstrate the statistical necessity and protective efficacy of the IntentGuard protocol, we benchmark it against four real-world and literature-inspired baseline architectures.

---

## 1. Baseline A — Direct Agent Access (No Safety Layer)
```
[AI Agent] ───────────────► [Payment Service]
```
- **Description**: The AI Agent possesses direct network credentials to the payment API and invokes settlement endpoints autonomously.
- **Vulnerabilities**: Every hallucination immediately mutates external financial state. Timeouts trigger naive agent retries, causing severe duplicate payouts.
- **Industrial Precedent**: Early customer service chatbot integrations with autonomous tool-calling privileges.

---

## 2. Baseline B — Fixed Pre-Execution Validation Alone
```
[AI Agent] ──► [Input Validation Filter] ──► [Payment Service]
```
- **Description**: Evaluates input parameters against basic syntactic schemas (e.g., regex checks, type boundaries, positive numbers) before dispatching to the payment service.
- **Vulnerabilities**: Lacks durable intent context. A refund of ₹15,000 for an order originally worth ₹1,500 passes schema validation because 15,000 is a valid positive integer. Has no state machine or reconciliation logic.
- **Industrial Precedent**: Standard API gateway schemas (OpenAPI validation / API Gateway request validators).

---

## 3. Baseline C — API Idempotency Keys Alone
```
[AI Agent] ──► [Idempotency Key Generator] ──► [Payment Service]
```
- **Description**: The agent attaches an idempotency key (e.g., UUIDv4) to payment requests.
- **Vulnerabilities**: If the agent crashes or restarts, it frequently creates a *new* idempotency key for the same underlying intent, bypassing provider-level duplicate protection. Does not validate semantic alignment or handle active recovery.
- **Industrial Precedent**: Standard Stripe / Razorpay `Idempotency-Key` header usage without persistent intent binding.

---

## 4. Baseline D — LLM Reviewer / Dual-Agent Guardrail
```
[Worker Agent] ──► [Critic / Reviewer LLM] ──► [Payment Service]
```
- **Description**: A second "Reviewer" or "Supervisor" LLM inspects the proposal before execution and votes to approve or reject.
- **Vulnerabilities**: Stochastic and non-deterministic. Vulnerable to jailbreak techniques, hallucination in complex reasoning, high latency (1–3 seconds), and complete blindness to external network timeouts and post-execution drops.
- **Industrial Precedent**: LLM-as-a-Judge and multi-agent supervisor patterns (e.g., LangGraph supervisor architectures).

---

## 5. Proposed System — IntentGuard
```
[Durable Intent] ──► [AI Agent] ──► [10-Point Gateway] ──► [Payment Service]
                                             ▲                     │
                                             └──── Reconciliation ─┘
```
- Combines durable intent binding, 10-point deterministic validation, finite state machine transitions, attempt ledger, active external-state reconciliation, and state-aware recovery.
