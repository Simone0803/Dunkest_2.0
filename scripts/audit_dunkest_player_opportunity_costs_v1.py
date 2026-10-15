#!/usr/bin/env python3
"""Counterfactual player opportunity-cost audit for one saved prediction run.

For every player in the rank-1 lineup, exclude that player and solve the same
MILP again with the same market, rules, risk objective, coach universe, and
capital-gain shadow price. Outputs are model-based decision diagnostics, not
realized-performance evidence.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from dunkest.config import Settings
from dunkest.names import player_key
from dunkest.optimize.milp import (
    MIN_PLAY_PROB,
    _solve_once,
    _validate_optimizer_inputs,
    optimize_top_k_lineups,
)
from dunkest.pipeline.optimize import run_optimize
from dunkest.rules.eligibility import unavailable_mask
from dunkest.rules.roster import RosterRules

ROOT = Path(__file__).resolve().parents[1]


def prepare_inputs(players: pd.DataFrame, coaches: pd.DataFrame, settings: Settings):
    players = players.copy()
    coaches = coaches.copy()
    players["role"] = players["role"].astype(str).str.strip().str.upper()
    players["team"] = players["team"].astype(str).str.strip().str.upper()
    coaches["team"] = coaches["team"].astype(str).str.strip().str.upper()

    if "coach_projection_source" in coaches.columns:
        verified = coaches["coach_projection_source"].astype(str).isin(
            {"verified_matchup", "verified_matchup_neutral_baseline"}
        )
        if "matchup_projection_available" in coaches.columns:
            verified &= coaches["matchup_projection_available"].fillna(False).astype(bool)
        coaches = coaches.loc[verified].copy()
    elif "matchup_projection_available" in coaches.columns:
        coaches = coaches.loc[
            coaches["matchup_projection_available"].fillna(False).astype(bool)
        ].copy()
    if coaches.empty:
        raise RuntimeError("No verified coach matchup rows in the saved run.")

    _validate_optimizer_inputs(players, coaches, settings)
    eligible = ~unavailable_mask(players)
    if "p_play" in players.columns:
        eligible &= pd.to_numeric(players["p_play"], errors="coerce").fillna(1.0).ge(MIN_PLAY_PROB)
    df = players.loc[eligible].copy()
    if "expected_min" not in df:
        df["expected_min"] = 24.0
    df["expected_min"] = pd.to_numeric(df["expected_min"], errors="coerce").fillna(0.0)
    df = df.loc[df["cr"].between(settings.min_cr, settings.max_cr)].copy()
    gain = pd.to_numeric(
        df.get("expected_plusvalenza", pd.Series(0.0, index=df.index)), errors="coerce"
    )
    df["expected_plusvalenza"] = gain.where(np.isfinite(gain), 0.0)
    df["_sort_name"] = df["player_name"].astype(str).str.strip().str.casefold()
    df["_sort_team"] = df["team"].astype(str).str.strip().str.upper()
    df = df.sort_values(
        ["_sort_name", "_sort_team", "role", "cr"], kind="stable"
    ).drop(columns=["_sort_name", "_sort_team"]).reset_index(drop=True)

    coach_df = coaches.copy()
    coach_df["_sort_coach"] = coach_df["coach"].astype(str).str.strip().str.casefold()
    coach_df["_sort_team"] = coach_df["team"].astype(str).str.strip().str.upper()
    coach_df = coach_df.sort_values(
        ["_sort_coach", "_sort_team", "coach_cr"], kind="stable"
    ).drop(columns=["_sort_coach", "_sort_team"]).reset_index(drop=True)
    return df, coach_df


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Saved prediction run directory")
    parser.add_argument("--config", default="config/season_opener.yaml")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    if not run_dir.is_dir():
        raise SystemExit(f"Prediction run directory not found: {run_dir}")
    players_path = run_dir / "predictions.parquet"
    coaches_path = run_dir / "coach_predictions.parquet"
    manifest_path = run_dir / "manifest.json"
    for path in (players_path, coaches_path, manifest_path):
        if not path.exists():
            raise SystemExit(f"Required prediction-run artifact missing: {path}")

    run_id = run_dir.name
    stem = f"dunkest_player_opportunity_cost_{run_id}_v1"
    out_dir = ROOT / "reports" / "audit"
    csv_path, json_path, md_path = (
        out_dir / f"{stem}.csv",
        out_dir / f"{stem}.json",
        out_dir / f"{stem}.md",
    )
    if any(path.exists() for path in (csv_path, json_path, md_path)):
        raise SystemExit(f"Refusing to overwrite versioned artifacts for {run_id}.")

    settings_path = Path(args.config)
    if not settings_path.is_absolute():
        settings_path = ROOT / settings_path
    settings = Settings.from_yaml(settings_path)
    players = pd.read_parquet(players_path)
    coaches = pd.read_parquet(coaches_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Run through the production entry point so the reference lineup has the
    # same coach verification gate and top-3 behavior as the actual pipeline.
    solutions = run_optimize(settings, players, coaches)
    reference = solutions[0]
    market, coach_market = prepare_inputs(players, coaches, settings)
    rules = RosterRules(max_from_same_team=settings.max_from_same_nba_team)
    base_objective = float(reference.meta["solver_objective_value"])
    shadow_price = float(reference.meta.get("capital_gain_shadow_price", 0.0))
    selected_names = set(reference.players["player_name"].astype(str))
    records = []

    for _, selected in reference.players.iterrows():
        excluded_key = player_key(selected["player_name"])
        alternative_market = market.loc[
            market["player_name"].map(player_key).ne(excluded_key)
        ].reset_index(drop=True)
        alternative, diagnostics = _solve_once(
            alternative_market,
            coach_market,
            settings,
            rules,
            settings.current_roster,
            settings.current_coach,
            [],
            set(),
            set(),
            capital_gain_shadow_price=shadow_price,
        )
        row = {
            "run_id": run_id,
            "reference_rank": reference.rank,
            "excluded_player": str(selected["player_name"]),
            "role": str(selected["role"]),
            "cr": float(selected["cr"]),
            "reference_slot": str(selected["slot"]),
            "reference_expected_pdk": float(selected["expected_pdk"]),
            "reference_score_multiplier": float(
                selected.get("score_multiplier", 1.0)
            ),
            "reference_net_team_pdk": float(reference.expected_team_pdk),
            "reference_optimizer_objective": base_objective,
            "alternative_solver_status": diagnostics.get("status"),
            "alternative_solve_time_seconds": diagnostics.get("solve_time_seconds"),
            "capital_gain_shadow_price": shadow_price,
        }
        if alternative is None or diagnostics.get("status") != "Optimal":
            row.update({
                "counterfactual_status": "inconclusive_solver",
                "opportunity_cost_objective_pdk_equivalent": np.nan,
                "opportunity_cost_net_expected_pdk": np.nan,
                "alternative_net_team_pdk": np.nan,
                "alternative_coach": None,
                "alternative_replacement_players": None,
            })
        else:
            alternative_names = set(alternative.players["player_name"].astype(str))
            row.update({
                "counterfactual_status": "optimal",
                "opportunity_cost_objective_pdk_equivalent": (
                    base_objective - float(alternative.meta["solver_objective_value"])
                ),
                "opportunity_cost_net_expected_pdk": (
                    float(reference.expected_team_pdk) - float(alternative.expected_team_pdk)
                ),
                "alternative_net_team_pdk": float(alternative.expected_team_pdk),
                "alternative_coach": alternative.coach,
                "alternative_replacement_players": "; ".join(
                    sorted(alternative_names - selected_names)
                ),
            })
        records.append(row)

    result = pd.DataFrame(records)
    result.to_csv(csv_path, index=False)
    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "input_manifest": str(manifest_path.relative_to(ROOT)),
        "season": manifest.get("season"),
        "gameweek": manifest.get("gameweek"),
        "objective": settings.optimizer_objective,
        "risk_lambda": settings.risk_lambda,
        "method": (
            "For each rank-1 selected player, remove only that player from the eligible "
            "market and solve the same MILP with identical settings and a fixed reference "
            "capital-gain shadow price. Opportunity costs are model-based counterfactuals."
        ),
        "reference": {
            "rank": reference.rank,
            "players": sorted(selected_names),
            "coach": reference.coach,
            "expected_net_team_pdk": reference.expected_team_pdk,
            "solver_objective": base_objective,
            "budget_used": reference.budget_used,
        },
        "counterfactuals": records,
        "complete_counterfactuals": int(result["counterfactual_status"].eq("optimal").sum()),
        "total_counterfactuals": int(len(result)),
        "interpretation_limitations": [
            "This quantifies model-implied opportunity cost, not realized PDK gained or lost.",
            "Removing one player allows all other roster choices and coach to change, under the same optimizer constraints.",
            "The capital-gain shadow price is held fixed to isolate the player's exclusion effect.",
            "No historical outcomes or frozen holdout results are used.",
        ],
    }
    json_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    valid = result.loc[result["counterfactual_status"].eq("optimal")]
    lines = [
        f"# Player opportunity-cost counterfactual — {run_id}",
        "",
        "## Reference lineup",
        "",
        f"- Objective: {settings.optimizer_objective}; risk lambda: {settings.risk_lambda}",
        f"- Coach: {reference.coach}",
        f"- Expected net team PDK: {reference.expected_team_pdk:.2f}",
        f"- Budget used: {reference.budget_used:.2f} CR",
        "",
        "## Method",
        "",
        "Each selected player is excluded in turn; the same MILP is re-solved using the same eligible market, coach candidates, budget, roster rules, objective and fixed capital-gain shadow price. This is a counterfactual diagnostic, not a realized-outcome backtest.",
        "",
        "## Results",
        "",
        f"- Completed optimal counterfactuals: {len(valid)} / {len(result)}",
    ]
    if not valid.empty:
        lines.extend([
            f"- Median objective opportunity cost: {valid['opportunity_cost_objective_pdk_equivalent'].median():.3f} PDK-equivalent",
            f"- Median net expected-PDK difference: {valid['opportunity_cost_net_expected_pdk'].median():.3f}",
            "",
            "| Excluded player | Role | CR | Slot | Objective gap | Net expected PDK gap | Replacement players |",
            "|---|---|---:|---|---:|---:|---|",
        ])
        for _, row in valid.iterrows():
            lines.append(
                f"| {row['excluded_player']} | {row['role']} | {row['cr']:.1f} | "
                f"{row['reference_slot']} | {row['opportunity_cost_objective_pdk_equivalent']:.3f} | "
                f"{row['opportunity_cost_net_expected_pdk']:.3f} | "
                f"{row['alternative_replacement_players'] or '—'} |"
            )
    lines.extend([
        "",
        "## Limitations",
        "",
        "- Costs are model-based, conditional on this prediction run and candidate market.",
        "- A zero or small gap means the optimizer can replace the player with little modeled loss; it does not prove the replacement is better in reality.",
        "- Solver timeouts are marked inconclusive, not interpreted as an opportunity-cost estimate.",
        "- No historical outcomes or frozen 2026/27 GW1 results were used.",
        "",
        "## Artifacts",
        "",
        f"- CSV: {csv_path.relative_to(ROOT)}",
        f"- JSON: {json_path.relative_to(ROOT)}",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "status": "completed",
        "run_id": run_id,
        "reference_coach": reference.coach,
        "counterfactuals": len(records),
        "optimal_counterfactuals": len(valid),
        "median_objective_gap": (
            float(valid["opportunity_cost_objective_pdk_equivalent"].median())
            if not valid.empty else None
        ),
        "outputs": [str(path.relative_to(ROOT)) for path in (csv_path, json_path, md_path)],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
