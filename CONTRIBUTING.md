# Contributing to IntentGuard

Thank you for contributing to **IntentGuard: Intent-Consistent Transaction Execution and Recovery for Financial AI Agents Under Uncertain Outcomes**.

## Research Prototype Safety Notice
- **NEVER** introduce real payment credentials, real banking API connections, or live payment gateway SDKs (e.g., Stripe live keys, Razorpay live keys, UPI endpoints).
- All financial operations **MUST** target the internal mock payment service simulator.
- Always preserve reproducible random seeds for experimental benchmarks.

## Code Standards
1. **Python**: Python 3.12+ compatible, strict type annotations, docstrings explaining assumptions, and Pydantic validation schemas.
2. **Architecture**: Adhere to Clean Architecture and Service Separation:
   - `backend/app/api/`: FastHTTP route endpoints and input validation.
   - `backend/app/services/`: Core business logic (authorization, gateway validation, idempotency, reconciliation, recovery).
   - `backend/app/models/`: SQLAlchemy relational ORM models.
   - `backend/app/schemas/`: Pydantic data transfer objects.
   - `backend/app/state_machine/`: Formal finite state machine transitions.
3. **Commit Messages**: Write clear, imperative commit messages (e.g., `feat: implement active reconciliation loop`, `test: add invalid state transition safety tests`).

## Team Roles & Subsystem Division
Refer to [Git Workflow](docs/git_workflow.md) for branch strategy and role distribution:
- **U V Tanush** (`tanush091`) — Project Architecture, Gateway & Payment Simulator, Core Framework
- **Narla Sindhuja** (`NarlaSindhuja-5` / `narlasindhuja45@gmail.com`) — Safety Protocol, Reconciliation Recovery Engine, Experimental Methodology & Benchmark Validation

