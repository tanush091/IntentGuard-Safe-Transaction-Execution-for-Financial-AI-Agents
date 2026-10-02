# ANTIGRAVITY MASTER PROMPT

## Master Specification: Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes

```
Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes

You are acting as a senior full-stack engineer, AI engineer, software architect, security engineer, QA engineer, technical writer, and research engineer.

Build a complete, runnable, well-documented academic/research prototype called:

Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes

The project must be safe for student/research use:

NEVER use real money.
NEVER connect to a real bank, UPI account, credit card, Stripe/Razorpay production account, or real financial account.
Build and use a completely simulated/mock payment service.
Clearly label the system as a research prototype/simulation.
Do not claim that simulated results guarantee safety in production.
Do not invent research results, market-size figures, citations, or benchmarks. Where external research is required, create a references section with real sources and clearly distinguish sourced facts from our own experimental results.

1. PROJECT GOAL
Build a system where an AI agent can propose a financial action such as:
"Refund ₹1,500 for order ORD-204 to customer C-17."
The system must NOT allow the AI agent to directly execute the financial operation.
Instead:
Human authorization → durable intent record → AI proposes structured action → intent-consistency safety gateway → simulated payment service → external-state verification/reconciliation → final resolution.
The central principle is:
Do not trust only what the AI says it did. Verify what actually happened.

2. PRIMARY USE CASE
Refund as main transaction.
Secondary: Payment authorization + cancellation.

3. IMPORTANT RESEARCH QUESTION
Can an intent-consistent transaction protocol reduce incorrect and duplicate final financial outcomes under timeouts, crashes, changed retries, and other controlled failures while still completing legitimate requests?

4. HIGH-LEVEL ARCHITECTURE
Human Operator -> Durable Intent Record -> AI Agent -> Intent-Consistency Gateway -> Mock Payment Service -> Read External State -> Expected / Unknown (Reconcile) / Incorrect (Cancel/Escalate).

5. TECHNOLOGY STACK
Backend: Python 3.12+, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic.
AI Layer: ScriptedAgentProvider, optional LLMAgentProvider.
Mock Payment Service: Separate FastAPI application.
Frontend: React, Vite, Recharts.
Testing: pytest, deterministic random seeds.
```
