#!/usr/bin/env python3
"""Chronological evaluation of the production ensemble under single/multi-season training.

Uses certified official Dunkest PDK labels and the exact production feature adapter.
2025/26 is excluded from all validation folds because it has been inspected by prior
experiments; 2026/27 GW1 artifacts are never read or modified.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
STEM = "dunkest_multiseason_production_ensemble_walk_forward_20261014_v1"
OUT = ROOT / "reports/audit" / STEM
SEASONS = ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]


def score(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    err = p - y
    return {"n": int(len(y)), "mae": float(mean_absolute_error(y, p)),
            "rmse": float(np.sqrt(mean_squared_error(y, p))), "bias_pred_minus_actual": float(err.mean())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-stem",
        default=STEM,
        help="Versioned output stem under reports/audit (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    if Path(args.output_stem).name != args.output_stem or not args.output_stem.startswith("dunkest_"):
        raise SystemExit("--output-stem must be a simple filename beginning with 'dunkest_'.")
    output = ROOT / "reports/audit" / args.output_stem

    from dunkest.config import Settings
    from dunkest.models.multiseason_training import adapt_certified_training_rows
    from dunkest.models.predictor import train_models, _ensemble_predict

    files = [output.with_suffix(".json"), output.with_suffix(".md"), output.with_name(output.name + "_metrics.csv"), output.with_name(output.name + "_predictions.csv")]
    if any(p.exists() for p in files):
        raise SystemExit(f"Refusing to overwrite existing versioned outputs for {STEM}")
    data = adapt_certified_training_rows(pd.read_parquet(DATA), include_2025_26=False)
    settings = Settings(training_target="target_pdk_official")
    metric_rows, prediction_frames = [], []
    for i, season in enumerate(SEASONS[2:], start=2):
        test = data.loc[data.season_label.eq(season)].copy()
        previous_season = SEASONS[i - 1]
        arms = [
            ("previous_season_only", data.loc[data.season_label.eq(previous_season)].copy(), False),
            ("all_prior_seasons", data.loc[data.season_label.isin(SEASONS[:i])].copy(), False),
            ("all_prior_seasons_low_history_weighted", data.loc[data.season_label.isin(SEASONS[:i])].copy(), True),
        ]
        for method, train, weighted in arms:
            if train.empty or test.empty or pd.to_datetime(train.GAME_DATE).max() >= pd.to_datetime(test.GAME_DATE).min():
                raise ValueError(f"Empty or temporally overlapping fold: {season}/{method}")
            weights = train["_training_sample_weight"] if weighted else None
            models, _ = train_models(settings, train, target_column="target_pdk_official", sample_weight=weights)
            pred = _ensemble_predict(models, test)
            y = test["target_pdk_official"].to_numpy(float)
            if len(pred) != len(y) or not np.isfinite(pred).all():
                raise ValueError(f"Non-finite/misaligned predictions in {season}/{method}")
            row = {"test_season": season, "method": method, "train_rows": len(train),
                   "train_seasons": ";".join(sorted(train.season_label.unique())),
                   "models": ";".join(k for k in models if not k.startswith("_")),
                   "ensemble_weights": json.dumps(models.get("_weights", {}), sort_keys=True),
                   **score(y, pred)}
            metric_rows.append(row)
            frame = pd.DataFrame({
                "test_season": season, "method": method,
                "game_date": pd.to_datetime(test.GAME_DATE).astype(str).to_numpy(),
                "player_id": test.PLAYER_ID.astype(str).to_numpy(),
                "game_id": test.GAME_ID.astype(str).to_numpy(),
                "actual_pdk": y, "predicted_pdk": pred,
                "history_games": pd.to_numeric(test.history_games_before_target, errors="coerce").to_numpy(),
            })
            frame["error"] = frame.predicted_pdk - frame.actual_pdk
            frame["abs_error"] = frame.error.abs()
            frame["actual_ge_25"] = frame.actual_pdk.ge(25)
            frame["actual_ge_30"] = frame.actual_pdk.ge(30)
            frame["low_history_le_5"] = frame.history_games.le(5)
            prediction_frames.append(frame)
            print(f"{season} {method}: MAE={row['mae']:.4f} RMSE={row['rmse']:.4f} bias={row['bias_pred_minus_actual']:.4f}", flush=True)
    metrics = pd.DataFrame(metric_rows)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    cohort_rows = []
    for (season, method), group in predictions.groupby(["test_season", "method"]):
        for cohort, mask in [
            ("all", pd.Series(True, index=group.index)),
            ("actual_ge_25", group.actual_ge_25),
            ("actual_ge_30", group.actual_ge_30),
            ("low_history_le_5", group.low_history_le_5),
            ("history_gt_5", ~group.low_history_le_5),
        ]:
            part = group.loc[mask]
            if len(part): cohort_rows.append({"test_season": season, "method": method, "cohort": cohort, **score(part.actual_pdk, part.predicted_pdk)})
    cohorts = pd.DataFrame(cohort_rows)
    metrics.to_csv(files[2], index=False)
    predictions.to_csv(files[3], index=False)
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data": str(DATA.relative_to(ROOT)), "training_label": "certified official Dunkest PDK",
        "test_folds": sorted(metrics.test_season.unique()),
        "methods": ["previous_season_only", "all_prior_seasons", "all_prior_seasons_low_history_weighted"],
        "metric_rows": metrics.to_dict(orient="records"), "cohort_metrics": cohort_rows,
        "holdout_policy": "2025/26 excluded; already inspected in prior project experiments; 2026/27 GW1 untouched",
        "promotion_policy": "No production changes. Require stable improvements across folds, score cohorts and uncertainty calibration; lineup promotion additionally requires certified pre-lock archives and full realized scoring.",
        "production_changed": False,
        "artifacts": {"metrics": str(files[2].relative_to(ROOT)), "predictions": str(files[3].relative_to(ROOT))},
    }
    files[0].write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = ["# Production ensemble: single-season vs multi-season walk-forward", "",
             f"Generated UTC: {result['created_at_utc']}", "",
             "This experiment runs the actual production ensemble and feature adapter on official Dunkest PDK labels. It does not modify production weights or configuration.", "",
             "## Overall metrics", "",
             "| Test season | Method | Train rows | MAE | RMSE | Bias | Ensemble weights |", "|---|---|---:|---:|---:|---:|---|"]
    for r in metric_rows:
        lines.append(f"| {r['test_season']} | {r['method']} | {r['train_rows']} | {r['mae']:.4f} | {r['rmse']:.4f} | {r['bias_pred_minus_actual']:.4f} | `{r['ensemble_weights']}` |")
    lines += ["", "## Cohort metrics", "", "| Test season | Method | Cohort | N | MAE | RMSE | Bias |", "|---|---|---|---:|---:|---:|---:|"]
    for r in cohort_rows:
        lines.append(f"| {r['test_season']} | {r['method']} | {r['cohort']} | {r['n']} | {r['mae']:.4f} | {r['rmse']:.4f} | {r['bias_pred_minus_actual']:.4f} |")
    lines += ["", "## Limitations and decision", "",
              "- 2025/26 is excluded because it has already been inspected by prior experiments; these folds are validation evidence, not a pristine final holdout.",
              "- This tests player-game forecasts, not full lineup strategy performance.",
              "- Low-history means at most five prior Dunkest rows, not a verified draft-rookie label.",
              "- No production model/configuration or frozen 2026/27 GW1 artifact was modified.",
              "- Promotion requires stable gains across folds and cohorts plus independent lineup-level evidence.", "",
              "## Artifacts", "", f"- Metrics: `{files[2].relative_to(ROOT)}`", f"- Predictions: `{files[3].relative_to(ROOT)}`", ""]
    files[1].write_text("\n".join(lines), encoding="utf-8")
    print("\nMETRICS\n" + metrics.to_string(index=False), flush=True)
    print("\nREPORT " + str(files[1]), flush=True)

if __name__ == "__main__":
    main()
