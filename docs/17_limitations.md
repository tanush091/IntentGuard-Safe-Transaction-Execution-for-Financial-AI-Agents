# 17. Limitations

## Explicit Limitations and Threats to Validity

IntentGuard is an academic research prototype. To preserve scientific rigor, we explicitly document its technical and operational limitations.

---

## 1. Simulated Payment Infrastructure
- The system evaluates performance against an in-memory/in-database mock payment service rather than a real banking core or payment network.
- Real payment gateways exhibit proprietary idiosyncrasies, undocumented error codes, delayed webhooks, multi-day batch settlement windows, and manual chargeback interventions that cannot be completely simulated in a lightweight HTTP testbed.

---

## 2. Synthetic Scenario Distribution
- The benchmark suite evaluates 250 synthetic scenarios across 12 failure categories. While these capture key distributed system and semantic failure modes, they do not replicate the long-tail empirical distribution of live e-commerce traffic.
- Evaluation on synthetic data does not mathematically guarantee identical safety rates in production environments.

---

## 3. LLM Variability & Non-Determinism
- Commercial LLMs (e.g., GPT-4o, Gemini 1.5) update their weights over time, causing slight variance in token generation and prompt susceptibility.
- While the scripted agent is 100% deterministic, LLM performance is subject to token limits, prompt drift, and vendor outages.

---

## 4. Single-Datacenter Database Assumptions
- The prototype persists state in a single relational instance (SQLite or PostgreSQL). In globally distributed multi-region architectures, database replication lag and split-brain network partitions introduce additional consistency challenges (CAP theorem constraints) that require distributed consensus protocols.
