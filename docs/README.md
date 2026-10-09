# IntentGuard documentation

IntentGuard is a research prototype. It runs only against a simulated payment provider with
synthetic customers, orders and money, and never connects to a real payment system.

These documents describe the code as it is in this repository: `backend/` (protocol, services,
tests), `experiments/bench/` (benchmark) and `frontend/` (React dashboard). Every result quoted
here comes from the measured run in
[`experiments/results/latest/summary.md`](../experiments/results/latest/summary.md).

## Reading order

New to the project:

1. [product/prd.md](product/prd.md): the problem, who it is for, goals and non-goals
2. [product/overview.md](product/overview.md): the four identities (intent, proposal, attempt, effect) and a glossary
3. [architecture/overview.md](architecture/overview.md): components, trust boundary, how a request flows
4. [operations/running.md](operations/running.md), then [operations/demo.md](operations/demo.md): run it and try the four demo scenarios

Working on the protocol:

- [architecture/state-machine.md](architecture/state-machine.md): every intent state and legal transition (generated from `TRANSITIONS`)
- [architecture/reconciliation.md](architecture/reconciliation.md): unknown outcomes, the absence window, recovery, key generations
- [architecture/data-model.md](architecture/data-model.md): tables and the constraints the database enforces
- [architecture/api.md](architecture/api.md): gateway and provider HTTP endpoints
- [security/threat-model.md](security/threat-model.md): what the gateway assumes and guarantees
- [testing/test-plan.md](testing/test-plan.md): the 42 tests, grouped by what they prove
- [decisions/](decisions/): architecture decision records

Research:

- [research/methodology.md](research/methodology.md): research question, hypotheses, scenarios, baselines, ablations, oracle, metrics
- [research/results.md](research/results.md): measured results, copied from `summary.md`
- [research/limitations.md](research/limitations.md): what the results do not show
- [research/paper/](research/paper/): paper outline and manuscript
- [research/references.md](research/references.md): related work

## Folder map

| Folder | Contents |
|---|---|
| `product/` | Requirements and core concepts |
| `architecture/` | How the system is built |
| `security/` | Threat model and invariants |
| `research/` | Method, results, limitations, paper, references |
| `decisions/` | ADRs, one per decision |
| `testing/` | Test plan |
| `operations/` | Running locally, on Windows, with Docker; demo walkthrough |
| `diagrams/` | Architecture diagram (Mermaid, HTML, PNG) and the generated state diagram |
| `archive/` | Documents from the earlier prototype, kept for history only. **Their numbers are not measured results.** |

`presentation/` is not tracked by git.
