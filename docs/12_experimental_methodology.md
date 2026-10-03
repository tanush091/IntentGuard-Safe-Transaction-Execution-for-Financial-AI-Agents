# 12. Experimental Methodology

## Benchmark Protocol, Metrics, and Evaluation Methodology

To evaluate whether an intent-consistent transaction protocol reduces incorrect and duplicate financial outcomes under uncertain conditions, IntentGuard provides a reproducible benchmarking testbed.

---

## 1. Scenario Generation Framework
The benchmark generator creates a comprehensive test suite of 250 synthetic scenarios across 12 distinct failure and stress categories:
1. `VALID_STANDARD`: Normal, valid refund execution under clean network conditions.
2. `WRONG_AMOUNT`: Agent proposes incorrect amount (10x inflation or arbitrary reduction).
3. `WRONG_ORDER`: Agent transposes or hallucinates order identifier.
4. `WRONG_CUSTOMER`: Agent misidentifies customer recipient.
5. `WRONG_OPERATION`: Agent attempts unauthorized operation (e.g., PAYMENT instead of REFUND).
6. `WRONG_CURRENCY`: Agent submits invalid ISO currency code.
7. `TIMEOUT_RETRY`: Network drops before execution; tests controlled retry capability.
8. `LOST_RESPONSE`: Provider settles refund but response packet drops; tests duplicate avoidance.
9. `CONCURRENT_AGENTS`: Dual agents race to submit competing proposals for the same intent.
10. `AGENT_RESTART`: Agent crashes mid-flight and re-submits initial request.
11. `PROVIDER_CORRUPT`: Provider records inconsistent amount; tests cancellation/escalation.
12. `UNSUPPORTED_CANCEL`: Erroneous transaction cannot be reversed; tests human escalation.

---

## 2. Quantitative Evaluation Metrics & Formulas

### Safety Metrics
1. **Incorrect Execution Rate ($R_{incorrect}$)**:
   $$R_{incorrect} = \frac{\text{Settled Transactions with Parameter Mismatch}}{\text{Total Scenarios}} \times 100\%$$
   *Target: 0.0% in IntentGuard.*

2. **Duplicate Effect Rate ($R_{duplicate}$)**:
   $$R_{duplicate} = \frac{\text{Intents Producing } \ge 2 \text{ Settled Effects}}{\text{Total Completed Intents}} \times 100\%$$
   *Target: 0.0% in IntentGuard.*

3. **Unauthorized Financial Effect Count ($N_{unauth}$)**:
   Total count of financial effects settled on the mock provider without valid operator authorization.

### Reliability & Utility Metrics
4. **Legitimate Task Completion Rate ($R_{legit}$)**:
   $$R_{legit} = \frac{\text{Valid Intents Completed Successfully}}{\text{Total Valid Intents Submitted}} \times 100\%$$

5. **False Block Rate ($R_{false\_block}$)**:
   $$R_{false\_block} = \frac{\text{Valid Proposals Blocked by Gateway}}{\text{Total Valid Proposals}} \times 100\%$$

6. **Recovery & Reconciliation Success Rate ($R_{recon}$)**:
   $$R_{recon} = \frac{\text{Resolved Unknown Outcomes}}{\text{Total Unknown Outcomes Encountered}} \times 100\%$$

### Auditability
7. **Audit Trail Completeness ($R_{audit}$)**:
   $$R_{audit} = \frac{\text{Transactions with Complete Event Chains}}{\text{Total Transactions Executed}} \times 100\%$$

---

## 3. Execution & Reproducibility
- Benchmark runs execute using fixed deterministic pseudo-random seeds (`seed=42`, `seed=1`, `seed=2`, etc.).
- Every run outputs raw JSON and CSV data files in `experiments/results/` for independent verification.
- No results or figures are fabricated; all reported statistics are computed live from experiment logs.
