# Academic Presentation Outline

## Slide Deck Structure for Project Defense & Conference Presentations

- **Slide 1: Title Slide**
  - Project Title: *Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes* (IntentGuard)
  - Presenter names, department, and academic institution.

- **Slide 2: The Rise of Autonomous Financial AI**
  - AI agents transitioning from chat interfaces to transactional execution (e-commerce, fintech, billing).
  - The promise of 24/7 autonomous support and instant dispute resolution.

- **Slide 3: The Danger: Triad of Financial AI Risk**
  - Semantic hallucinations & numerical drift.
  - Distributed systems uncertainty (timeouts, lost packets, two generals problem).
  - Blind retries leading to catastrophic double refunds.

- **Slide 4: Real-World Motivating Scenario**
  - Operator authorizes ₹1,500 refund for order ORD-204 to customer C-17.
  - AI reads adjacent invoice and proposes ₹15,000.
  - Or AI proposes ₹1,500, but request times out; agent blindly retries, issuing ₹3,000 in payouts.

- **Slide 5: Core Philosophy of IntentGuard**
  - *"Do not trust only what the AI says it did. Verify what actually happened in external state."*
  - Strict decoupling: Human Authorization → Intent Record → AI Proposal → Gateway → Payment Mock → Verification.

- **Slide 6: System Architecture Diagram**
  - Full pipeline walkthrough from Operator to Payment Simulator and Reconciliation loop.

- **Slide 7: The 10-Point Safety Gateway**
  - Invariant checks: Customer, Order, Operation, Amount, Currency, Operator, Duplicate Effect, Concurrent Attempt, Provider Effect, FSM State.

- **Slide 8: Transaction Finite State Machine**
  - Visual diagram showing legal transitions from `AUTHORIZED` to `COMPLETED`, `UNKNOWN`, `RECONCILING`, `CANCELLED`, and `ESCALATED`.

- **Slide 9: Active External-State Reconciliation**
  - Handling timeouts without naive retries.
  - The 8-step query-and-verify algorithm.

- **Slide 10: State-Aware Recovery**
  - Cancel-and-verify, controlled retry with deterministic idempotency keys, human escalation cases.

- **Slide 11: Experimental Methodology & Benchmark**
  - 250 synthetic scenarios across 12 failure modes.
  - 4 baseline architectures (Direct Agent, Fixed Validation, Idempotency Alone, LLM Reviewer).
  - 6 ablation configurations.

- **Slide 12: Empirical Results & Safety Comparison**
  - Quantitative comparison: IntentGuard eliminates incorrect and duplicate executions (0.0%) while maintaining high task completion.

- **Slide 13: Live Interactive Dashboard Demo**
  - Demonstration of the React/Vite observability dashboard: Intent Explorer, Safety Events, Reconciliation Inspector, and Experiment Visualizer.

- **Slide 14: Limitations & Ethical Scope**
  - Educational/academic simulation environment; absence of live financial network idiosyncrasies.

- **Slide 15: Future Work & Conclusion**
  - Cryptographic intent signing, formal verification (TLA+), and payment provider sandbox integration.
  - Concluding summary.

- **Slide 16: Q&A / Discussion**
