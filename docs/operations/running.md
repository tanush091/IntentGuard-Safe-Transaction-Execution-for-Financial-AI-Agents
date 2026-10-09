# Running IntentGuard

Everything runs against the simulated payment provider (`paysim`). Never put real payment
credentials in `.env`.

This page describes how the code in this repository starts today. The target deployment is in
[../ARCHITECTURE.md](../ARCHITECTURE.md) (section 7), and the status of each platform feature,
built or planned, in [../FEATURES.md](../FEATURES.md) (section 9).

## Requirements

- Python 3.12 or newer (CI and the Docker image use 3.12; the suite also passes on 3.13)
- Node.js 20.19 or newer, or 22.12 or newer (Vite 7); CI and the Docker image use Node 22
- Docker with Compose v2 (optional)
- Windows launcher only: PowerShell and `curl`, both part of current Windows 10 and 11

## Windows: start.bat and stop.bat

From the repository root:

```bat
start.bat
```

`start.bat` and `stop.bat` at the root only call `scripts\start.bat` and `scripts\stop.bat`.
The launcher:

1. creates `.env` from `.env.example` if it is missing. If an existing `.env` still has
   `DATABASE_URL=sqlite:///./intentguard.db` (the earlier prototype's database), it is rewritten to
   `intentguard_gateway.db`; the old database file is left untouched;
2. activates the first virtual environment it finds: `.venv`, `backend\.venv` or `venv`;
3. installs `backend\requirements.txt` when one of the required Python modules cannot be imported;
4. runs `scripts\init_env.py`, which appends any setting `.env.example` has and `.env` lacks (for example `SIMULATOR_MODE` in a `.env` created before the rebuild), with the example value, and fills an empty `JWT_SECRET` and `WEBHOOK_SECRET`. Existing values are never changed
   with random values (and adds either line if it is missing). Existing values are never changed,
   and the secrets never leave the machine (`.env` is gitignored);
5. runs `npm install` in `frontend\` when `node_modules` is missing or `npm ls` reports that it no
   longer matches `package.json` (for example after a pull), then clears Vite's pre-bundle cache;
6. stops IntentGuard processes left over from a previous run;
7. runs `scripts\check_db.py`. If the SQLite database named by `DATABASE_URL` was created by an
   earlier schema (tables of the old prototype, or a `schema_version` other than the current `"2"`),
   it renames the database (with its `-wal`/`-shm` files) and the simulator's state file to
   `<name>.schema-<old>-<timestamp>.bak`. Nothing is deleted. The two files describe the same
   payments, so they start fresh together. PostgreSQL databases are left alone;
8. checks that ports 8001 and 8000 are free. If another program holds one, it stops with an error
   naming that program; it never stops other programs;
9. picks the dashboard port: 3000, or the next free one up to 3020;
10. opens one window each for the provider (`127.0.0.1:8001`) and the gateway (`127.0.0.1:8000`),
    both run from `backend\`, and the dashboard (Vite dev server, `--strictPort`). It waits up to
    60 seconds for each to answer, then opens the dashboard in the browser.

The Vite dev server binds to `127.0.0.1` only (`frontend/vite.config.js`), because it serves
source files. To reach it from another device, start it deliberately with `npm run dev -- --host`.

Press any key in the launcher window to stop everything, or run `stop.bat`. Both stop only the
windows titled `IntentGuard - *` and any `uvicorn gateway_api|provider_api` or Vite process of this
repository. Other programs on ports 3000, 8000 and 8001 are left alone.

| Address | What |
|---|---|
| http://localhost:3000 | Dashboard. Sign in with a demo account: [demo.md](demo.md) |
| http://127.0.0.1:8000/docs | Gateway API (Swagger UI); everything is under `/api` |
| http://127.0.0.1:8000/api/health, `/api/ready` | Liveness; readiness (database and provider reachable) |
| http://127.0.0.1:8001/docs | Provider API, including `/v1/faults` when `SIMULATOR_MODE=true` |
| http://127.0.0.1:8001/v1/ledger | Provider ground truth: every transaction, ignoring search visibility |

## Manual run (any OS)

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
python scripts/init_env.py        # creates/updates .env from .env.example and fills JWT_SECRET, WEBHOOK_SECRET
```

Then start three processes, each in its own terminal:

```bash
# 1. simulated payment provider on :8001
cd backend && python -m uvicorn provider_api.main:app --host 127.0.0.1 --port 8001

# 2. gateway on :8000 (creates the schema and seeds demo users and orders on first start)
cd backend && python -m uvicorn gateway_api.main:app --host 127.0.0.1 --port 8000

# 3. dashboard on http://localhost:3000 (Vite proxies /api to :8000)
cd frontend && npm run dev
```

With `make`: `make install`, `make run-provider`, `make run-gateway`, `make run-frontend`.

Both services read `.env` (`backend/intentguard/envfile.py`): first a `.env` in the working
directory, then the one at the repository root. A variable already set in the process
environment is never overridden, so the environment wins over the working-directory file, which
wins over the root file. Without a `.env` the code defaults apply, and they differ from
`.env.example` in ways that matter for a demo:

- `SIMULATOR_MODE` defaults to `false`: `/api/dev/*` and the provider's `/v1/faults` return 404,
  and the dashboard's demo cards are disabled;
- an empty `JWT_SECRET` makes the gateway use a random per-process secret (it logs a warning), so
  every login ends when the gateway restarts;
- an empty `WEBHOOK_SECRET` means the provider sends no webhooks and the gateway rejects any it
  receives.

### Where state is kept

When the services run from `backend/` with the default settings:

- gateway database: `backend/intentguard_gateway.db` (plus `-wal`/`-shm` files)
- provider state: `backend/paysim_state.json` (`PAYSIM_STATE_PATH`)

To start from scratch, stop both services and delete **both**. The gateway seeds users and the
demo orders `ORD-204`, `ORD-240`, `ORD-2041`, `ORD-311` (and registers the orders with the provider)
only when its users table is empty. Deleting just the provider state leaves the gateway with orders
the provider does not know, and refunds on them are rejected with `order_not_found`. The
dashboard's demo cards are not affected: each run creates a fresh order on both sides.

The gateway refuses to start on a database created by an earlier schema (`SchemaMismatch`).
`start.bat` moves such a SQLite file aside (see above); on a manual run, delete it or point
`DATABASE_URL` elsewhere.

### Without the provider service

`PAYMENT_PROVIDER=inprocess` embeds the simulator in the gateway; only the gateway and the
dashboard are needed. In this mode the simulator keeps its state in `paysim_state.json` in the
gateway's working directory (`PAYSIM_STATE_PATH` is not read), settles refunds immediately (no
`PAYSIM_SETTLE_DELAY_S`), and sends no webhooks. `/api/dev/*` act on the embedded simulator.

