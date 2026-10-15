#!/usr/bin/env python3
"""Paired season-stratified bootstrap for V2 vs V6 historical lineup comparison."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/audit"
STEM = "dunkest_historical_lineups_rest_schedule_paired_bootstrap_20261013_v1"
SOURCE = OUT / "dunkest_historical_lineups_rest_schedule_20261013_v1_rounds.csv"
CSV, JSON, MD = (OUT / f"{STEM}.{ext}" for ext in ("csv", "json", "md"))
for path in (CSV, JSON, MD):
    if path.exists():
        raise SystemExit(f"Refusing to overwrite versioned artifact: {path}")
df = pd.read_csv(SOURCE)
df = df.loc[df.status.eq("evaluated")].copy()
if df.empty:
    raise RuntimeError("No evaluated paired rounds in lineup backtest.")
df["v6_minus_v2"] = pd.to_numeric(df["v6_minus_v2"], errors="coerce")
df = df[np.isfinite(df["v6_minus_v2"])].copy()
df["season_id"] = df.season_id.astype(str)
df["round_cluster"] = df.season_id + "|" + df.round_index.astype(str)
B = 10000
rng = np.random.default_rng(20261013)
metrics, boot = [], {}
for season in sorted(df.season_id.unique()):
    sub = df[df.season_id.eq(season)].copy()
    clusters = sub.round_cluster.unique()
    vals = sub.set_index("round_cluster")["v6_minus_v2"].to_dict()
    x = np.array([vals[c] for c in clusters], dtype=float)
    reps = np.empty(B)
    for b in range(B):
        reps[b] = x[rng.integers(0, len(x), size=len(x))].mean()
    boot[season] = reps
    metrics.append({
        "scope": season, "n_rounds": len(sub),
        "mean_v2_realized_team_score": float(sub.v2_realized_team_score.mean()),
        "mean_v6_realized_team_score": float(sub.v6_realized_team_score.mean()),
        "delta_v6_minus_v2": float(sub.v6_minus_v2.mean()),
        "median_delta_v6_minus_v2": float(sub.v6_minus_v2.median()),
        "v6_win_rate": float((sub.v6_minus_v2 > 0).mean()),
        "ci95_low": float(np.quantile(reps, .025)), "ci95_high": float(np.quantile(reps, .975)),
        "bootstrap_fraction_delta_positive": float(np.mean(reps > 0)),
    })
# Macro-average by season, preserving each season as an equal stratum.
seasons = sorted(boot)
macro = np.mean(np.vstack([boot[s] for s in seasons]), axis=0)
delta = float(np.mean([df.loc[df.season_id.eq(s), "v6_minus_v2"].mean() for s in seasons]))
pooled = {
    "scope": "macro_season", "n_rounds": len(df),
    "mean_v2_realized_team_score": float(np.mean([df.loc[df.season_id.eq(s), "v2_realized_team_score"].mean() for s in seasons])),
    "mean_v6_realized_team_score": float(np.mean([df.loc[df.season_id.eq(s), "v6_realized_team_score"].mean() for s in seasons])),
    "delta_v6_minus_v2": delta,
    "median_delta_v6_minus_v2": float(df.v6_minus_v2.median()),
    "v6_win_rate": float(np.mean([float((df.loc[df.season_id.eq(s), "v6_minus_v2"] > 0).mean()) for s in seasons])),
    "ci95_low": float(np.quantile(macro, .025)), "ci95_high": float(np.quantile(macro, .975)),
    "bootstrap_fraction_delta_positive": float(np.mean(macro > 0)),
}
metrics.append(pooled)
m = pd.DataFrame(metrics)
m.to_csv(CSV, index=False)
audit = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "source": str(SOURCE.relative_to(ROOT)), "evaluated_rounds": len(df),
    "seasons": seasons, "bootstrap_replicates": B,
    "resampling_unit": "whole evaluated Dunkest round, stratified by held-out season",
    "delta_definition": "V6 realized team score minus V2 realized team score; positive favors V6",
    "macro_season_ci95": [pooled["ci95_low"], pooled["ci95_high"]],
    "macro_season_bootstrap_fraction_positive": pooled["bootstrap_fraction_delta_positive"],
    "metrics": m.to_dict("records"),
    "limitations": [
        "This is a restricted candidate-pool lineup proxy, not a complete pre-lock market backtest.",
        "Historical coach prices/credit multipliers and transfer carry-over/malus are unavailable; coach CR is fixed at 10 and transfer malus is zero.",
        "Lineup outcomes depend on archived candidate coverage and the configured MILP time limit."
    ],
    "production_changed": False,
}
JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
lines = [
    "# Paired lineup bootstrap — expanded matchup V2 vs rest/schedule V6", "",
    f"Generated UTC: {audit['generated_at_utc']}", "",
    f"Evaluated paired rounds: {len(df):,}; held-out seasons: {', '.join(seasons)}.", "",
    "## Results", "", m.to_string(index=False), "",
    "## Interpretation", "",
    f"Macro-season delta (V6 − V2): {delta:.3f} realized team points per round; 95% cluster-bootstrap interval [{pooled['ci95_low']:.3f}, {pooled['ci95_high']:.3f}].",
    f"Fraction of bootstrap replicates above zero: {pooled['bootstrap_fraction_delta_positive']:.4f}.",
    "",
    "This comparison is paired on the same rounds and candidate pool. It is still a restricted historical proxy: coach prices and transfer malus are not historically validated, and the archived player universe is incomplete. Do not promote V6 to production solely from this result.", ""
]
MD.write_text("\n".join(lines), encoding="utf-8")
print(json.dumps({"status":"completed","metrics":m.to_dict("records"),"artifacts":[str(p.relative_to(ROOT)) for p in (CSV,JSON,MD)]},indent=2,default=str))
