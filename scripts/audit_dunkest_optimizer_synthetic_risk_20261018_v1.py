#!/usr/bin/env python3
"""Measure deterministic optimizer sensitivity to risk aversion on synthetic inputs."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from dunkest.config import Settings
from dunkest.optimize.milp import optimize_top_k_lineups


ROOT = Path(__file__).resolve().parents[1]
STEM = "dunkest_optimizer_synthetic_risk_20261018_v1"
SEED = 20261018


def main() -> None:
    rng = np.random.default_rng(SEED)
    roles = (["G"] * 16) + (["F"] * 16) + (["C"] * 8)
    n = len(roles)
    expected = rng.uniform(15.0, 32.0, n).round(3)
    spread = rng.uniform(6.0, 18.0, n).round(3)
    names = [f"Synthetic Player {index:02d}" for index in range(n)]
    names[0] = "Synthetic High Variance Guard"
    roles[0] = "G"
    expected[0] = 27.0
    spread[0] = 52.0
    players = pd.DataFrame({
        "player_name": names,
        "team": [f"T{index:02d}" for index in range(n)],
        "role": roles,
        "cr": rng.uniform(7.0, 13.0, n).round(2),
        "expected_pdk": expected,
        "p10": np.maximum(0.0, expected - spread / 2.0),
        "p50": expected.copy(),
        "p90": expected + spread / 2.0,
        "expected_min": rng.uniform(12.0, 36.0, n).round(1),
        "p_play": 1.0,
        "expected_plusvalenza": 0.0,
    })
    coaches = pd.DataFrame({
        "coach": ["Synthetic Coach A", "Synthetic Coach B"],
        "team": ["COACH_A", "COACH_B"],
        "coach_cr": [8.0, 9.0],
        "expected_coach_pdk": [5.0, 5.0],
        "p10_coach_pdk": [4.0, 4.0],
        "p50_coach_pdk": [5.0, 5.0],
        "p90_coach_pdk": [6.0, 6.0],
    })
    cases = [("expected_value", 0.0), ("risk_adjusted", 0.05),
             ("risk_adjusted", 0.10), ("risk_adjusted", 0.20),
             ("risk_adjusted", 0.50)]
    records = []
    for objective, risk_lambda in cases:
        settings = Settings.from_yaml(ROOT / "config/season_opener.yaml")
        settings.budget = 200.0
        settings.optimizer_objective = objective
        settings.risk_lambda = risk_lambda
        started = time.perf_counter()
        solution = optimize_top_k_lineups(players, coaches, settings, k=1)[0]
        duration = time.perf_counter() - started
        records.append({
            "objective": objective,
            "risk_lambda": risk_lambda,
            "solver_status": solution.meta.get("solver", {}).get("status"),
            "solver_objective_value": solution.meta.get("solver_objective_value"),
            "reported_expected_net_pdk": solution.expected_team_pdk,
            "p10_team": solution.p10_team,
            "p50_team": solution.p50_team,
            "p90_team": solution.p90_team,
            "budget_used": solution.budget_used,
            "selected_players": sorted(solution.players["player_name"].astype(str).tolist()),
            "coach": solution.coach,
            "module": solution.module,
            "duration_seconds": round(duration, 6),
            "validation_valid": bool(solution.meta.get("validation", {}).get("valid")),
        })
    result = {
        "audit_version": 1,
        "seed": SEED,
        "input_type": "deterministic_synthetic_player_and_coach_pool",
        "player_count": int(len(players)),
        "coach_count": int(len(coaches)),
        "candidate_objectives": cases,
        "candidate_count": len(records),
        "records": records,
        "all_solver_optimal": all(row["solver_status"] == "Optimal" for row in records),
        "all_independent_validation_passed": all(row["validation_valid"] for row in records),
        "risk_objectives_nonincreasing": all(
            records[index]["solver_objective_value"] >= records[index + 1]["solver_objective_value"]
            for index in range(1, len(records) - 1)
        ),
        "decision": "retain current policy; synthetic sensitivity verifies objective behavior only and cannot select a real-data strategy",
    }
    result["result"] = "pass" if (
        result["all_solver_optimal"]
        and result["all_independent_validation_passed"]
        and result["risk_objectives_nonincreasing"]
    ) else "fail"
    out = ROOT / "reports/audit"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{STEM}.json"
    md_path = out / f"{STEM}.md"
    if json_path.exists() or md_path.exists():
        raise SystemExit(f"Refusing to overwrite versioned output: {STEM}")
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Optimizer synthetic risk sensitivity — 2026-10-18 V1",
        "",
        f"Result: **{result['result'].upper()}**",
        "",
        f"- Synthetic pool: {len(players)} players and {len(coaches)} coaches; seed `{SEED}`.",
        "- Same player pool, coach pool, roster rules and budget used in all five runs.",
        "- All plusvalenza values are zero; no transfer history or real score labels are used.",
        "- Every solution is checked by the optimizer's independent validator.",
        "",
        "| Objective | Risk lambda | Solver objective | Expected net PDK | P10 | P50 | P90 | Budget | Seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        *[
            f"| {row['objective']} | {row['risk_lambda']:.2f} | {row['solver_objective_value']:.3f} | {row['reported_expected_net_pdk']:.3f} | {row['p10_team']:.3f} | {row['p50_team']:.3f} | {row['p90_team']:.3f} | {row['budget_used']:.2f} | {row['duration_seconds']:.4f} |"
            for row in records
        ],
        "",
        "## Selected players",
        "",
        *[
            f"- `{row['objective']}`, lambda `{row['risk_lambda']:.2f}`: {', '.join(row['selected_players'])}; coach {row['coach']}; module {row['module']}."
            for row in records
        ],
        "",
        "## Decision and limits",
        "",
        result["decision"],
        "Synthetic score distributions validate deterministic optimizer sensitivity and arithmetic only. They do not estimate real-game performance or justify a change to `risk_lambda`.",
        "",
        "## Reproduction",
        "",
        "```bash",
        f"PYTHONPATH=src .venv/bin/python scripts/{Path(__file__).name}",
        "```",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "result": result["result"],
        "all_solver_optimal": result["all_solver_optimal"],
        "all_independent_validation_passed": result["all_independent_validation_passed"],
        "risk_objectives_nonincreasing": result["risk_objectives_nonincreasing"],
        "records": [{key: row[key] for key in (
            "objective", "risk_lambda", "solver_status", "solver_objective_value",
            "reported_expected_net_pdk", "duration_seconds",
        )} for row in records],
    }, indent=2))
    print(f"Wrote {md_path.relative_to(ROOT)} and {json_path.relative_to(ROOT)}")
    if result["result"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
