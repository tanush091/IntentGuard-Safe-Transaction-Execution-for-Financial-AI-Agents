# Experiments

Benchmark code and recorded results for IntentGuard. Method:
[docs/research/methodology.md](../docs/research/methodology.md). Results:
[docs/research/results.md](../docs/research/results.md).

## Layout

| Path | Contents |
|---|---|
| `bench/` | The benchmark package: `scenarios.py` (seeded generator, 30 categories in 6 families), `agent.py` (scripted agent and error model), `arms.py` (baselines A–D, IntentGuard, ablations), `runner.py` (simulated clock, crashes, concurrency), `scoring.py` (the oracle), `report.py` (statistics, `summary.md`/`.json`) |
| `results/latest/` | The run the documentation cites (`summary.md`, `summary.json`, `scenarios.csv`) |
| `results/20261005T141650Z/` | The same run under its run id |
| `results/quick/` | Output of `make bench-quick` (gitignored) |

## Running

`bench` adds `../backend` to `sys.path`, so run it from this directory without installing anything:

```bash
cd experiments
python -m bench run --seeds 2 --scenarios 60 --out results/quick   # quick check, about 30 s
python -m bench run --seeds 10 --start-seed 42 --scenarios 300      # full run; replaces results/latest/
python -m bench run --llm-reviewer                                  # baseline D with a real LLM (needs LLM_PROVIDER)
python -m bench list-arms
```

Or from the repository root: `make bench-quick`, `make bench-full`.

Options: `--arms A_direct,E_intentguard` (subset), `--workers N` (process pool size, default CPU
count − 1), `--out DIR` (default `experiments/results`).

Each run writes `<out>/<run_id>/` and copies it to `<out>/latest/`. `summary.json` is what the
gateway serves at `/api/experiments/latest` and the dashboard shows on its Experiments page.
