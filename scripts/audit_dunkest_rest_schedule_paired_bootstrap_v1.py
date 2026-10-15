#!/usr/bin/env python3
"""Paired season-stratified cluster bootstrap for V6 rest/schedule ablation."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/audit"
STEM = "dunkest_rest_schedule_paired_bootstrap_20261013_v1"
CSV, JSON, MD = (OUT / f"{STEM}.{ext}" for ext in ("csv", "json", "md"))
PRED = OUT / "dunkest_lagged_credit_matchup_walk_forward_20261013_v6_rest_schedule_predictions.csv"
BASE = "historical_form_plus_lagged_credit_and_expanded_matchup_v2"
CHALLENGER = "historical_form_plus_lagged_credit_expanded_matchup_rest_schedule_v6"
for path in (CSV, JSON, MD):
    if path.exists():
        raise SystemExit(f"Refusing to overwrite versioned artifact: {path}")
df = pd.read_csv(PRED)
df = df[df.feature_family.isin([BASE, CHALLENGER])].copy()
df["abs_error"] = (pd.to_numeric(df.predicted_pdk_round_total) - pd.to_numeric(df.actual_pdk_round_total)).abs()
df["sq_error"] = (pd.to_numeric(df.predicted_pdk_round_total) - pd.to_numeric(df.actual_pdk_round_total)) ** 2
keys = ["season_id", "source_week", "source_round", "player_name"]
wide = None
for family, label in ((BASE, "base"), (CHALLENGER, "rest")):
    x = df[df.feature_family.eq(family)].copy()
    x = x.rename(columns={"abs_error": f"abs_{label}", "sq_error": f"sq_{label}",
                          "predicted_pdk_round_total": f"pred_{label}",
                          "actual_pdk_round_total": f"actual_{label}"})
    keep = keys + [f"actual_{label}", f"pred_{label}", f"abs_{label}", f"sq_{label}"]
    x = x[keep]
    wide = x if wide is None else wide.merge(x.drop(columns=[f"actual_{label}"]), on=keys, how="inner", validate="one_to_one")
if len(wide) < 50000:
    raise RuntimeError(f"Unexpected paired sample size: {len(wide)}")
wide["round_cluster"] = wide.season_id.astype(str) + "|" + wide.source_week.astype(str) + "|" + wide.source_round.astype(str)
wide["season_id"] = wide.season_id.astype(str)
wide["delta_abs_rest_minus_base"] = wide.abs_rest - wide.abs_base
wide["delta_sq_rest_minus_base"] = wide.sq_rest - wide.sq_base
B = 10000
rng = np.random.default_rng(20261013)
rows, season_boot = [], {}
for season in sorted(wide.season_id.unique()):
    sub = wide[wide.season_id.eq(season)].copy()
    clusters = sub.round_cluster.unique()
    rows.append({
        "scope": season, "n_player_rounds": len(sub), "n_rounds": len(clusters),
        "mae_base": float(sub.abs_base.mean()), "mae_rest": float(sub.abs_rest.mean()),
        "delta_mae_rest_minus_base": float(sub.delta_abs_rest_minus_base.mean()),
        "rmse_base": float(np.sqrt(sub.sq_base.mean())), "rmse_rest": float(np.sqrt(sub.sq_rest.mean())),
        "round_win_rate_rest_better": float(sub.groupby("round_cluster").apply(lambda g: g.abs_rest.mean() < g.abs_base.mean(), include_groups=False).mean()),
    })
    groups = [np.flatnonzero(sub.round_cluster.to_numpy() == c) for c in clusters]
    diffs = np.empty(B)
    errors = sub.delta_abs_rest_minus_base.to_numpy()
    for b in range(B):
        chosen = rng.integers(0, len(groups), size=len(groups))
        idx = np.concatenate([groups[i] for i in chosen])
        diffs[b] = errors[idx].mean()
    season_boot[season] = diffs
pooled = np.mean(np.vstack([season_boot[s] for s in sorted(season_boot)]), axis=0)
macro_delta = float(np.mean([wide.loc[wide.season_id.eq(s), "delta_abs_rest_minus_base"].mean() for s in sorted(season_boot)]))
pooled_rows = {
    "scope": "pooled_macro_season_bootstrap", "n_player_rounds": len(wide),
    "n_rounds": int(wide.round_cluster.nunique()),
    "mae_base": float(wide.groupby("season_id").abs_base.mean().mean()),
    "mae_rest": float(wide.groupby("season_id").abs_rest.mean().mean()),
    "delta_mae_rest_minus_base": macro_delta,
    "rmse_base": float(np.mean([np.sqrt(wide.loc[wide.season_id.eq(s), "sq_base"].mean()) for s in sorted(season_boot)])),
    "rmse_rest": float(np.mean([np.sqrt(wide.loc[wide.season_id.eq(s), "sq_rest"].mean()) for s in sorted(season_boot)])),
    "round_win_rate_rest_better": float(np.mean([wide[wide.season_id.eq(s)].groupby("round_cluster").apply(lambda g: g.abs_rest.mean() < g.abs_base.mean(), include_groups=False).mean() for s in sorted(season_boot)])),
}
rows.append(pooled_rows)
metrics = pd.DataFrame(rows)
metrics.to_csv(CSV, index=False)
detail = {
    "macro_season_delta_mae_ci95": [float(np.quantile(pooled, .025)), float(np.quantile(pooled, .975))],
    "bootstrap_fraction_delta_below_zero": float(np.mean(pooled < 0)),
    "per_season": {s: {"ci95": [float(np.quantile(v, .025)), float(np.quantile(v, .975))],
                       "fraction_below_zero": float(np.mean(v < 0))} for s, v in season_boot.items()},
}
audit = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(), "paired_rows": len(wide),
    "round_clusters": int(wide.round_cluster.nunique()), "test_seasons": sorted(wide.season_id.unique()),
    "bootstrap_replicates": B, "bootstrap_unit": "Dunkest season-week-round cluster, stratified by held-out season",
    "comparison": f"{CHALLENGER} minus {BASE}", "bootstrap": detail,
    "production_changed": False,
    "interpretation": "Negative delta MAE favors rest/schedule features. This is player-level evidence only and does not establish an improvement to the lineup optimizer.",
}
JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
lines = [
    "# Rest/schedule features — paired cluster bootstrap", "",
    f"Generated UTC: {audit['generated_at_utc']}", "",
    f"Paired sample: {len(wide):,} player-round rows, {wide.round_cluster.nunique():,} season-week-round clusters.", "",
    "## Metrics", "", metrics.to_string(index=False), "",
    "## Paired bootstrap (10,000 replicates)", "",
    f"- Macro-season delta MAE (rest minus baseline), 95% CI: [{detail['macro_season_delta_mae_ci95'][0]:.4f}, {detail['macro_season_delta_mae_ci95'][1]:.4f}].",
    f"- Bootstrap fraction with delta below zero: {detail['bootstrap_fraction_delta_below_zero']:.4f}.",
    "- Per-season intervals:",
]
for season, item in detail["per_season"].items():
    lines.append(f"  - {season}: [{item['ci95'][0]:.4f}, {item['ci95'][1]:.4f}], fraction below zero {item['fraction_below_zero']:.4f}.")
lines += ["", "## Decision", "", "Do not promote features based on tiny or unstable player-level gains. Any candidate must subsequently improve a complete, leakage-safe lineup backtest; this experiment does not change production.", ""]
MD.write_text("\n".join(lines), encoding="utf-8")
print(json.dumps({"status": "completed", "metrics": metrics.to_dict("records"), "bootstrap": detail,
                  "artifacts": [str(p.relative_to(ROOT)) for p in (CSV, JSON, MD)]}, indent=2))
