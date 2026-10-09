> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# Project Memory (MEMORY.md) — IntentGuard

## Current Status
- **Phase**: Core Protocol, Research Benchmark, Test Suite & Observability Dashboard **Completed and Verified**.
- **All Tests**: 11 passed in 2.30s (`pytest`).
- **Benchmark**: 250 synthetic scenarios completed with exit code 0 (`benchmark_results.json`).

## Completed Modules
- **Data & Models**: SQLAlchemy ORM models, Pydantic v2 schemas, database migrations/init.
- **Payment Service**: Mock payment server with refund and payment authorization APIs + configurable fault engine.
- **Gateway Core**: State machine, pre-execution validator, durable effects ledger, active reconciliation engine, state-aware recovery policies.
- **AI Agents**: Scripted benchmark agents and natural language parsing agent.
- **Experiments**: 250-scenario benchmark generator, 5 baseline implementations, 6 ablation studies.
- **Observability Dashboard**: Single-page dark mode glassmorphic UI with prescribed scenario demos and live state machine visualization.
- **Research Manuscript**: Full paper manuscript in `RESEARCH_PAPER_MANUSCRIPT.md`.
- **Deployment**: `docker-compose.yml` and `Dockerfile`.

## Current Focus / Next Opportunities
- Integrating optional external live LLM API keys (Gemini / OpenAI) for conversational chat testing.
- Launching the interactive dashboard in a live browser session.

## Known Gotchas & Insights
- On Windows systems, terminal stdout cp1252 character encoding does not support unescaped Rupee character `₹`. Always format currency outputs as `INR` in terminal prints.
- SQLite memory sessions require `StaticPool` or persistent file for multi-threaded async executions.
