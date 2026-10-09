"""
Aggregation and reporting. Every number in summary.json / summary.md is computed
here from per-scenario results; nothing is typed in by hand.
"""

from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from bench.arms import arm_meta

METRICS: dict[str, dict[str, str]] = {
    "correct_pct": {"label": "Correct scenarios", "unit": "pct", "better": "higher",
                    "description": "Every achievable intent fulfilled exactly once, nothing unintended live."},
    "completion_pct": {"label": "Legitimate completion", "unit": "pct", "better": "higher",
                       "description": "Achievable intents with their intended effect at the horizon."},
    "unsafe_scenarios": {"label": "Unsafe scenarios", "unit": "count", "better": "lower",
                         "description": "Scenarios ending with any duplicate or unintended live money movement."},
    "duplicate_effects": {"label": "Duplicate effects", "unit": "count", "better": "lower",
                          "description": "Extra live effects for an intent beyond the first."},
    "unintended_effects": {"label": "Unintended effects", "unit": "count", "better": "lower",
                           "description": "Live effects matching no achievable intent (wrong order/amount/customer...)."},
    "wrong_money_minor": {"label": "Wrong money moved", "unit": "minor", "better": "lower",
                          "description": "Amount of duplicate + unintended effects still live at the horizon."},
    "undetected_wrong_minor": {"label": "Undetected wrong money", "unit": "minor", "better": "lower",
                               "description": "Wrong money in scenarios where the system raised no flag."},
    "recovered_effects": {"label": "Reversed effects", "unit": "count", "better": "higher",
                          "description": "Transactions that were created and then cancelled/voided."},
    "misreports": {"label": "Misreported outcomes", "unit": "count", "better": "lower",
                   "description": "System claims success with no intended effect, or failure while one exists."},
    "false_blocks": {"label": "False blocks", "unit": "count", "better": "lower",
                     "description": "Achievable intents left unfulfilled after a correct proposal was rejected."},
    "unresolved_intents": {"label": "Unresolved at horizon", "unit": "count", "better": "lower",
                           "description": "Intents the system still reports as in progress at the horizon."},
    "review_cases": {"label": "Human reviews", "unit": "count", "better": "lower",
                     "description": "Cases escalated to a human (cost of safety)."},
    "latency_mean_ms": {"label": "Mean submit latency", "unit": "ms", "better": "lower",
                        "description": "Wall-clock time per agent submission, in-process provider."},
    "latency_p95_ms": {"label": "p95 submit latency", "unit": "ms", "better": "lower",
                       "description": "95th percentile wall-clock time per agent submission."},
}

_SUMS = ["unsafe_scenarios", "duplicate_effects", "unintended_effects", "wrong_money_minor",
         "undetected_wrong_minor", "recovered_effects", "misreports", "false_blocks", "unresolved_intents",
         "review_cases"]
_FIELD = {"unsafe_scenarios": "unsafe", "undetected_wrong_minor": "undetected_wrong_minor"}


def cell_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    m: dict[str, float] = {}
    m["correct_pct"] = 100.0 * sum(r["correct"] for r in rows) / len(rows)
    ach = sum(r["achievable_intents"] for r in rows)
    m["completion_pct"] = 100.0 * sum(r["fulfilled_achievable"] for r in rows) / ach if ach else 0.0
    for k in _SUMS:
        m[k] = float(sum(int(r[_FIELD.get(k, k)]) for r in rows))
    lat = [x for r in rows for x in r["submit_latency_ms"]]
    m["latency_mean_ms"] = float(np.mean(lat)) if lat else 0.0
    m["latency_p95_ms"] = float(np.percentile(lat, 95)) if lat else 0.0
    return m


