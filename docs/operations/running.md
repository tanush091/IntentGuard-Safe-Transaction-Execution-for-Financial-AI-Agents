# Running IntentGuard

Everything runs against the simulated provider. Never put real payment credentials in `.env`.

## Requirements

- Python 3.12 or newer (CI and the Docker image use 3.12; also run locally with 3.13)
- Node.js 20 or newer, with npm (for the dashboard)
- Docker with Compose v2 (optional)

## Local (any OS)

From the repository root:

```bash
python -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

Then start three processes, each in its own terminal:

```bash
# 1. mock payment provider on :8001
cd backend && python -m uvicorn provider_api.main:app --port 8001

# 2. gateway on :8000 (seeds demo operators and orders on first start)
cd backend && python -m uvicorn gateway_api.main:app --port 8000

# 3. dashboard on http://localhost:3000 (proxies /api to :8000)
cd frontend && npm run dev
```

With `make` available, the same steps are `make install`, `make run-provider`,
`make run-gateway` and `make run-frontend`.

| Address | What |
|---|---|
| http://localhost:3000 | Dashboard |
| http://127.0.0.1:8000/docs | Gateway API (Swagger UI) |
| http://127.0.0.1:8001/docs | Provider API, including `POST /v1/faults` for fault injection |
| http://127.0.0.1:8001/v1/ledger | Provider ground truth |

### Where state is kept

When the services run from `backend/` with the default settings:

- gateway database: `backend/intentguard_gateway.db` (plus `-wal`/`-shm` files)
- provider state: `backend/paysim_state.json`

To start from scratch, stop both services and delete **both**. The gateway seeds demo orders
into the provider only when its own database has no operators, so deleting just the provider
state leaves the gateway with orders the provider does not know (`order_not_found`).

### Without the provider service

`PAYMENT_PROVIDER=inprocess` embeds the simulator in the gateway (state in `paysim_state.json`
next to it). Only the gateway and the dashboard are needed then.

### Using an LLM for the agent endpoint

The agent endpoint uses the offline rule extractor unless `LLM_PROVIDER` is set **in the
gateway's process environment** (a value in `.env` is not read for this):

```bash
export LLM_PROVIDER=openai OPENAI_API_KEY=...        # or: ollama (OLLAMA_BASE_URL), gemini (GEMINI_API_KEY)
cd backend && python -m uvicorn gateway_api.main:app --port 8000
```

`GET /info` shows which extractor is active. All variables:
[../architecture/overview.md#configuration](../architecture/overview.md#configuration).

## Windows

```bat
scripts\start.bat
```

The script:

1. creates `.env` from `.env.example` if it is missing;
2. uses `.venv` in the repository root if it exists, and installs Python and dashboard
   dependencies if they are missing;
3. stops any IntentGuard processes from a previous run, then checks that ports 8001 and 8000 are
   free. It never stops other programs; it stops with an error naming the program that holds the port;
4. picks the dashboard port: 3000, or the next free one up to 3020;
5. opens one window each for the provider and the gateway (both run from `backend\`) and the
   dashboard, waits for each to answer, and opens the dashboard in the browser.

Press any key in the launcher window to stop everything, or run `scripts\stop.bat`. It stops only
IntentGuard's uvicorn and Vite processes.

## Docker

```bash
docker compose up --build      # or: make up
docker compose down            # or: make down   (add -v to drop the database and provider volumes)
```

| Service | Port | Notes |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 16; volume `pgdata` |
| `provider` | 8001 | Built from `backend/Dockerfile`; state in volume `paysim` |
| `gateway` | 8000 | Same image; `DATABASE_URL` points at PostgreSQL; `experiments/results` is mounted read-only for the Experiments page |
| `frontend` | 3000 | Production build served by nginx, which proxies `/api` to the gateway |

The automated tests and the benchmark use SQLite; the PostgreSQL path is only exercised by this
Compose setup.

## Tests and benchmark

```bash
cd backend && python -m pytest                                        # 42 tests (make test)
cd experiments && python -m bench run --seeds 2 --scenarios 60 --out results/quick   # quick (make bench-quick)
cd experiments && python -m bench run --seeds 10 --start-seed 42 --scenarios 300     # full (make bench-full)
```

A benchmark run without `--out` replaces `experiments/results/latest/`, which the documentation
cites. See [../research/methodology.md](../research/methodology.md#reproducing).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `start.bat`: "Port 8000 is already used by …" | Another program holds the port; close it |
| Experiments page: "no benchmark results yet" | `RESULTS_DIR/latest/summary.json` is missing. It defaults to `<repo>/experiments/results` |
| Refunds fail with `order_not_found` | The provider lost its state but the gateway did not; see "Where state is kept" |
| `start.bat` rewrites `DATABASE_URL` in `.env` | An old `.env` pointed at `intentguard.db`, the earlier prototype's incompatible database; the old file is left untouched |
