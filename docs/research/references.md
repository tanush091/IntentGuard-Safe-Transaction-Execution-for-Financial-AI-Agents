# References

Related work for the paper ([paper/outline.md](paper/outline.md), section 3). **Status** says how
far each entry has been checked:

- *Corrected*: an error in the earlier list was fixed (noted). Confirm against the primary source before citing.
- *To verify*: plausible, but the details (authors, version, section, date) have not been checked against the primary source.

None of these sources is used to support a number in [results.md](results.md). All results are
our own measurements.

## Idempotency, transactions and compensation

| # | Reference | Status |
|---|---|---|
| 1 | Fielding, R., & Reschke, J. (2014). *Hypertext Transfer Protocol (HTTP/1.1): Semantics and Content*. IETF RFC 7231, §4.2.2 (idempotent methods). Obsoleted by RFC 9110 (2022), §9.2.2 | To verify; prefer citing RFC 9110 |
| 2 | Jena, J., & Dalal, S. *The Idempotency-Key HTTP Header Field*. IETF Internet-Draft `draft-ietf-httpapi-idempotency-key-header` | Corrected: authors were listed as "Notts, M., & Reschke, J.". Version and date to verify |
| 3 | Leach, B. (2017). *Designing robust and predictable APIs with idempotency*. Stripe blog. https://stripe.com/blog/idempotency | Corrected: author was listed as "Brandao, M." |
| 4 | Gray, J., & Reuter, A. (1992). *Transaction Processing: Concepts and Techniques*. Morgan Kaufmann | To verify (often cited as 1993) |
| 5 | Garcia-Molina, H., & Salem, K. (1987). *Sagas*. Proc. ACM SIGMOD 1987; *SIGMOD Record* 16(3), 249–259 | To verify |

## AI agents, tool use and guardrails

| # | Reference | Status |
|---|---|---|
| 6 | Schick, T., et al. (2023). *Toolformer: Language Models Can Teach Themselves to Use Tools*. NeurIPS 2023. arXiv:2302.04761 | To verify (full author list) |
| 7 | Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR 2023. arXiv:2210.03629 | To verify |
| 8 | Inan, H., et al. (2023). *Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations*. arXiv:2312.06674 | To verify |
| 9 | Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., & Fritz, M. (2023). *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*. ACM AISec 2023. arXiv:2302.12173 | To verify |
| 10 | Amodei, D., Olah, C., Steinhardt, J., Christiano, P., Schulman, J., & Mané, D. (2016). *Concrete Problems in AI Safety*. arXiv:1606.06565 | Corrected: was labelled "Revisiting Transaction Safety in AI", which is not the paper's title. Relevance to this work is weak; consider dropping |

## Payment standards and operating rules

| # | Reference | Status |
|---|---|---|
| 11 | ISO 20022. *Financial services — Universal financial industry message scheme*. International Organization for Standardization | To verify (cite a specific part) |
| 12 | Federal Reserve Financial Services. *FedNow Service Operating Procedures* | To verify (edition, and that it covers error resolution as claimed earlier) |
| 13 | National Payments Corporation of India. *UPI Procedural Guidelines* | To verify. The earlier list cited "Section 7 on dispute resolution … auto-reconciliation of timed-out transactions"; that section reference is unconfirmed |
