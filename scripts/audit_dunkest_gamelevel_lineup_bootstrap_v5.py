#!/usr/bin/env python3
"""Season-stratified paired-round bootstrap for the explicit zero-for-missing historical lineup proxy."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "reports/audit/dunkest_historical_lineups_gamelevel_actuals_20261014_v5_rounds.csv"
STEM = "dunkest_historical_lineups_gamelevel_actuals_20261014_v5_proxy_bootstrap"
REPORT = ROOT / "reports/audit" / f"{STEM}.md"
OUTPUT = ROOT / "reports/audit" / f"{STEM}.json"

def main():
    if REPORT.exists() or OUTPUT.exists():
        raise SystemExit("Refusing to overwrite versioned bootstrap artifacts.")
    rounds = pd.read_csv(INPUT)
    rounds = rounds.loc[rounds["proxy_status"].eq("evaluated_proxy")].copy()
    rounds["delta"] = pd.to_numeric(rounds["proxy_model_minus_baseline"], errors="coerce")
    rounds = rounds.dropna(subset=["delta"])
    if rounds.empty:
        raise SystemExit("No evaluated paired rounds.")
    groups = [(str(season), g["delta"].to_numpy(float)) for season, g in rounds.groupby("season_id", sort=True)]
    total = sum(len(v) for _, v in groups)
    weights = np.array([len(v) / total for _, v in groups], dtype=float)
    rng = np.random.default_rng(42)
    n_boot = 50000
    boot = np.zeros(n_boot, dtype=float)
    season_summary = []
    for (season, values), weight in zip(groups, weights):
        idx = rng.integers(0, len(values), size=(n_boot, len(values)))
        boot += weight * values[idx].mean(axis=1)
        season_summary.append({
            "season_id": season,
            "rounds": int(len(values)),
            "mean_delta": float(values.mean()),
            "median_delta": float(np.median(values)),
            "win_rate": float(np.mean(values > 0)),
        })
    lo, hi = np.quantile(boot, [0.025, 0.975])
    delta = rounds["delta"].to_numpy(float)
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(INPUT.relative_to(ROOT)),
        "bootstrap_unit": "paired gameweek/round",
        "stratification": "resample rounds within each test season; preserve observed season sample sizes in pooled estimate",
        "seed": 42,
        "bootstrap_replicates": n_boot,
        "paired_rounds": int(len(rounds)),
        "mean_model_minus_baseline": float(delta.mean()),
        "median_model_minus_baseline": float(np.median(delta)),
        "model_win_rate": float(np.mean(delta > 0)),
        "stratified_round_bootstrap_95_ci": [float(lo), float(hi)],
        "bootstrap_replicates_with_nonpositive_mean_delta": int(np.sum(boot <= 0)),
        "by_season": season_summary,
        "limitations": [
            "This estimates uncertainty conditional on the reconstructed candidate pool and the explicit zero-for-missing player outcome proxy.",
            "It does not correct missing historical pre-lock prices/availability, unknown coach credits, or transfer malus.",
            "It compares fresh independent round lineups, not a sequential roster with carried players and transfer constraints."
        ],
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Game-level historical lineup proxy — paired bootstrap", "",
        f"Generated UTC: {result['generated_at_utc']}", "",
        "## Pooled comparison", "",
        f"- Paired rounds: {result['paired_rounds']}",
        f"- Mean model minus baseline: **{result['mean_model_minus_baseline']:.3f} PDK**",
        f"- Median paired difference: **{result['median_model_minus_baseline']:.3f} PDK**",
        f"- Model wins on **{result['model_win_rate']:.1%}** of rounds",
        f"- Season-stratified paired-round bootstrap 95% CI: **[{lo:.3f}, {hi:.3f}] PDK**",
        f"- Bootstrap replicates with non-positive mean difference: {result['bootstrap_replicates_with_nonpositive_mean_delta']} / {n_boot}",
        "", "| Season ID | Rounds | Mean delta | Median delta | Model win rate |", "|---:|---:|---:|---:|---:|"
    ]
    for row in season_summary:
        lines.append(f"| {row['season_id']} | {row['rounds']} | {row['mean_delta']:.3f} | {row['median_delta']:.3f} | {row['win_rate']:.1%} |")
    lines += ["", "## Interpretation", "",
        "This interval is conditional on the explicit assumption that a previously observed candidate with no valid player-game PDK row scores zero. It is exploratory, not a certified historical Dunkest result. The raw previous-five baseline is not post-selection calibrated; historical market state, availability, coach prices and transfer penalties remain unobserved.", "",
        "## Limitations", ""]
    lines.extend(f"- {x}" for x in result["limitations"])
    lines += ["", f"Machine-readable output: {OUTPUT.relative_to(ROOT)}", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "paired_rounds": len(rounds), "mean_delta": float(delta.mean()),
        "win_rate": float(np.mean(delta > 0)), "ci95": [float(lo), float(hi)],
        "outputs": [str(REPORT.relative_to(ROOT)), str(OUTPUT.relative_to(ROOT))]}, indent=2))

if __name__ == "__main__":
    main()
