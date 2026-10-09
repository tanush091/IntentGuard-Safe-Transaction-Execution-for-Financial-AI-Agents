# IntentGuard documentation

IntentGuard is a research prototype. It runs only against a simulated payment provider with
synthetic customers, orders and money, and never connects to a real payment system. Every result
quoted in these documents comes from the measured run in
[`experiments/results/latest/summary.md`](../experiments/results/latest/summary.md).

The documentation has two layers:

- **Target spec** (the uppercase files in this folder): what *IntentGuard Recovery* should be. The
  code was rebuilt to it, and each file marks what is implemented and what is *planned*.
- **As-built reference** (the subfolders): what the code does today, file by file. Each page links
  to the target section it implements.

## Target spec

| Document | Contents |
|---|---|
| [PRD.md](PRD.md) | Problem, users, goals and non-goals, requirements with build status, phasing |
| [FEATURES.md](FEATURES.md) | Every feature with its status (implemented / partial / planned) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components, invariants, state model (generated from the code), data flows, deployment |
| [API.md](API.md) | The REST contract; the matching schema is [api/openapi.json](api/openapi.json) |
| [DESIGN.md](DESIGN.md) | Dashboard design system: tokens, components, pages, accessibility |
| [SECURITY.md](SECURITY.md) | Threat model, auth, RBAC, webhooks, LLM controls, checklist |
| [TEST_PLAN.md](TEST_PLAN.md) | What "working" means, test levels, coverage map to the real tests |
| [DECISIONS.md](DECISIONS.md) | All architecture decisions, one numbering (ADR-001 to ADR-035) |

## Reading order

New to the project:

1. [PRD.md](PRD.md), then [product/overview.md](product/overview.md): the problem, and the four
   identities (intent, proposal, attempt, effect)
2. [ARCHITECTURE.md](ARCHITECTURE.md), then [architecture/overview.md](architecture/overview.md):
   components, trust boundary, how a request flows
3. [operations/running.md](operations/running.md), then [operations/demo.md](operations/demo.md):
   run it, sign in, and try the four demo scenarios

Working on the code:

- [RULES.md](RULES.md) and [CONTRIBUTING.md](CONTRIBUTING.md): invariants you must not break, where things go
- [architecture/state-machine.md](architecture/state-machine.md): every intent state and legal transition (generated from `TRANSITIONS`)
- [architecture/reconciliation.md](architecture/reconciliation.md): unknown outcomes, the absence window, recovery, webhooks, reconciliation runs, the investigator
- [architecture/data-model.md](architecture/data-model.md): tables and the constraints the database enforces
- [architecture/api.md](architecture/api.md): every gateway and provider endpoint, as built
- [security/threat-model.md](security/threat-model.md): what the gateway assumes and guarantees
- [testing/test-plan.md](testing/test-plan.md): the tests, grouped by what they prove
- [TASKS.md](TASKS.md): open work

Research:

- [research/methodology.md](research/methodology.md): research question, hypotheses, scenarios, baselines, ablations, oracle, metrics
- [research/results.md](research/results.md): measured results, copied from `summary.md`
- [research/limitations.md](research/limitations.md): what the results do not show
- [research/paper/](research/paper/): paper outline and manuscript
- [research/references.md](research/references.md): related work

## Folder map

| Folder | Contents |
|---|---|
| `product/` | Core concepts and requirements as built |
| `architecture/` | How the system is built |
| `api/` | `openapi.json`, exported from the gateway by `scripts/export_openapi.py` (CI checks it) |
| `security/` | Threat model and invariants as built |
| `research/` | Method, results, limitations, paper, references |
| `decisions/` | Map from the prototype's old ADR numbers to [DECISIONS.md](DECISIONS.md) |
| `testing/` | Test plan as built |
| `operations/` | Running locally, on Windows, with Docker; demo walkthrough |
| `diagrams/` | Architecture diagram (Mermaid, HTML, PNG) and the generated state diagram |
| `archive/` | Documents from the earlier prototype and its old ADR files, kept for history only. **Their numbers are not measured results.** |

`presentation/` is not tracked by git.
