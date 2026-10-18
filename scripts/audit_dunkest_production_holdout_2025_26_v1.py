#!/usr/bin/env python3
"""One-shot audit of the exact production PDK trainer on the 2025/26 official-label block.

This season has been inspected by prior experiments, so this is a retrospective
robustness audit, not a pristine final holdout and not a tuning/selection step.
It never reads the 2026/27 prospective bundle and never changes production code.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from dunkest.config import Settings
from dunkest.models.multiseason_training import DEFAULT_DATASET, TRAIN_SEASONS, adapt_certified_training_rows
from dunkest.models.predictor import _ensemble_predict, train_models

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/audit"
STEM = "dunkest_production_holdout_2025_26_v1"
N_BOOTSTRAP = 5000
SEED = 20261018


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    e = p - y
    result = {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "bias_pred_minus_actual": float(e.mean()),
    }
    for threshold in (25, 30):
        mask = y >= threshold
        result[f"n_actual_ge_{threshold}"] = int(mask.sum())
        result[f"mae_actual_ge_{threshold}"] = float(np.mean(np.abs(e[mask]))) if mask.any() else float("nan")
        result[f"bias_actual_ge_{threshold}"] = float(e[mask].mean()) if mask.any() else float("nan")
    return result


def clustered_delta_ci(frame: pd.DataFrame, candidate: str, baseline: str) -> dict:
    """Bootstrap paired absolute-error delta by NBA date clusters."""
    data = frame[["GAME_DATE", "target_pdk_official", candidate, baseline]].copy()
    data["delta_abs"] = (
        np.abs(data[candidate].to_numpy(float) - data.target_pdk_official.to_numpy(float))
        - np.abs(data[baseline].to_numpy(float) - data.target_pdk_official.to_numpy(float))
    )
    clusters = data.groupby("GAME_DATE", sort=False).delta_abs.agg(["sum", "count"])
    sums, counts = clusters["sum"].to_numpy(float), clusters["count"].to_numpy(float)
    if len(sums) < 20:
        raise ValueError(f"Too few game-date clusters for bootstrap: {len(sums)}")
    rng = np.random.default_rng(SEED)
    draws = np.empty(N_BOOTSTRAP, dtype=float)
    for i in range(N_BOOTSTRAP):
        ix = rng.integers(0, len(sums), size=len(sums))
        draws[i] = sums[ix].sum() / counts[ix].sum()
    return {
        "delta_mae_candidate_minus_baseline": float(data.delta_abs.mean()),
        "ci95_low": float(np.quantile(draws, 0.025)),
        "ci95_high": float(np.quantile(draws, 0.975)),
        "date_clusters": int(len(clusters)),
        "bootstrap_replicates": N_BOOTSTRAP,
        "interpretation": "negative favors candidate",
    }


def main() -> None:
    paths = [OUT / f"{STEM}.json", OUT / f"{STEM}.md", OUT / f"{STEM}_metrics.csv", OUT / f"{STEM}_predictions.csv", OUT / f"{STEM}_cohorts.csv"]
    if any(path.exists() for path in paths):
        raise SystemExit(f"Refusing to overwrite versioned audit outputs: {STEM}")

    settings = Settings(training_target="target_pdk_official")
    source_path = settings.data_path / DEFAULT_DATASET
    source = pd.read_parquet(source_path)
    rows = adapt_certified_training_rows(source, include_2025_26=True)
    train = rows.loc[rows.season_label.astype(str).isin(TRAIN_SEASONS)].copy()
    test = rows.loc[rows.season_label.astype(str).eq("2025-26")].copy()
    if train.empty or len(test) < 10_000:
        raise ValueError(f"Unexpected train/test size: train={len(train)}, test={len(test)}")
    train_max = pd.to_datetime(train.GAME_DATE).max()
    test_min = pd.to_datetime(test.GAME_DATE).min()
    if train_max >= test_min:
        raise ValueError(f"Temporal overlap: train max={train_max}, test min={test_min}")
    if test.duplicated(["PLAYER_ID", "GAME_DATE"]).any():
        raise ValueError("Duplicate player/date keys in holdout")

    models, _ = train_models(
        settings,
        train,
        target_column="target_pdk_official",
        sample_weight=train["_training_sample_weight"],
    )
    prediction = np.asarray(_ensemble_predict(models, test), dtype=float)
    if len(prediction) != len(test) or not np.isfinite(prediction).all():
        raise ValueError("Production trainer returned missing/non-finite/misaligned holdout predictions")

    frame = test[["season_label", "GAME_DATE", "GAME_ID", "PLAYER_ID", "PLAYER_NAME", "target_pdk_official", "pdk_mean_10", "history_games_before_target", "nba_history_games_before_target"]].copy()
    frame["prediction_production_ensemble"] = prediction
    training_median = float(pd.to_numeric(train.target_pdk_official, errors="coerce").median())
    frame["baseline_prev10"] = pd.to_numeric(frame.pdk_mean_10, errors="coerce").fillna(training_median)
    frame["prediction_error"] = frame.prediction_production_ensemble - frame.target_pdk_official
    frame["baseline_error"] = frame.baseline_prev10 - frame.target_pdk_official
    frame["abs_error"] = frame.prediction_error.abs()
    frame["actual_ge_25"] = frame.target_pdk_official.ge(25)
    frame["actual_ge_30"] = frame.target_pdk_official.ge(30)
    frame["low_history_le_5"] = pd.to_numeric(frame.history_games_before_target, errors="coerce").fillna(0).le(5)
    frame["prediction_ge_25"] = frame.prediction_production_ensemble.ge(25)
    frame["prediction_ge_30"] = frame.prediction_production_ensemble.ge(30)

    overall = {
        "production_ensemble": metrics(frame.target_pdk_official.to_numpy(float), frame.prediction_production_ensemble.to_numpy(float)),
        "previous10_baseline": metrics(frame.target_pdk_official.to_numpy(float), frame.baseline_prev10.to_numpy(float)),
    }
    ci = clustered_delta_ci(frame, "prediction_production_ensemble", "baseline_prev10")
    cohort_rows = []
    cohort_specs = {
        "all": pd.Series(True, index=frame.index),
        "actual_ge_25": frame.actual_ge_25,
        "actual_ge_30": frame.actual_ge_30,
        "low_history_le_5": frame.low_history_le_5,
        "history_gt_5": ~frame.low_history_le_5,
        "prediction_ge_25": frame.prediction_ge_25,
        "prediction_ge_30": frame.prediction_ge_30,
    }
    for name, mask in cohort_specs.items():
        part = frame.loc[mask]
        if part.empty:
            continue
        for method, col in [("production_ensemble", "prediction_production_ensemble"), ("previous10_baseline", "baseline_prev10")]:
            cohort_rows.append({"cohort": name, "method": method, **metrics(part.target_pdk_official.to_numpy(float), part[col].to_numpy(float))})
    cohorts = pd.DataFrame(cohort_rows)
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset": str(source_path.relative_to(ROOT)),
        "label": "official Dunkest PDK labels; 2025/26 matched subset",
        "train_seasons": list(TRAIN_SEASONS),
        "train_rows": int(len(train)),
        "test_season": "2025-26",
        "test_rows": int(len(test)),
        "test_first_date": str(test_min),
        "train_last_date": str(train_max),
        "feature_count": len(models.get("_feature_cols", [])),
        "feature_cols": models.get("_feature_cols", []),
        "ensemble_weights": models.get("_weights", {}),
        "ridge_alpha": getattr(models.get("ridge"), "alpha", None),
        "overall_metrics": overall,
        "paired_date_cluster_bootstrap": ci,
        "holdout_status": "retrospective robustness audit only: 2025/26 has been inspected in prior experiments and is not a pristine final holdout",
        "selection_or_tuning_on_test": False,
        "prospective_2026_27_data_loaded": False,
        "production_changed": False,
        "lineup_performance_certified": False,
    }
    frame.to_csv(paths[3], index=False)
    cohorts.to_csv(paths[4], index=False)
    pd.DataFrame([{"method": method, **vals} for method, vals in overall.items()]).to_csv(paths[2], index=False)
    paths[0].write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [
        "# Production PDK trainer — 2025/26 retrospective holdout audit", "",
        f"Generated UTC: {summary['created_utc']}", "",
        "## Scope and leakage controls", "",
        f"- Train: official PDK rows from {', '.join(TRAIN_SEASONS)} ({len(train):,} rows).",
        f"- Test: {len(test):,} matched official-label player-games from 2025/26.",
        f"- Chronology: last training date {train_max.date()}, first test date {test_min.date()}.",
        "- Exact production `train_models` and certified multi-season feature adapter; no hyperparameter or blend selection on 2025/26.",
        "- This season was inspected by earlier experiments; treat this as robustness evidence, not a pristine holdout.",
        "- No 2026/27 prospective inputs loaded; no production code/config changed.", "",
        "## Overall results", "",
        "| Method | N | MAE | RMSE | Bias pred−actual | MAE actual ≥25 | MAE actual ≥30 |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method, m in overall.items():
        lines.append(f"| {method} | {m['n']:,} | {m['mae']:.4f} | {m['rmse']:.4f} | {m['bias_pred_minus_actual']:.4f} | {m['mae_actual_ge_25']:.4f} | {m['mae_actual_ge_30']:.4f} |")
    lines += ["", "## Paired date-cluster uncertainty", "", f"Delta MAE (production minus prev10): {ci['delta_mae_candidate_minus_baseline']:.5f}; 95% CI [{ci['ci95_low']:.5f}, {ci['ci95_high']:.5f}] over {ci['date_clusters']} game dates. Negative favors production.", "", "## Cohort results", "", cohorts.to_string(index=False, float_format=lambda x: f"{x:.4f}"), "", "## Decision", "", "This audit checks whether the current production trainer generalizes to the 2025/26 official-label subset and where errors remain concentrated. It does not certify lineup quality because authentic pre-lock market/injury/coach snapshots are not complete for the historical season. Do not use this single season to tune or promote a challenger; use it to guide future diagnostics, then require repeated temporal folds and lineup-level evidence.", "", "## Artifacts", "", *[f"- `{p.relative_to(ROOT)}`" for p in paths], ""]
    paths[1].write_text("\n".join(lines), encoding="utf-8")
    print("OVERALL", json.dumps(overall, indent=2), flush=True)
    print("PAIRED_BOOTSTRAP", json.dumps(ci, indent=2), flush=True)
    print("COHORTS\n" + cohorts.to_string(index=False), flush=True)
    print("REPORT=" + str(paths[1].relative_to(ROOT)), flush=True)


if __name__ == "__main__":
    main()
