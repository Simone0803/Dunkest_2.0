#!/usr/bin/env python3
"""Paired bootstrap for same-constraint lineup baselines and strict sequential policies."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reports" / "audit"
LINEUP_ROUNDS = AUDIT / "dunkest_historical_lineups_fair_baselines_20261014_v1_rounds.csv"
TRANSFER_ROUNDS = AUDIT / "dunkest_historical_lineups_sequential_transfer_strict_20261014_v1_rounds.csv"
STEM = "dunkest_lineup_baselines_and_multigameweek_paired_bootstrap_20261014_v1"
OUT_CSV, OUT_JSON, OUT_MD = (AUDIT / f"{STEM}.csv", AUDIT / f"{STEM}.json", AUDIT / f"{STEM}.md")
REPLICATES = 10_000
SEED = 20261014


def bootstrap_mean_difference(
    frame: pd.DataFrame, left: str, right: str, *, reps: int = REPLICATES, seed: int = SEED
) -> dict:
    pair = frame[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
    n = len(pair)
    if n == 0:
        return {"left": left, "right": right, "n_paired_rounds": 0, "mean_difference": None,
                "median_difference": None, "win_rate": None, "ci95_low": None, "ci95_high": None}
    diff = pair[left].to_numpy(float) - pair[right].to_numpy(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(reps, n))
    means = diff[idx].mean(axis=1)
    return {
        "left": left, "right": right, "n_paired_rounds": int(n),
        "mean_difference": float(diff.mean()), "median_difference": float(np.median(diff)),
        "win_rate": float((diff > 0).mean()),
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
        "bootstrap_replicates": int(reps), "seed": int(seed),
    }


def main() -> int:
    if any(p.exists() for p in (OUT_CSV, OUT_JSON, OUT_MD)):
        raise SystemExit("Refusing to overwrite versioned bootstrap outputs.")
    results = []
    coverage = {}

    if LINEUP_ROUNDS.is_file():
        rounds = pd.read_csv(LINEUP_ROUNDS)
        required = {
            "status", "strict_actuals_complete_all_strategies", "model_realized_team_score",
            "baseline_realized_team_score", "pdk_per_cr_realized_team_score", "role_rank_realized_team_score",
        }
        if required.issubset(rounds.columns):
            eligible = rounds.loc[
                rounds["status"].eq("evaluated")
                & rounds["strict_actuals_complete_all_strategies"].fillna(False).astype(bool)
            ].copy()
            for col in (
                "model_realized_team_score", "baseline_realized_team_score",
                "pdk_per_cr_realized_team_score", "role_rank_realized_team_score",
            ):
                eligible[col] = pd.to_numeric(eligible[col], errors="coerce")
            eligible = eligible.dropna(subset=[
                "model_realized_team_score", "baseline_realized_team_score",
                "pdk_per_cr_realized_team_score", "role_rank_realized_team_score",
            ])
            coverage["same_constraint_baselines"] = {
                "rounds_optimized": int(rounds["status"].eq("evaluated").sum()),
                "rounds_strict_complete_all_strategies": int(len(eligible)),
                "rounds_excluded_for_incomplete_actuals": int(rounds["status"].eq("evaluated").sum() - len(eligible)),
            }
            comparisons = [
                ("model_realized_team_score", "baseline_realized_team_score", "model_milp_minus_previous5"),
                ("model_realized_team_score", "pdk_per_cr_realized_team_score", "model_milp_minus_pdk_per_cr"),
                ("model_realized_team_score", "role_rank_realized_team_score", "model_milp_minus_role_rank"),
            ]
            for i, (left, right, label) in enumerate(comparisons):
                row = bootstrap_mean_difference(eligible, left, right, seed=SEED + i)
                row.update({"experiment": "same_constraint_baselines", "comparison": label})
                results.append(row)
        else:
            coverage["same_constraint_baselines"] = {
                "status": "not_run", "reason": f"missing columns: {sorted(required - set(rounds.columns))}"
            }
    else:
        coverage["same_constraint_baselines"] = {"status": "pending", "missing_file": str(LINEUP_ROUNDS.relative_to(ROOT))}

    if TRANSFER_ROUNDS.is_file():
        rounds = pd.read_csv(TRANSFER_ROUNDS)
        required = {"season_id", "season", "round_index", "transfer_penalty", "status", "realized_net_team_score"}
        if required.issubset(rounds.columns):
            eligible = rounds.loc[rounds["status"].eq("evaluated")].copy()
            eligible["realized_net_team_score"] = pd.to_numeric(eligible["realized_net_team_score"], errors="coerce")
            pivot = eligible.pivot_table(
                index=["season_id", "season", "round_index"],
                columns="transfer_penalty", values="realized_net_team_score", aggfunc="first"
            ).reindex(columns=[0.0, 2.5, 5.0])
            paired = pivot.dropna()
            coverage["sequential_transfer_policy"] = {
                "rounds_optimized_any_scenario": int(eligible[["season_id", "season", "round_index"]].drop_duplicates().shape[0]),
                "rounds_complete_across_all_penalties": int(len(paired)),
                "rounds_excluded_for_incomplete_actuals": int(eligible[["season_id", "season", "round_index"]].drop_duplicates().shape[0] - len(paired)),
                "scenarios": [0.0, 2.5, 5.0],
                "scoring_malus_per_transfer": 5.0,
            }
            for i, (left, right, label) in enumerate([
                (2.5, 0.0, "penalty_2_5_minus_penalty_0"),
                (2.5, 5.0, "penalty_2_5_minus_penalty_5"),
                (5.0, 0.0, "penalty_5_minus_penalty_0"),
            ]):
                if len(paired):
                    diff = paired[left].to_numpy(float) - paired[right].to_numpy(float)
                    rng = np.random.default_rng(SEED + 100 + i)
                    idx = rng.integers(0, len(diff), size=(REPLICATES, len(diff)))
                    means = diff[idx].mean(axis=1)
                    row = {
                        "left": str(left), "right": str(right), "n_paired_rounds": int(len(diff)),
                        "mean_difference": float(diff.mean()), "median_difference": float(np.median(diff)),
                        "win_rate": float((diff > 0).mean()),
                        "ci95_low": float(np.quantile(means, 0.025)),
                        "ci95_high": float(np.quantile(means, 0.975)),
                        "bootstrap_replicates": REPLICATES, "seed": SEED + 100 + i,
                    }
                else:
                    row = {"left": str(left), "right": str(right), "n_paired_rounds": 0,
                           "mean_difference": None, "median_difference": None, "win_rate": None,
                           "ci95_low": None, "ci95_high": None}
                row.update({"experiment": "sequential_transfer_policy", "comparison": label})
                results.append(row)
        else:
            coverage["sequential_transfer_policy"] = {
                "status": "not_run", "reason": f"missing columns: {sorted(required - set(rounds.columns))}"
            }
    else:
        coverage["sequential_transfer_policy"] = {"status": "pending", "missing_file": str(TRANSFER_ROUNDS.relative_to(ROOT))}

    result = pd.DataFrame(results)
    result.to_csv(OUT_CSV, index=False)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Paired bootstrap over identical historical round IDs; strict complete-observed outcomes only. No missing selected-player actual is imputed as zero.",
        "replicates": REPLICATES, "seed": SEED, "coverage": coverage,
        "comparisons": results,
        "limitations": [
            "Historical player market and availability snapshots are incomplete; these results apply only to the reconstructed lagged candidate universe.",
            "Coach CR is fixed to 10 and coach actuals are reconstructed neutral-credit base scores, not exact price-adjusted official coach outcomes.",
            "Sequential transfer rosters are simulated recommendations, not the user's actual historical carried roster.",
            "Bootstrap intervals quantify sampling uncertainty conditional on the observed strict paired rounds; they do not remove market reconstruction bias.",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = [
        "# Same-constraint lineup baselines and multi-gameweek policy — paired bootstrap",
        "",
        f"Generated (UTC): {payload['generated_at_utc']}",
        "",
        "## Coverage",
        "",
        json.dumps(coverage, indent=2, ensure_ascii=False),
        "",
        "## Comparisons",
        "",
        result.to_string(index=False) if not result.empty else "No comparisons available yet.",
        "",
        "## Interpretation limits",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines.extend(["", "No production parameters were changed.", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"outputs": [str(p.relative_to(ROOT)) for p in (OUT_CSV, OUT_JSON, OUT_MD)],
                      "coverage": coverage, "comparisons": results}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