def bootstrap_ci(values: list[float], *, resamples: int = 10_000, seed: int = 0) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2 or np.all(arr == arr[0]):
        return float(arr.mean()), float(arr.mean())
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(resamples, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def summarize(results: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    by_cell: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_cell[(r["arm"], r["seed"])].append(r)
    arms = list(dict.fromkeys(r["arm"] for r in results))
    seeds = sorted({r["seed"] for r in results})

    out_arms = []
    for arm in arms:
        per_seed = [cell_metrics(by_cell[(arm, s)]) for s in seeds if by_cell.get((arm, s))]
        metrics = {}
        for k in METRICS:
            vals = [c[k] for c in per_seed]
            lo, hi = bootstrap_ci(vals)
            metrics[k] = {"mean": float(np.mean(vals)), "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
                          "ci95": [lo, hi], "per_seed": vals}
        out_arms.append({**arm_meta(arm), "metrics": metrics})

    categories: dict[str, dict[str, dict[str, float]]] = {}
    families: dict[str, dict[str, dict[str, float]]] = {}
    for arm in arms:
        cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
        fam: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in results:
            if r["arm"] == arm:
                cat[r["category"]].append(r)
                fam[r["family"]].append(r)
        categories[arm] = {c: _group(rs) for c, rs in sorted(cat.items())}
        families[arm] = {f: _group(rs) for f, rs in sorted(fam.items())}
    return {"meta": {**meta, "seeds": seeds}, "metric_definitions": METRICS, "arms": out_arms,
            "categories": categories, "families": families}


def _group(rs: list[dict[str, Any]]) -> dict[str, float]:
    return {"scenarios": len(rs), "correct_pct": 100.0 * sum(r["correct"] for r in rs) / len(rs),
            "unsafe": sum(r["unsafe"] for r in rs), "wrong_money_minor": sum(r["wrong_money_minor"] for r in rs),
            "review_cases": sum(r["review_cases"] for r in rs)}


def _fmt(v: float, unit: str) -> str:
    if unit == "pct":
        return f"{v:.1f}%"
    if unit == "minor":
        return f"₹{v / 100:,.0f}"
    if unit == "ms":
        return f"{v:.2f}"
    return f"{v:.1f}"


def _cell(m: dict[str, Any], unit: str) -> str:
    lo, hi = m["ci95"]
    half = (hi - lo) / 2
    return _fmt(m["mean"], unit) if half == 0 else f"{_fmt(m['mean'], unit)} ± {_fmt(half, unit)}"


def to_markdown(summary: dict[str, Any]) -> str:
    meta = summary["meta"]
    cols = ["correct_pct", "completion_pct", "unsafe_scenarios", "duplicate_effects", "unintended_effects",
            "wrong_money_minor", "undetected_wrong_minor", "misreports", "false_blocks", "review_cases",
            "latency_mean_ms"]
    head = "| Architecture | " + " | ".join(METRICS[c]["label"] for c in cols) + " |"
    sep = "|---" * (len(cols) + 1) + "|"

    def table(group: set[str]) -> list[str]:
        lines = [head, sep]
        for a in summary["arms"]:
            if a["group"] in group:
                lines.append(f"| {a['label']} | " + " | ".join(_cell(a["metrics"][c], METRICS[c]["unit"]) for c in cols) + " |")
        return lines

    n = len(meta["seeds"])
    md = [
        "# IntentGuard benchmark results",
        "",
        f"Generated by `python -m bench run` — run `{meta['run_id']}`, commit `{meta.get('git_commit', '?')}`, "
        f"{meta['created_at']}.",
        f"{n} seeds ({', '.join(map(str, meta['seeds']))}) × {meta['scenarios_per_seed']} scenarios per seed; "
        f"the scenario mix is sampled per seed. Values are the mean per seed with a 95% bootstrap CI over seeds "
        f"(± half-width). Counts are per {meta['scenarios_per_seed']} scenarios.",
        "",
        "All arms receive identical agent behaviour and provider faults and are scored by the same oracle "
        "against the provider's ground-truth ledger (see `experiments/bench/scoring.py`).",
        "",
        "## Baselines vs. IntentGuard",
        "",
        *table({"baseline", "proposed"}),
        "",
        "## Ablations (IntentGuard with components removed)",
        "",
        *table({"proposed", "ablation"}),
        "",
        "## Correct-scenario rate by scenario family",
        "",
    ]
    fams = sorted({f for arm in summary["families"].values() for f in arm})
    md.append("| Architecture | " + " | ".join(fams) + " |")
    md.append("|---" * (len(fams) + 1) + "|")
    for a in summary["arms"]:
        fam = summary["families"][a["arm"]]
        md.append(f"| {a['label']} | " + " | ".join(
            f"{fam[f]['correct_pct']:.1f}%" if f in fam else "—" for f in fams) + " |")

    e = summary["categories"].get("E_intentguard")
    if e:
        md += ["", "## Where the full protocol is not correct", "",
               "Categories in which IntentGuard ended a scenario in a non-correct state (all seeds pooled).", "",
               "| Category | Scenarios | Correct | Unsafe | Wrong money | Human reviews |", "|---|---|---|---|---|---|"]
        rows = [(c, v) for c, v in e.items() if v["correct_pct"] < 100.0]
        for c, v in sorted(rows, key=lambda x: x[1]["correct_pct"]):
            md.append(f"| {c} | {v['scenarios']} | {v['correct_pct']:.1f}% | {v['unsafe']} | "
                      f"₹{v['wrong_money_minor'] / 100:,.0f} | {v['review_cases']} |")
        if not rows:
            md.append("| (none) | | | | | |")

    md += ["", "## Metric definitions", ""]
    for k, d in METRICS.items():
        md.append(f"- **{d['label']}** (`{k}`, {d['better']} is better): {d['description']}")
    return "\n".join(md) + "\n"


def write(results: list[dict[str, Any]], summary: dict[str, Any], out_dir: Path) -> Path:
    run_dir = out_dir / summary["meta"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(to_markdown(summary), encoding="utf-8")
    with open(run_dir / "scenarios.csv", "w", newline="", encoding="utf-8") as fh:
        fields = [k for k in results[0] if k != "submit_latency_ms"]
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    latest = out_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for name in ("summary.json", "summary.md", "scenarios.csv"):
        shutil.copyfile(run_dir / name, latest / name)
    return run_dir
