# Archive

> **Superseded - describes the earlier prototype. Numbers here are not measured results.**

These documents describe an earlier build: a vanilla-JS dashboard, a 250-scenario benchmark
across 12 failure modes, 11 test suites, and benchmark numbers written by a script rather than
measured. That code (`src/`, the old `backend/app/`, `mock-payment-service/`, `tests/`) was
deleted on 2026-10-09; it remains in git history. The files are kept for history only. Every file
carries the banner above.

Current documentation: [../README.md](../README.md).

| Archived | Current equivalent |
|---|---|
| `PRD.md`, `01_project_overview.md`, `02_problem_statement.md`, `15_market_and_real_world_applications.md`, `16_scope_and_future_work.md` | [../product/prd.md](../product/prd.md), [../../TASKS.md](../../TASKS.md) |
| `ARCHITECTURE.md`, `DESIGN.md`, `03_system_architecture.md`, `04_workflow.md`, `08_ai_agent.md`, `09_safety_gateway.md` | [../architecture/overview.md](../architecture/overview.md) |
| `05_state_machine.md`, `diagrams/state-machine.mmd` | [../architecture/state-machine.md](../architecture/state-machine.md) |
| `06_database_design.md`, `diagrams/database-er.mmd` | [../architecture/data-model.md](../architecture/data-model.md) |
| `07_api_documentation.md` | [../architecture/api.md](../architecture/api.md) |
| `10_reconciliation.md`, `11_fault_injection.md`, `diagrams/timeout-sequence-diagram.mmd` | [../architecture/reconciliation.md](../architecture/reconciliation.md), [../architecture/api.md#faults](../architecture/api.md#faults) |
| `12_experimental_methodology.md`, `13_baselines.md`, `14_ablation_study.md` | [../research/methodology.md](../research/methodology.md), [../research/results.md](../research/results.md) |
| `17_limitations.md` | [../research/limitations.md](../research/limitations.md) |
| `SECURITY.md`, `18_security_and_ethics.md` | [../security/threat-model.md](../security/threat-model.md) |
| `DECISIONS.md` | [../decisions/](../decisions/) |
| `TEST_PLAN.md` | [../testing/test-plan.md](../testing/test-plan.md) |
| `MEMORY.md`, `PHASE_0.md`, `git_workflow.md`, `19_viva_questions.md`, `presentation_outline.md` | none (project notes for the earlier build) |
| `spec/01`–`spec/10` | The original specification. Its demo flow is reproduced in [../operations/demo.md](../operations/demo.md); its paper outline is replaced by [../research/paper/outline.md](../research/paper/outline.md) |
| `diagrams/architecture.mmd`, `diagrams/sequence-diagram.mmd` | [../diagrams/intentguard_architecture.mmd](../diagrams/intentguard_architecture.mmd) |

## Removed from the repository root

- `PHASE_0.md`: a short summary of the earlier build, with absolute `file:///` links and the
  unmeasured numbers. The fuller document it pointed to is [PHASE_0.md](PHASE_0.md) here.
- `ANTIGRAVITY_MASTER_PROMPT.md`: the original build prompt. Its safety rules (simulation only,
  no real credentials, no invented results) are kept in `CONTRIBUTING.md` and `RULES.md`.
- `PROJECT_GUIDE.md`: a guide to the current build. Its content was moved into `docs/` (product,
  architecture, operations, research). Dropped: the FAQ and the suggestion to replay data from
  another project, which had no code behind it.

See also [UNSORTED.md](UNSORTED.md).
