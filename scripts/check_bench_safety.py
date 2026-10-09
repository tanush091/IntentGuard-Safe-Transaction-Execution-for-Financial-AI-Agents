"""
CI safety gate for the benchmark (docs/TEST_PLAN.md): the full protocol must never duplicate an
effect, leave wrong money undetected, or misreport an outcome, in any seed.

    cd experiments && python -m bench run --seeds 2 --scenarios 60 --out ../.bench-ci
    python scripts/check_bench_safety.py .bench-ci/latest/summary.json

These three are the invariants the protocol claims (docs/research/manuscript.md); everything else in
the summary (completion, latency, review counts) is a measurement, not a pass/fail property.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ARM = "E_intentguard"
INVARIANTS = {
    "duplicate_effects": "duplicate effects",
    "undetected_wrong_minor": "undetected wrong money (minor units)",
    "misreports": "misreported outcomes",
}


def main(path: str) -> int:
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    arm = next((a for a in summary["arms"] if a["arm"] == ARM), None)
    if arm is None:
        print(f"[FAIL] {path} has no {ARM} arm")
        return 1
    meta = summary.get("meta", {})
    failures = []
    for key, label in INVARIANTS.items():
        per_seed = arm["metrics"][key]["per_seed"]
        bad = [v for v in per_seed if v != 0]
        status = "FAIL" if bad else "OK"
        print(f"[{status}] {label}: per seed {per_seed}")
        if bad:
            failures.append(label)
    print(f"        run {meta.get('run_id', '?')}, seeds {meta.get('seeds', '?')}, "
          f"{meta.get('scenarios_per_seed', '?')} scenarios per seed")
    if failures:
        print(f"[FAIL] the full protocol violated: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/check_bench_safety.py <results>/latest/summary.json")
    sys.exit(main(sys.argv[1]))