### Using an LLM

The agent endpoint (`POST /api/intents/{id}/agent`) and the exception investigator use offline
rules unless `LLM_PROVIDER` is set to `openai`, `ollama` or `gemini`, in the environment or in
`.env`. The response shows which was used: `extraction.model` on the agent endpoint
(`offline-rules` or `<provider>/<model>`), `model` on an investigation. Output from either model
is validated against a strict schema and rejected, not repaired, when it does not fit
(`422 INVALID_AGENT_OUTPUT`, `422 INVALID_INVESTIGATOR_OUTPUT`).

## Docker

```bash
docker compose up --build      # or: make up
docker compose down            # or: make down   (add -v to drop the pgdata and paysim volumes)
```

Compose reads `.env` at the repository root to fill `${JWT_SECRET}` and `${WEBHOOK_SECRET}`. Run
`python scripts/init_env.py` once before the first `up`; without it both are empty, with the
effects listed under the manual run.

| Service | Port | Notes |
|---|---|---|
| `postgres` | 5432 | `postgres:16-alpine`; volume `pgdata`; sandbox credentials in `docker-compose.yml` |
| `provider` | 8001 | Built from `backend/Dockerfile`; `SIMULATOR_MODE=true`; state in volume `paysim` (`/data`); `PAYSIM_SETTLE_DELAY_S=3`; signed webhooks to `http://gateway:8000/api/webhooks/paysim` when `WEBHOOK_SECRET` is set |
| `gateway` | 8000 | Same image; `DATABASE_URL` points at PostgreSQL; `SIMULATOR_MODE=true`; `experiments/results` is mounted read-only for the Experiments page |
| `frontend` | 3000 | Production build served by `nginx-unprivileged`, which listens on 8080 inside the container (published as 3000) and proxies `/api/` to the gateway |

The dashboard is at http://localhost:3000. nginx adds a Content-Security-Policy (scripts, fonts
and API calls from the same origin only, no inline scripts; inline style attributes are allowed
because React and Recharts set them) and `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` and `Cross-Origin-Opener-Policy` headers
(`frontend/security-headers.conf`). No container runs as root: the backend image runs as the
system user `intentguard` (uid 10001), and the nginx image is the unprivileged variant. Demo users
are seeded on the first start (`DEMO_SEED` defaults to true).

