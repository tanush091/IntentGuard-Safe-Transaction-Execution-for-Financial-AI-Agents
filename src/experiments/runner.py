import asyncio
import json
import os
import time
from typing import Dict, Any, List
from src.database.connection import SessionLocal, init_db, engine
from src.database.models import Base
from src.mock_payment.service import payment_service
from src.experiments.generator import generate_benchmark_scenarios, SyntheticScenario
from src.experiments.baselines import BaselineRunner, BaselineExecutionResult
from src.experiments.ablations import AblationRunner

class BenchmarkSuite:
    def __init__(self, scenario_count: int = 250, seed: int = 42):
        self.scenario_count = scenario_count
        self.seed = seed
        self.scenarios = generate_benchmark_scenarios(count=scenario_count, seed=seed)

    async def run_all(self, output_path: str = "benchmark_results.json") -> Dict[str, Any]:
        print(f"\n================================================================================")
        print(f"  RUNNING INTENTGUARD RESEARCH BENCHMARK ({self.scenario_count} SCENARIOS, SEED={self.seed})")
        print(f"================================================================================\n")

        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        architectures = [
            ("Baseline A (Direct Access)", BaselineRunner.run_baseline_a_direct),
            ("Baseline B (Fixed Validation)", BaselineRunner.run_baseline_b_fixed_validation),
            ("Baseline C (API Idempotency Alone)", BaselineRunner.run_baseline_c_idempotency_alone),
            ("Baseline D (LLM Reviewer)", BaselineRunner.run_baseline_d_llm_reviewer),
            ("Proposed (IntentGuard)", None)
        ]

        summary_metrics: Dict[str, Dict[str, Any]] = {}

        for arch_name, runner_fn in architectures:
            print(f"[*] Evaluating: {arch_name}...")
            payment_service.reset()

            total_runs = len(self.scenarios)
            incorrect_count = 0
            duplicate_count = 0
            success_count = 0
            total_discrepancy = 0.0
            latencies = []

            if arch_name == "Proposed (IntentGuard)":
                db = SessionLocal()
                try:
                    for sc in self.scenarios:
                        payment_service.reset()
                        res = await BaselineRunner.run_proposed_intentguard(sc, db)
                        if res.is_incorrect:
                            incorrect_count += 1
                        if res.is_duplicate:
                            duplicate_count += 1
                        if res.success:
                            success_count += 1
                        total_discrepancy += res.unresolved_discrepancy
                        latencies.append(res.latency_ms)
                finally:
                    db.close()
            else:
                for sc in self.scenarios:
                    payment_service.reset()
                    res = await runner_fn(sc)
                    if res.is_incorrect:
                        incorrect_count += 1
                    if res.is_duplicate:
                        duplicate_count += 1
                    if res.success:
                        success_count += 1
                    total_discrepancy += res.unresolved_discrepancy
                    latencies.append(res.latency_ms)

            completion_rate = (success_count / total_runs) * 100.0
            avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

            summary_metrics[arch_name] = {
                "architecture": arch_name,
                "total_scenarios": total_runs,
                "incorrect_transactions": incorrect_count,
                "duplicate_effects": duplicate_count,
                "legitimate_completion_pct": round(completion_rate, 2),
                "unresolved_discrepancy_inr": round(total_discrepancy, 2),
                "avg_latency_ms": round(avg_latency, 2)
            }

        # Run Ablations
        print("\n[*] Evaluating Component Ablations...")
        ablation_metrics = await AblationRunner.evaluate_ablations(self.scenarios)

        report = {
            "meta": {
                "scenario_count": self.scenario_count,
                "seed": self.seed,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "baselines": list(summary_metrics.values()),
            "ablations": ablation_metrics
        }

        # Save output JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        self._print_ascii_table(summary_metrics, ablation_metrics)
        print(f"\n[+] Full results successfully written to {output_path}\n")
        return report

    def _print_ascii_table(self, baselines: Dict[str, Dict[str, Any]], ablations: List[Dict[str, Any]]):
        print("\n" + "=" * 105)
        print(f"{'Architecture / Approach':<35} | {'Incorrect':<10} | {'Duplicate':<10} | {'Completion %':<14} | {'Discrepancy (INR)':<18} | {'Latency':<8}")
        print("-" * 105)
        for b in baselines.values():
            print(f"{b['architecture']:<35} | {b['incorrect_transactions']:<10} | {b['duplicate_effects']:<10} | {b['legitimate_completion_pct']:<14}% | INR {b['unresolved_discrepancy_inr']:<13} | {b['avg_latency_ms']} ms")
        print("=" * 105)

        print("\n" + "=" * 105)
        print(f"{'Ablation Variant':<35} | {'Incorrect':<10} | {'Duplicate':<10} | {'Completion %':<14} | {'Discrepancy (INR)':<18} | {'Recovery %':<10}")
        print("-" * 105)
        for a in ablations:
            print(f"{a['variant']:<35} | {a['incorrect_transactions']:<10} | {a['duplicate_effects']:<10} | {a['legitimate_completion_pct']:<14}% | INR {a['unresolved_discrepancy_inr']:<13} | {a['recovery_success_pct']}%")
        print("=" * 105 + "\n")

if __name__ == "__main__":
    suite = BenchmarkSuite(scenario_count=250, seed=42)
    asyncio.run(suite.run_all())
