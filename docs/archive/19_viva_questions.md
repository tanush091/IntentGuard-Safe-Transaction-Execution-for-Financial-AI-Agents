> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# 19. Viva / Oral Examination Questions & Answers

This document contains 32 comprehensive viva questions and simple, concise answers prepared for academic reviews, project defenses, and technical evaluations.

---

### Basic Concepts
**Q1: What is IntentGuard?**
*A1:* IntentGuard is an academic research prototype that introduces an intent-consistent transaction execution and recovery protocol to safeguard financial operations proposed by AI agents.

**Q2: Why shouldn't an AI agent directly execute financial operations?**
*A2:* AI agents are non-deterministic and prone to hallucinations, prompt injections, and numerical errors. Furthermore, when distributed network timeouts occur, an agent cannot safely determine if a transaction succeeded or failed.

**Q3: What is the central guiding principle of IntentGuard?**
*A3:* "Do not trust only what the AI says it did. Verify what actually happened in the external financial state."

**Q4: Does IntentGuard connect to real bank accounts or real money?**
*A4:* No. IntentGuard operates entirely within an isolated simulation sandbox using a dedicated mock payment service.

**Q5: What is the primary transaction workflow evaluated in this project?**
*A5:* Refund processing (e.g., refunding ₹1,500 for order ORD-204 to customer C-17).

**Q6: What is the secondary transaction workflow?**
*A6:* Payment authorization and cancellation (voiding holds).

---

### Architecture & Protocols
**Q7: Explain the high-level workflow from authorization to resolution.**
*A7:* Human authorization → Durable intent record → AI proposes structured action → Safety gateway evaluates 10 checks → Mock payment service execution → External-state verification → Final resolution.

**Q8: What is a Durable Intent Record?**
*A8:* An immutable database entry storing the exact authorized parameters (order, customer, amount, currency, operation, and operator) against which the AI proposal is verified.

**Q9: What are the 10 checks performed by the Safety Gateway?**
*A9:* 1. Customer match, 2. Order match, 3. Operation match, 4. Amount conformity, 5. Currency match, 6. Operator authorization, 7. Duplicate effect check, 8. Concurrent attempt check, 9. Existing provider effect check, 10. FSM state validity.

**Q10: What is the difference between an Intent and an Attempt?**
*A10:* An Intent represents the authorized business goal (one per transaction). An Attempt represents an individual physical network request to execute that intent (multiple attempts can belong to one intent).

**Q11: What is an Effect in the IntentGuard ledger?**
*A11:* An Effect is a verified record of external financial reality observed directly on the payment provider.

---

### Distributed Systems & Reconciliation
**Q12: What happens when an execution request times out?**
*A12:* The attempt is marked `UNKNOWN`, and the state machine transitions to `RECONCILING`. The system does NOT retry immediately.

**Q13: Why is an immediate retry after a timeout dangerous?**
*A13:* The request might have succeeded at the provider right before the connection dropped. An immediate retry creates a duplicate transaction (e.g., double refund).

**Q14: How does the Active Reconciliation Engine resolve an UNKNOWN state?**
*A14:* It queries the mock payment provider by provider reference and order ID. If it finds a settled refund matching the intent, it marks it complete. If the provider has no record, it permits a controlled retry. If an incorrect effect is found, it triggers cancellation or escalation.

**Q15: What is an Idempotency Key and how is it used?**
*A15:* A unique token attached to a request so that if the provider receives the exact same request twice, it processes it only once. IntentGuard generates deterministic idempotency keys bound to the intent ID and attempt number.

**Q16: What happens if an agent crashes and restarts?**
*A16:* Because the intent record and attempt ledger are durable in the database, the restarted agent cannot issue a duplicate payment; the gateway detects the existing intent and blocks duplicate execution.

---

### State Machine & Recovery
**Q17: What is the Finite State Machine (FSM) in IntentGuard?**
*A17:* A formal model defining legal transaction states (e.g., `AUTHORIZED`, `PROPOSED`, `APPROVED`, `SUBMITTED`, `COMPLETED`, `UNKNOWN`, `RECONCILING`, `ESCALATED`) and prohibiting arbitrary state jumps.

**Q18: What happens if an unauthorized state transition is attempted?**
*A18:* The system raises an `InvalidStateTransitionException`, logs a security audit event, and halts processing.

**Q19: What is State-Aware Recovery?**
*A19:* A policy engine that decides whether an interrupted or mismatched transaction can be cancelled at the provider, retried with an incremented attempt number, or escalated for human review.

**Q20: When does a transaction transition to the ESCALATED state?**
*A20:* When an incorrect effect cannot be cancelled by the provider, when reconciliation yields an ambiguous outcome, or when maximum retry attempts are exhausted.

---

### AI & Agent Integration
**Q21: What is the ScriptedAgentProvider?**
*A21:* A deterministic agent implementation that outputs faithful or flawed proposals (wrong amount, wrong order, wrong operation) based on explicit profiles, ensuring reproducible experiments without network dependencies.

**Q22: How does the LLM adapter work?**
*A22:* It sends customer support dialogue to an LLM (Gemini, OpenAI, or Ollama) with a strict JSON schema prompt and parses the response into Pydantic models.

**Q23: Does the LLM possess payment service API keys?**
*A23:* No. The LLM only generates proposals; it has zero direct access to payment APIs.

---

### Evaluation, Benchmarks & Ablations
**Q24: What are the 4 baseline architectures compared against IntentGuard?**
*A24:* 1. Direct Agent (no gateway), 2. Fixed Pre-Execution Validation Alone, 3. API Idempotency Keys Alone, 4. LLM Reviewer / Dual-Agent.

**Q25: What is an Ablation Study in this research?**
*A25:* Systematically removing one component at a time (e.g., removing reconciliation, removing the gateway, removing duplicate detection) to isolate its impact on safety and duplicate prevention.

**Q26: What key metrics are measured in the benchmark?**
*A26:* Incorrect execution rate, duplicate effect rate, legitimate-task completion rate, false block rate, reconciliation success rate, and audit completeness.

**Q27: How many scenarios are generated in the benchmark?**
*A27:* 250 synthetic scenarios across 12 failure categories.

---

### Engineering & Security
**Q28: Why is the audit log append-only?**
*A28:* To guarantee complete regulatory auditability and prevent accidental or malicious tampering with historical transaction events.

**Q29: What database engines are supported?**
*A29:* SQLite by default for zero-setup local research; PostgreSQL via Docker Compose for production-like relational persistence.

**Q30: How does IntentGuard protect against Prompt Injection?**
*A30:* Prompt injection may manipulate the AI's proposal, but the Safety Gateway validates that proposal against the immutable, human-authorized intent record. Any injected amount or order is blocked.

**Q31: What technology stack is used for the frontend dashboard?**
*A31:* React, Vite, Recharts, and Vanilla CSS with modern glassmorphism.

**Q32: What is the main conclusion of the research?**
*A32:* Decoupling AI proposal from execution and pairing durable intent validation with active external-state reconciliation effectively eliminates duplicate and incorrect transactions under network uncertainty while preserving legitimate task completion.
