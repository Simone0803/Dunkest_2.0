#!/usr/bin/env python3
"""Chronological audit of reconstructed Dunkest PDK versus official labels.

This is an evaluation-only script: it does not modify targets or production
projection weights. Fit uses earlier game dates only; final dates are held out.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/player_game_logs_2025-26_official_pdk_overlay_v4.parquet"
OUT = ROOT / "reports/audit/dunkest_pdk_proxy_calibration_20261015_v1.json"
BOOTSTRAPS = 1000
SEED = 20261015


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing official PDK overlay: {SOURCE}")
    frame = pd.read_parquet(SOURCE)
    required = {"GAME_DATE", "PDK", "PDK_OFFICIAL_VALID", "PLAYER_ID", "GAME_ID", "MIN"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"Overlay schema missing columns: {missing}")
    frame["date"] = pd.to_datetime(frame["GAME_DATE"], errors="coerce", utc=True)
    frame["proxy"] = pd.to_numeric(frame["PDK"], errors="coerce")
    frame["actual"] = pd.to_numeric(frame["PDK_OFFICIAL_VALID"], errors="coerce")
    frame["minutes"] = pd.to_numeric(frame["MIN"], errors="coerce")
    frame = frame.dropna(subset=["date", "proxy", "actual", "PLAYER_ID", "GAME_ID"])
    frame = frame.loc[np.isfinite(frame["proxy"]) & np.isfinite(frame["actual"])].copy()
    dates = np.array(sorted(frame["date"].dt.normalize().unique()))
    if len(dates) < 10:
        raise SystemExit(f"Insufficient distinct dates for chronological evaluation: {len(dates)}")
    split_index = int(np.floor(len(dates) * 0.70))
    train_dates, test_dates = set(dates[:split_index]), set(dates[split_index:])
    train = frame.loc[frame["date"].dt.normalize().isin(train_dates)].copy()
    test = frame.loc[frame["date"].dt.normalize().isin(test_dates)].copy()
    if len(train) < 1000 or len(test) < 500:
        raise SystemExit(f"Insufficient train/test rows: train={len(train)}, test={len(test)}")

    model = LinearRegression().fit(train[["proxy"]], train["actual"])
    test["raw_prediction"] = test["proxy"]
    test["calibrated_prediction"] = model.predict(test[["proxy"]])
    test["raw_abs_error"] = (test["raw_prediction"] - test["actual"]).abs()
    test["cal_abs_error"] = (test["calibrated_prediction"] - test["actual"]).abs()
    test["raw_sq_error"] = (test["raw_prediction"] - test["actual"]) ** 2
    test["cal_sq_error"] = (test["calibrated_prediction"] - test["actual"]) ** 2
    test["raw_error"] = test["raw_prediction"] - test["actual"]
    test["cal_error"] = test["calibrated_prediction"] - test["actual"]

    def metrics(data: pd.DataFrame, prefix: str) -> dict:
        return {
            "mae": float(data[f"{prefix}_abs_error"].mean()),
            "rmse": float(np.sqrt(data[f"{prefix}_sq_error"].mean())),
            "bias": float(data[f"{prefix}_error"].mean()),
        }

    # Paired cluster bootstrap by game date preserves within-date dependence.
    rng = np.random.default_rng(SEED)
    grouped = test.groupby(test["date"].dt.normalize())
    day_values = list(grouped.groups)
    differences = []
    for _ in range(BOOTSTRAPS):
        sampled = rng.choice(day_values, size=len(day_values), replace=True)
        sample = pd.concat([grouped.get_group(day) for day in sampled], ignore_index=True)
        differences.append(float(sample["cal_abs_error"].mean() - sample["raw_abs_error"].mean()))
    ci_low, ci_high = np.quantile(differences, [0.025, 0.975])

    by_minutes = []
    bins = [-np.inf, 12, 20, 28, 36, np.inf]
    labels = ["<=12", "12-20", "20-28", "28-36", ">36"]
    test["minutes_bucket"] = pd.cut(test["minutes"], bins=bins, labels=labels, include_lowest=True)
    for bucket, part in test.groupby("minutes_bucket", observed=True):
        by_minutes.append({
            "minutes_bucket": str(bucket), "n": int(len(part)),
            "proxy_bias": float(part["raw_error"].mean()),
            "calibrated_bias": float(part["cal_error"].mean()),
            "proxy_mae": float(part["raw_abs_error"].mean()),
            "calibrated_mae": float(part["cal_abs_error"].mean()),
        })

    raw, calibrated = metrics(test, "raw"), metrics(test, "cal")
    report = {
        "audit": "chronological_proxy_to_official_pdk_calibration",
        "source": str(SOURCE.relative_to(ROOT)),
        "target": "PDK_OFFICIAL_VALID; rows with invalid/missing official labels excluded",
        "proxy": "existing reconstructed PDK; preserved without mutation",
        "split": {
            "method": "first 70% distinct dates fit; final 30% distinct dates held out",
            "train_first_date": str(train["date"].min().date()),
            "train_last_date": str(train["date"].max().date()),
            "test_first_date": str(test["date"].min().date()),
            "test_last_date": str(test["date"].max().date()),
            "train_rows": int(len(train)), "test_rows": int(len(test)),
            "train_dates": int(len(train_dates)), "test_dates": int(len(test_dates)),
        },
        "calibration": {
            "model": "ordinary least squares: official PDK ~ proxy PDK",
            "intercept": float(model.intercept_),
            "slope": float(model.coef_[0]),
            "fit_only_on_training_dates": True,
        },
        "test_metrics": {"raw_proxy": raw, "affine_calibration": calibrated},
        "paired_date_cluster_bootstrap": {
            "replicates": BOOTSTRAPS, "seed": SEED,
            "estimand": "calibrated MAE minus raw proxy MAE; negative favors calibration",
            "mean_difference": float(np.mean(differences)),
            "ci_95_percentile": [float(ci_low), float(ci_high)],
        },
        "test_bias_by_realized_minutes_descriptive_only": by_minutes,
        "production_change": "none; use calibration only if held-out paired evidence is robust and season-replicated",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUT.relative_to(ROOT)),
        "split": report["split"],
        "calibration": report["calibration"],
        "test_metrics": report["test_metrics"],
        "bootstrap": report["paired_date_cluster_bootstrap"],
    }, indent=2))


if __name__ == "__main__":
    main()
