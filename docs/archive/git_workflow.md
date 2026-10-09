> **Superseded - describes the earlier prototype. Numbers here are not measured results.** See [docs/README.md](../README.md) for the current documentation.

# Git Workflow & Team Collaboration Guide

This document outlines the version control strategy, standard commands, and team role division for the **IntentGuard** research prototype.

---

## 1. Core Git Commands Reference (PowerShell & Terminal)

```powershell
# Clone the repository
git clone https://github.com/tanush091/IntentGuard-Safe-Transaction-Execution-for-Financial-AI-Agents.git
cd IntentGuard-Safe-Transaction-Execution-for-Financial-AI-Agents

# Check current branch and changes
git status

# View local and remote branches
git branch -a

# Create and switch to a new feature branch
git checkout -b feature/gateway-validation

# Stage specific modified files or directories
git add backend/app/services/gateway_service.py

# Commit staged changes with descriptive message
git commit -m "feat(gateway): implement 10-point authorization validation check"

# Pull latest updates from develop with rebase
git pull origin develop

# Push branch to remote repository
git push -u origin feature/gateway-validation

# Merge branch into develop (after code review)
git checkout develop
git merge --no-ff feature/gateway-validation
```

---

## 2. Branching Strategy

| Branch | Purpose | Protection Rules |
| :--- | :--- | :--- |
| `main` | Production-ready stable prototype releases | PR + review required, all tests passing |
| `develop` | Integration branch for current iteration | Automated test run on every PR |
| `feature/agent` | AI agent development (Scripted & LLM adapters) | Scoped to `backend/app/agents/` |
| `feature/gateway` | Safety gateway, state machine, and validator | Scoped to `backend/app/services/` & `state_machine/` |
| `feature/mock-payment` | Payment simulator & fault injection engine | Scoped to `mock-payment-service/` |
| `feature/reconciliation` | Active reconciliation & recovery engine | Scoped to `backend/app/services/reconciliation_service.py` |
| `feature/frontend` | Modern React/Vite research studio dashboard | Scoped to `frontend/` |
| `feature/experiments` | Benchmark runner, baselines, & ablation suite | Scoped to `experiments/` & `scripts/` |
| `docs/research` | Academic paper, architecture, and system docs | Scoped to `docs/` |

---

## 3. Team Task & Role Division

When working as a multi-disciplinary research team, tasks are recommended as follows:

| Role / Member | Domain Ownership | Key Responsibilities | Primary Maintainer |
| :--- | :--- | :--- | :--- |
| **Backend & Core Engine** | Backend API & DB | FastAPI app routing, SQLAlchemy models, schema validation, database migrations. | U V Tanush (`tanush091`) |
| **Safety Protocol & Gateway** | Gateway & State Machine | 10-point safety checks, transactional state machine, idempotency ledger. | Narla Sindhuja (`NarlaSindhuja-5`) |
| **Payment Simulator** | Mock Payment & Faults | Mock payment engine, configurable fault injector, timeout and crash simulator. | U V Tanush (`tanush091`) |
| **Reconciliation & Recovery** | Active State Reconciliation | Provider state discovery, ledger reconciliation, controlled retries, escalation. | Narla Sindhuja (`NarlaSindhuja-5`) |
| **AI Agent Layer** | Scripted & LLM Layer | Deterministic scripted agent profiles, optional LLM provider adapter, prompt guard. | U V Tanush (`tanush091`) |
| **Frontend & Visualization** | Dashboard & Visuals | React dashboard, live state visualizer, transaction log table, review modal. | U V Tanush (`tanush091`) |
| **Research & Methodology** | Benchmark & Evaluation | 250+ synthetic scenarios, 4 baselines, 6 ablations, metrics export, Wilson intervals. | Narla Sindhuja (`NarlaSindhuja-5`) |

