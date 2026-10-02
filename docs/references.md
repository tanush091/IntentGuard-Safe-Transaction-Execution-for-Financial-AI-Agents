# References & Related Literature

This document lists real academic publications, industry standards, specifications, and technical documentation relevant to transactional AI agents, distributed systems, idempotency, and financial safety.

---

## 1. Distributed Systems & Idempotency Specifications
1. **IETF RFC 7231**: Fielding, R., & Reschke, J. (2014). *Hypertext Transfer Protocol (HTTP/1.1): Semantics and Content*. Section 4.2.2 defines idempotent methods (`GET`, `PUT`, `DELETE`, etc.).
2. **IETF Internet-Draft**: Notts, M., & Reschke, J. (2023). *The Idempotency-Key HTTP Header Field*. draft-ietf-httpapi-idempotency-key-header-04.
3. **Stripe Engineering**: Brandao, M. (2017). *Designing robust and predictable APIs with idempotency*. Stripe Blog. Available at: `https://stripe.com/blog/idempotency`
4. **Gray, J., & Reuter, A.** (1992). *Transaction Processing: Concepts and Techniques*. Morgan Kaufmann Publishers. Foundational text on ACID transactions, two-phase commit, and recovery ledgers.
5. **Garcia-Molina, H., & Salem, K.** (1987). *Sagas*. In *ACM SIGMOD Record*, Vol. 16, No. 3, pp. 249-259. Formalization of compensating transactions and recovery under distributed failure.

---

## 2. AI Agents, Tool Use & Guardrails
6. **Schick, T., Dwivedi-Yu, J., Dessì, R., Raileanu, R., Lomeli, M., Zettlemoyer, L., Cancedda, N., & Scialom, T.** (2023). *Toolformer: Language Models Can Teach Themselves to Use Tools*. In *NeurIPS 2023*. arXiv:2302.04761.
7. **Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y.** (2022). *ReAct: Synergizing Reasoning and Acting in Language Models*. In *ICLR 2023*. arXiv:2210.03629.
8. **Inan, H., Upasani, K., et al.** (2023). *Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations*. Meta AI Research. arXiv:2312.06674.
9. **Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., & Fritz, M.** (2023). *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*. In *ACM Workshop on AISec*. arXiv:2302.12173.
10. **Revisiting Transaction Safety in AI**: Amodei, D., Olah, C., Steinhardt, J., Christiano, P., Schulman, J., & Mané, D. (2016). *Concrete Problems in AI Safety*. arXiv:1606.06565.

---

## 3. Financial Settlement & Reconciliation Industry Standards
11. **ISO 20022**: International Organization for Standardization. *Financial Services — Universal Financial Industry Message Scheme*. Standard for payment clearing and settlement messages.
12. **Federal Reserve Bank Financial Services**: *FedNow Service Operating Procedures* (2023). Rules governing immediate settlement and error resolution in real-time payments.
13. **National Payments Corporation of India (NPCI)**: *Unified Payments Interface (UPI) Procedural Guidelines* (2022). Section 7 on Dispute Resolution, Chargebacks, and Auto-Reconciliation of Timed-out Transactions.
