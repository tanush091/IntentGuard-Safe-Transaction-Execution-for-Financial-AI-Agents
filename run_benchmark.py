"""
Root Benchmark Entrypoint
Run 250 reproducible synthetic scenarios comparing 5 architectures and 6 ablation variants.
"""
import asyncio
from src.experiments.runner import BenchmarkSuite

if __name__ == "__main__":
    suite = BenchmarkSuite(scenario_count=250, seed=42)
    asyncio.run(suite.run_all())
