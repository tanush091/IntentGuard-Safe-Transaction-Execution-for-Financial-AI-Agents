> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

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

---

## 4. Statistical Rigor & Confidence Bounds

To ensure scientific validity in peer-reviewed evaluation, metrics across benchmark iterations are analyzed with formal statistical bounds:

1. **Wilson Score Intervals for Zero-Error Rates**:
   For extreme rates like $R_{incorrect} = 0.0\%$ and $R_{duplicate} = 0.0\%$, standard normal approximation intervals degrade. We employ the Wilson score interval:
   $$w = \frac{p + \frac{z^2}{2n} \pm z\sqrt{\frac{p(1-p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$
   With $n=250$ scenarios and $z=1.96$ (95% confidence level), an observed zero-rate yields an upper bound of $\le 1.48\%$ under adversarial stress testing.

2. **Paired $t$-Test for Latency Overhead**:
   Comparing IntentGuard's validation round-trip latency ($T_{IntentGuard}$) against Direct Execution ($T_{Direct}$):
   $$t = \frac{\bar{d}}{s_d / \sqrt{n}}$$
   where $d_i = T_{IntentGuard, i} - T_{Direct, i}$. Hypothesis tests confirm whether safety checks introduce statistically significant latency penalties.

---

## 5. Experimental Failure Taxonomy & Scenario Matrix

The 250 evaluation scenarios are systematically partitioned across operational conditions:

| Category Code | Scenario Description | Count | Injected Fault Mechanism | Target Protocol Defense | Expected State |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `VAL-01` | Valid Standard Refund | 50 | Nominal execution | Fast-path idempotency & state machine | `COMPLETED` |
| `ERR-01` | Wrong Amount Parameter | 25 | Parameter divergence ($10\times$ inflation) | Invariant Check #4 (Amount bounded) | `REJECTED` |
| `ERR-02` | Wrong Customer ID | 20 | Recipient hallucination | Invariant Check #2 (Customer match) | `REJECTED` |
| `ERR-03` | Unauthorized Operation | 15 | Privilege escalation (Debit attempt) | Invariant Check #3 (Op authorization) | `REJECTED` |
| `FLT-01` | Network Timeout on Call | 30 | Dropped HTTP request packet | Controlled retry with idempotency key | `COMPLETED` |
| `FLT-02` | Lost Provider Response | 30 | Provider settles; ACK dropped | Active external reconciliation sweep | `COMPLETED` |
| `RCE-01` | Concurrent Racing Agents | 25 | Race condition on single intent | Relational lock / 409 Conflict | `COMPLETED` (1x) |
| `CRS-01` | Agent Mid-Flight Crash | 20 | Process termination before write | WAL state replay & ledger recovery | `COMPLETED` |
| `COR-01` | Corrupted Provider State | 15 | Tampered provider ledger record | Cancellation attempt & escalation | `ESCALATED` |
| `ESC-01` | Unsupported Provider Void | 20 | Provider settlement non-reversible | Operator review ticket generation | `ESCALATED` |

---

## 6. Research Contribution & Protocol Audit

- **Lead Protocol Architecture**: Multi-stage verification gateway and transactional state machine.
- **Safety & Reconciliation Verification**: Authored and validated by **Narla Sindhuja** (`NarlaSindhuja-5` / `narlasindhuja45@gmail.com`).
- **Review Status**: Integration test coverage verified across all 12 scenario taxonomy classes.

