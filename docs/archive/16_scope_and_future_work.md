> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# 16. Scope and Future Work

## Research Prototype Boundaries & Roadmap

Understanding the boundary between the current research prototype and future production deployment is essential for academic integrity.

---

## 1. Current Research Scope
- **Domain**: Automated refund processing (primary) and payment authorization/cancellation (secondary).
- **Execution Target**: Standalone, simulated Mock Payment Service running in local Docker/HTTP networks.
- **Protocol Core**: Deterministic 10-point safety gateway, append-only SQLite/PostgreSQL ledger, 14-state finite state machine, active query-based reconciliation, and state-aware recovery.
- **Agent Integration**: Deterministic scripted agent profiles (providing 100% reproducible baseline benchmarks) and an optional structured LLM adapter (Gemini/OpenAI/Ollama).

---

## 2. Near-Term Scope (Extensions)
- **Multi-Currency Dynamic Conversion**: Integrating real-time mock foreign exchange feeds with maximum allowable slippage limits.
- **Asynchronous Task Queues**: Offloading delayed reconciliation sweeps to distributed worker frameworks (Celery with Redis).
- **Policy Engine Pluggability**: Exporting gateway rules to declarative policy languages (Open Policy Agent Rego or AWS Cedar).

---

## 3. Production-Level Future Scope
1. **Live Payment Gateway Sandbox Integration**: Validating protocol adapters against real staging sandboxes (e.g., Stripe Testmode, Razorpay Sandbox, PayPal Sandbox).
2. **Cryptographic Intent Signing**: Requiring operators to sign durable intents using asymmetric key pairs (Ed25519) so intents cannot be tampered with in storage.
3. **Formal Protocol Verification**: Using TLA+ or Coq to mathematically prove that under any arbitrary interleaving of network drops and agent crashes, duplicate financial settlement is impossible.
4. **Hardware Security Modules (HSM)**: Anchoring gateway keys and payment tokens within dedicated cryptographic hardware.
5. **Decentralized Multi-Agent Consensus**: Expanding the protocol to support Byzantine-tolerant consensus when multiple independent agents coordinate multi-leg financial transfers.
