#!/usr/bin/env python3
"""
IntentGuard Empirical Benchmark & Ablation Sweep Runner CLI.
Executes 250+ reproducible synthetic scenarios across 5 architectures and 6 ablation variants.
"""

import sys
from pathlib import Path

# Ensure UTF-8 output on Windows PowerShell
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import argparse
import asyncio
from src.experiments.runner import BenchmarkSuite


def main():
    parser = argparse.ArgumentParser(description="Run IntentGuard research benchmarks.")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    parser.add_argument("--scenarios", type=int, default=250, help="Number of scenarios to evaluate")
    args = parser.parse_args()

    print(f"Initializing IntentGuard Benchmark Harness (seed={args.seed}, scenarios={args.scenarios})...")
    suite = BenchmarkSuite(scenario_count=args.scenarios, seed=args.seed)
    asyncio.run(suite.run_all())


if __name__ == "__main__":
    main()