## Configuration

The settings that matter. "Code default" is what applies when neither the environment nor a
`.env` sets the variable; `.env.example` sets the values marked in the last column.

### Gateway (`backend/gateway_api/settings.py`)

| Variable | Code default | Meaning | `.env.example` |
|---|---|---|---|
| `DATABASE_URL` | `sqlite:///./intentguard_gateway.db` | Relative to the working directory. PostgreSQL: `postgresql+psycopg://user:pass@host:5432/db` | same |
| `PAYMENT_PROVIDER` | `http` | `http` talks to `provider_api`; `inprocess` embeds the simulator | `http` |
| `PAYMENT_SERVICE_URL` | `http://127.0.0.1:8001` | Provider base URL | same |
| `PROVIDER_TIMEOUT_S` | `5` | Provider call timeout; a timeout is an unknown outcome, never a failure | `5` |
| `ABSENCE_WINDOW_S` | `30` | How long after an attempt "not found" may be trusted as "did not happen" | `30` |
| `MAX_ATTEMPTS` | `3` | Attempt budget per intent | `3` |
| `UNKNOWN_REVIEW_AFTER_S` | `300` | An outcome still unknown after this long opens a review case | `300` |
| `POLL_INTERVAL_S`, `WORKER_INTERVAL_S` | `5`, `2` | Reconciliation polling; background worker period | same |
| `SIMULATOR_MODE` | `false` | Enables `/api/dev/*` (faults, ledger, demo orders, worker tick). Sandbox only | `true` |
| `DEMO_SEED` | `true` | Seeds demo users and orders when no user exists | `true` |
| `DEMO_PASSWORD` | `intentguard-demo` | Password of the seeded users; at least 12 characters | commented out |
| `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` | empty | With `DEMO_SEED=false`, creates the first admin when no user exists | empty |
| `JWT_SECRET` | empty | HS256 signing secret, at least 32 bytes (a shorter one stops startup). Empty: random per process | empty, filled by `init_env.py` |
| `COOKIE_SECURE` | `true` | `Secure` flag on the `ig_refresh` cookie. Browsers accept it on `http://localhost` | `true` |
| `WEBHOOK_SECRET` | empty | HMAC secret for provider webhooks; empty rejects them. An admin can also set one per provider (`PUT /api/admin/providers/paysim`), which takes precedence | empty, filled by `init_env.py` |
| `WEBHOOK_TOLERANCE_S` | `300` | Maximum age of a webhook signature timestamp | not set |
| `ACCESS_TOKEN_TTL_S`, `AGENT_TOKEN_MAX_TTL_S` | `900`, `300` | Access token lifetime; cap on agent service tokens | not set |
| `REFRESH_TOKEN_TTL_S`, `REFRESH_TOKEN_ABSOLUTE_S` | 7 days, 30 days | Refresh token lifetime per rotation, and for the whole family | not set |
| `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_S` | `5`, `900` | Account lockout | not set |
| `RATE_LIMIT_PER_MINUTE`, `LOGIN_RATE_LIMIT_PER_MINUTE` | `1200`, `20` | Per principal; per client IP for login (in process memory) | not set |
| `RESULTS_DIR` | `<repo>/experiments/results` | The Experiments page reads `RESULTS_DIR/latest/summary.json` | not set |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed browser origins | same |

The attempt budget, absence window and unknown-review timeout can also be changed by an admin
(`PUT /api/admin/policies`, the Admin page). Those values are stored in the database and replace
the environment values when the gateway starts. The kill switch, the maximum amount and separation
of duties exist only as admin policies.

### Provider (`backend/provider_api/main.py`)

| Variable | Code default | Meaning |
|---|---|---|
| `PAYSIM_STATE_PATH` | `paysim_state.json` | State file, relative to the working directory |
| `PAYSIM_SETTLE_DELAY_S` | `3` | Seconds a refund stays `PENDING` before it completes |
| `SIMULATOR_MODE` | `false` | Enables `/v1/faults` |
| `PAYSIM_WEBHOOK_URL` | empty | Where to send signed status-change events (`.env.example`: `http://127.0.0.1:8000/api/webhooks/paysim`) |
| `PAYSIM_WEBHOOK_SECRET` or `WEBHOOK_SECRET` | empty | Signing secret; webhooks are sent only when both URL and secret are set |

