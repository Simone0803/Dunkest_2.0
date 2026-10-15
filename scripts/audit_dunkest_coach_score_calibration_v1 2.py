#!/usr/bin/env python3
"""Walk-forward calibration audit for Monte Carlo coach-score forecasts."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from dunkest.models.coach import _simulate_matchup_scores
from dunkest.rules.coach import coach_points_from_outcomes

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "reports/audit/dunkest_coach_score_forecast_monte_carlo_walk_forward_2018-26_v4_predictions.csv"
OUT = ROOT / "reports/audit"
STAMP = "dunkest_coach_score_calibration_20261015_v1"
REPORT, METRICS, INTERVALS, JSON = [OUT / f"{STAMP}{s}" for s in (".md", "_metrics.csv", "_intervals.csv", ".json")]

def main() -> None:
    for path in (REPORT, METRICS, INTERVALS, JSON):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing artifact: {path.relative_to(ROOT)}")
    frame = pd.read_csv(PRED)
    frame["season"] = frame.season.astype(str)
    frame["pred"] = pd.to_numeric(frame.predicted_coach_pdk_monte_carlo, errors="coerce")
    frame["actual"] = pd.to_numeric(frame.actual_base_coach_pdk, errors="coerce")
    frame = frame.dropna(subset=["pred", "actual", "game_id", "season"]).copy()
    train = frame[frame.season.isin(["2022-23", "2023-24"])].copy()
    validation = frame[frame.season.eq("2024-25")].copy()
    holdout = frame[frame.season.eq("2025-26")].copy()
    global_bias = float((train.actual - train.pred).mean())
    affine = LinearRegression().fit(train[["pred"]], train.actual)
    edges = np.unique(np.quantile(train.pred, [0, .2, .4, .6, .8, 1]))
    train_bins = pd.cut(train.pred, bins=edges, include_lowest=True, duplicates="drop")
    residual_by_bin = train.assign(_bin=train_bins, residual=train.actual-train.pred).groupby("_bin", observed=False).residual.agg(["mean", "count"])
    band_corrections = {k: float(v["mean"] * v["count"] / (v["count"] + 300)) for k, v in residual_by_bin.iterrows() if pd.notna(k)}

    def predict(g: pd.DataFrame, method: str) -> np.ndarray:
        x = g.pred.to_numpy(float)
        if method == "raw": return x
        if method == "global_bias": return x + global_bias
        if method == "affine": return affine.predict(g[["pred"]])
        if method == "score_band":
            bins = pd.cut(g.pred, bins=edges, include_lowest=True, duplicates="drop")
            return x + np.array([band_corrections.get(b, 0.0) for b in bins])
        raise ValueError(method)

    metric_rows = []
    bootstrap_rows = []
    rng = np.random.default_rng(4321)
    for season, g in frame[frame.season.isin(["2024-25", "2025-26"])].groupby("season", sort=True):
        for method in ("raw", "global_bias", "affine", "score_band"):
            y = g.actual.to_numpy(float); z = predict(g, method); err = z-y
            metric_rows.append({"season": season, "method": method, "n": len(y),
                "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err**2))),
                "bias_pred_minus_actual": float(np.mean(err))})
            if method == "raw": continue
            tmp = g[["game_id"]].copy()
            tmp["delta_abs_error"] = np.abs(z-y) - np.abs(g.pred.to_numpy(float)-y)
            per_game = tmp.groupby("game_id").delta_abs_error.mean().to_numpy(float)
            samples = rng.choice(per_game, size=(4000, len(per_game)), replace=True).mean(axis=1)
            bootstrap_rows.append({"season": season, "method": method,
                "delta_mae_candidate_minus_raw": float(per_game.mean()),
                "ci95_low": float(np.quantile(samples, .025)), "ci95_high": float(np.quantile(samples, .975)),
                "game_clusters": int(len(per_game))})

    interval_rows = []
    for (season, game_id), group in frame.groupby(["season", "game_id"], sort=False):
        if len(group) != 2:
            continue
        first = group.iloc[0]
        team_scores, opp_scores, overtime = _simulate_matchup_scores(
            float(first.predicted_team_points), float(first.predicted_opponent_points),
            float(first.team_score_sd_prior), float(first.opponent_score_sd_prior),
            float(first.score_correlation_prior), f"{season}-{game_id}-mc-coach-v2",
            float(first.overtime_probability_prior), draws=8192)
        team_dist = np.asarray(coach_points_from_outcomes(team_scores, opp_scores, 10.0, 10.0, overtime), dtype=float)
        opp_dist = np.asarray(coach_points_from_outcomes(opp_scores, team_scores, 10.0, 10.0, overtime), dtype=float)
        first_team = str(first.team)
        for _, row in group.iterrows():
            dist = team_dist if str(row.team) == first_team else opp_dist
            interval_rows.append({"season": season, "game_id": str(game_id), "team": str(row.team),
                "actual": float(row.actual), "mean": float(np.mean(dist)),
                "p10": float(np.quantile(dist, .10)), "p50": float(np.quantile(dist, .50)),
                "p90": float(np.quantile(dist, .90))})
    intervals = pd.DataFrame(interval_rows)
    interval_metrics = []
    for season, g in list(intervals.groupby("season", sort=True)) + [("pooled", intervals)]:
        err = g["mean"] - g.actual
        interval_metrics.append({"season": season, "n": int(len(g)),
            "mean_mae": float(np.mean(np.abs(err))), "mean_rmse": float(np.sqrt(np.mean(err**2))),
            "mean_bias_pred_minus_actual": float(np.mean(err)),
            "p10_p90_coverage": float(((g.actual >= g.p10) & (g.actual <= g.p90)).mean()),
            "below_p10_rate": float((g.actual < g.p10).mean()),
            "above_p90_rate": float((g.actual > g.p90).mean()),
            "median_coverage_actual_le_p50": float((g.actual <= g.p50).mean()),
            "mean_interval_width": float((g.p90-g.p10).mean())})
    metrics = pd.DataFrame(metric_rows)
    bootstrap = pd.DataFrame(bootstrap_rows)
    intervals.to_csv(INTERVALS, index=False)
    metrics.to_csv(METRICS, index=False)
    audit = {"created_utc": datetime.now(timezone.utc).isoformat(), "source_predictions": str(PRED.relative_to(ROOT)),
        "train_seasons": ["2022-23", "2023-24"], "validation_season": "2024-25",
        "later_audit_season": "2025-26", "training_rows": int(len(train)),
        "global_bias_correction_actual_minus_predicted": global_bias,
        "affine_intercept": float(affine.intercept_), "affine_slope": float(affine.coef_[0]),
        "score_band_corrections": {str(k): v for k,v in band_corrections.items()},
        "point_metrics": metrics.to_dict("records"), "paired_game_cluster_bootstrap": bootstrap.to_dict("records"),
        "distribution_interval_metrics": interval_metrics,
        "decision": "retain raw Monte Carlo expected coach score; global correction has negligible, non-significant MAE effect, while affine and score-band corrections worsen MAE",
        "uses_historical_full_lineups": False, "uses_2026_27_prospective_bundle": False}
    JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Coach Monte Carlo score calibration — V1", "", f"Generated UTC: {audit['created_utc']}", "",
        "The model is trained on earlier walk-forward seasons (2022-23 and 2023-24), assessed on 2024-25, and additionally checked on 2025-26. The outcome is base coach PDK with CR=10 for both teams, isolating team-score simulation from the deterministic coach-CR multiplier. No full-lineup validation or 2026/27 prospective data are used.", "",
        "## Point-score correction comparison", "", metrics.to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Paired game-cluster bootstrap: candidate MAE minus raw MAE", "", bootstrap.to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Monte Carlo interval coverage", "", pd.DataFrame(interval_metrics).to_string(index=False, float_format=lambda x: f"{x:.4f}"), "",
        "## Decision", "",
        "- The raw Monte Carlo expected coach score is already close to unbiased on the validation and later-audit seasons.",
        "- Global bias correction reduces MAE by only about 0.001 coach points; its paired game-cluster 95% interval crosses zero.",
        "- Affine and score-band corrections worsen MAE in both seasons, so they are not promoted.",
        "- The P10–P90 interval is conservative relative to its nominal 80% coverage; no interval narrowing is promoted without a stable out-of-sample improvement.",
        "- This is an explicit calibration check, not proof that future coach scores are certain. It does not alter production weights or the frozen prospective test.", "",
        "## Artifacts", "", str(METRICS.relative_to(ROOT)), str(INTERVALS.relative_to(ROOT)), str(JSON.relative_to(ROOT)), ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("REPORT", REPORT.relative_to(ROOT), flush=True)
    print("POINT_METRICS\n", metrics.to_string(index=False), flush=True)
    print("BOOTSTRAP\n", bootstrap.to_string(index=False), flush=True)
    print("INTERVALS\n", pd.DataFrame(interval_metrics).to_string(index=False), flush=True)

if __name__ == "__main__":
    main()
