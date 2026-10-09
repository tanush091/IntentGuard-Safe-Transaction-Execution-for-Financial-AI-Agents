"""
Command line (run from experiments/):

  python -m bench run [--seeds 10] [--start-seed 42] [--scenarios 300] [--arms all] [--workers N]
  python -m bench list-arms
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from bench import report
from bench.arms import ALL_ARMS, arm_meta
from bench.runner import run_job

# experiments/results, wherever the command is started from.
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "results"


def _llm_reviewer() -> Callable[[str], Any]:
    from intentguard.agents import LLMExtractor, LLMSettings

    settings = LLMSettings.from_env()
    if settings is None:
        raise SystemExit("--llm-reviewer needs LLM_PROVIDER (openai|ollama|gemini) and credentials in the environment")
    return LLMExtractor(settings).extract


def _git_commit() -> str:
    try:
        head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True,
                                        stderr=subprocess.DEVNULL).strip()
        return f"{head}-dirty" if dirty else head
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def cmd_run(args: argparse.Namespace) -> int:
    arms = ALL_ARMS if args.arms == "all" else [a.strip() for a in args.arms.split(",")]
    for a in arms:
        arm_meta(a)  # validates the name
    seeds = list(range(args.start_seed, args.start_seed + args.seeds))
    jobs = [(a, s) for a in arms for s in seeds]
    factory = _llm_reviewer if args.llm_reviewer else None
    print(f"Running {len(jobs)} cells: {len(arms)} arms × {len(seeds)} seeds × {args.scenarios} scenarios "
          f"on {args.workers} workers", flush=True)

    t0 = time.time()
    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_job, a, s, args.scenarios, factory): (a, s) for a, s in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            a, s = futures[fut]
            rows = fut.result()
            results.extend(rows)
            ok = sum(r["correct"] for r in rows)
            print(f"[{i:3d}/{len(jobs)}] {a:28s} seed {s}: {ok}/{len(rows)} correct ({time.time() - t0:6.0f}s)",
                  flush=True)

    order = {a: i for i, a in enumerate(arms)}
    results.sort(key=lambda r: (order[r["arm"]], r["seed"], r["scenario_id"]))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenarios_per_seed": args.scenarios,
        "git_commit": _git_commit(),
        "duration_s": round(time.time() - t0, 1),
        "reviewer": "llm" if args.llm_reviewer else "offline-extractor",
        "python": sys.version.split()[0],
    }
    summary = report.summarize(results, meta)
    run_dir = report.write(results, summary, Path(args.out))
    print(f"\nWrote {run_dir} (and {Path(args.out) / 'latest'})")
    print(report.to_markdown(summary).split("## Ablations")[0])
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the benchmark")
    run.add_argument("--seeds", type=int, default=10)
    run.add_argument("--start-seed", type=int, default=42)
    run.add_argument("--scenarios", type=int, default=300)
    run.add_argument("--arms", default="all", help="comma-separated arm names, or 'all'")
    run.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    run.add_argument("--out", default=str(DEFAULT_OUT))
    run.add_argument("--llm-reviewer", action="store_true", help="use a real LLM for baseline D")
    run.set_defaults(func=cmd_run)
    sub.add_parser("list-arms").set_defaults(func=lambda _a: print("\n".join(ALL_ARMS)) or 0)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