### LLM (`backend/intentguard/agents/llm.py`)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `offline` | `offline`, `openai`, `ollama` or `gemini` |
| `LLM_MODEL` | `gpt-4o-mini`, `llama3.1` or `gemini-1.5-flash` | Model name for the chosen provider |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | empty, `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama |
| `GEMINI_API_KEY` | empty | Google Gemini |

The benchmark's `--llm-reviewer` option reads the same variables (and `.env`).

## Tests and checks

```bash
cd backend && python -m pytest -q                 # 127 tests, about 1.5 minutes (make test)
```

To run the same suite against PostgreSQL, point `TEST_DATABASE_URL` at a dedicated database. Every
test drops and recreates its `public` schema, so the database name must contain `test` (the
fixtures refuse anything else):

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://intentguard:<password>@localhost:5432/intentguard_test python -m pytest -q
```

Dashboard and contract checks:

```bash
cd frontend
npm test                    # 19 Vitest tests
npm run check:contract      # every route the dashboard calls exists in docs/api/openapi.json
npm run build
```

Repository checks, from the root:

```bash
ruff check .                                   # lint (CI pins ruff 0.16.10; config in ruff.toml)
python scripts/export_openapi.py               # rewrite docs/api/openapi.json from the gateway app
python scripts/export_openapi.py --check       # exit 1 if the committed schema is out of date
```

Benchmark:

```bash
cd experiments && python -m bench run --seeds 2 --scenarios 60 --out results/quick    # quick (make bench-quick)
python scripts/check_bench_safety.py experiments/results/quick/latest/summary.json     # from the root
cd experiments && python -m bench run --seeds 10 --start-seed 42 --scenarios 300      # full (make bench-full)
```

`check_bench_safety.py` fails (exit 1) when the full protocol (`E_intentguard`) has a non-zero
`duplicate_effects`, `undetected_wrong_minor` or `misreports` in any seed. A run without `--out`
replaces `experiments/results/latest/`, which the documentation cites; see
[../research/methodology.md](../research/methodology.md#reproducing). What each test proves is in
[../testing/test-plan.md](../testing/test-plan.md).

### CI (`.github/workflows/ci.yml`)

Runs on every push and pull request:

| Job | Steps |
|---|---|
| Lint (ruff) | `ruff check .` |
| Backend tests (SQLite) + OpenAPI drift | `pytest -q`; `scripts/export_openapi.py --check` |
| Backend tests (PostgreSQL) | `pytest -q` against a PostgreSQL 16 service (`TEST_DATABASE_URL`) |
| Dashboard tests, contract, build | `npm ci`, `npm test`, `npm run check:contract`, `npm run build`, `npm audit --audit-level=high` |
| Quick benchmark (safety gate) | `python -m bench run --seeds 2 --scenarios 60 --workers 2`, then `scripts/check_bench_safety.py`; the summary is uploaded as an artifact |
| Secret scan + Python dependency audit | gitleaks over the full history; `pip-audit -r backend/requirements.txt` |
| Docker images build | `docker compose build` |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `start.bat`: "Port 8000 is already used by …" | Another program holds the port; close it |
| `start.bat` prints "… was created by an earlier IntentGuard …" | The old database and simulator state were renamed to `*.bak`; the gateway starts with a fresh database |
| Gateway fails to start with `SchemaMismatch` | Manual run or PostgreSQL with a database from an earlier schema; delete it or point `DATABASE_URL` elsewhere |
| Overview: "SIMULATOR_MODE is off, so the demo scenarios are disabled" | `SIMULATOR_MODE` is not `true` for the gateway or the provider (the gateway forwards `/api/dev/faults` to the provider's `/v1/faults`). A `.env` from an earlier version may lack the line: run `python scripts/init_env.py` (or `start.bat`), which adds it from `.env.example`, or set `SIMULATOR_MODE=true` yourself, then restart both |
| Signed out after every gateway restart | `JWT_SECRET` is empty; run `python scripts/init_env.py` |
| Login answers `ACCOUNT_LOCKED` | Five failed logins lock the account for `LOGIN_LOCKOUT_S` (15 minutes) |
| Experiments page: "No benchmark results yet" | `RESULTS_DIR/latest/summary.json` is missing. It defaults to `<repo>/experiments/results` |
| Refunds on `ORD-204` etc. fail with `order_not_found` | The provider lost its state but the gateway did not; see "Where state is kept" |
| `start.bat` rewrites `DATABASE_URL` in `.env` | An old `.env` pointed at `intentguard.db`, the earlier prototype's incompatible database; the old file is left untouched |
