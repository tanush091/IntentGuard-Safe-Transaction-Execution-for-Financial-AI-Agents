> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# 01. Project Overview

## Title
**Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes** (Short Title: **IntentGuard**)

---

## 1. Executive Summary
Autonomous Artificial Intelligence (AI) agents powered by Large Language Models (LLMs) are rapidly being piloted to automate enterprise workflows, including customer support, dispute resolution, procurement, and financial operations. However, deploying AI agents directly to interact with financial infrastructure creates existential risk:
- LLMs are prone to stochastic hallucination, producing incorrect transaction parameters (such as amounts, recipient identifiers, or operations).
- Distributed financial networks suffer from network latency, timeouts, server crashes, and delayed settlement statuses.
- Direct retries by an AI agent under uncertain conditions routinely result in catastrophic duplicate transactions and financial loss.

**IntentGuard** is an open-source, academic research prototype that introduces an **Intent-Consistent Transaction Execution and Recovery Protocol**. It enforces a strict separation of concerns:
> **The AI agent never directly executes financial operations.**
> 
> Instead, all operations flow through:
> **Human Authorization → Durable Intent Record → Structured AI Proposal → Safety Gateway → Mock Payment Simulator → External-State Verification → Final Resolution.**

---

## 2. Core Operational Philosophy
The foundational axiom of IntentGuard is:
> **"Do not trust only what the AI says it did. Verify what actually happened in the external financial state."**

When an AI agent reports "Refund of ₹1,500 completed successfully," the system does not accept this self-assessment as ground truth. Instead, IntentGuard observes durable records, queries payment provider ledgers, cross-references transaction references, and performs active reconciliation.

---

## 3. Safe Simulation Guarantee
- **Zero Real Money**: IntentGuard operates purely within an isolated simulation sandbox.
- **Zero External Financial Connections**: No bank APIs, card payment gateways, UPI networks, or live credentials (e.g., Stripe, Razorpay) are connected.
- **Reproducible Academic Experimentation**: All failures, network drops, and delayed provider states are deterministically controlled via explicit random seeds to allow rigorous comparative evaluation.

---

## 4. Key Protocol Capabilities
1. **Durable Intent Record**: Captures the operator's authorized boundary (order ID, customer ID, maximum amount, currency, and operation type).
2. **10-Point Safety Gateway**: Evaluates AI-generated structured proposals against durable authorizations before any external call is initiated.
3. **Formal Finite State Machine**: Prevents illegal transitions and guarantees that unverified outcomes cannot be prematurely marked as completed.
4. **Active Reconciliation**: Reconciles `UNKNOWN` outcomes by querying external provider state before authorizing any controlled retry.
5. **State-Aware Recovery**: Automatically triggers cancellation if an incorrect state exists and provider rules permit, or escalates to a human operator for dispute resolution.
