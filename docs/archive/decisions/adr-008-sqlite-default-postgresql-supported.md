# ADR-008: SQLite by default, PostgreSQL supported

**Status:** Accepted (carries forward ADR-001 of the archived DECISIONS.md)

## Context
Local runs and the benchmark should need no database server. A deployment-like setup should use a
server database with row locks.

## Decision
`DATABASE_URL` defaults to a SQLite file; every SQLite transaction starts with `BEGIN IMMEDIATE`.
The benchmark uses shared-cache in-memory SQLite per arm and seed. `docker-compose.yml` runs the
gateway on PostgreSQL 16, where the engine locks the intent row with `SELECT ... FOR UPDATE`.

## Consequences
- Zero-setup local runs and fast experiments.
- All measured results and tests use SQLite. PostgreSQL code paths are not exercised by automated tests; adding that to CI is an open task.
