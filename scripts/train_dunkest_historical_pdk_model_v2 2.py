#!/usr/bin/env python3
"""Fit an experimental historical Dunkest PDK model after walk-forward validation.

The artifact is deliberately separate from the production optimizer.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "scripts"))
from validate_dunkest_historical_pdk_training_v2 import (  # noqa: E402
    CATEGORICAL_FEATURES,
    DATA_PATH,
    NUMERIC_FEATURES,
    TARGET,
    make_model,
)

MODEL_PATH = PROCESSED / "dunkest_pdk_historical_random_forest_2020-25_v2.joblib"
META_PATH = PROCESSED / "dunkest_pdk_historical_random_forest_2020-25_v2.json"
METRICS_PATH = PROCESSED / "dunkest_pdk_game_walk_forward_metrics_2020-25_v2.csv"
AUDIT_PATH = PROCESSED / "dunkest_pdk_game_walk_forward_audit_2020-25_v2.json"


def main() -> None:
    if MODEL_PATH.exists() or META_PATH.exists():
        raise SystemExit("Refusing to overwrite an existing model artifact.")
    if not DATA_PATH.exists():
        raise SystemExit(f"Missing training data: {DATA_PATH}")
    if not METRICS_PATH.exists() or not AUDIT_PATH.exists():
        raise SystemExit("Run the walk-forward validation first.")

    df = pd.read_parquet(DATA_PATH).copy()
    df["season_id"] = df["season_id"].astype(str)
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
    df = df.loc[df[TARGET].notna()].copy()
    features = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    missing = sorted(set(features) - set(df.columns))
    if missing:
        raise SystemExit("Missing safe features: " + str(missing))

    model = make_model("random_forest", NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    model.fit(df[features], df[TARGET].astype(float))
    joblib.dump(model, MODEL_PATH, compress=3)

    metrics = pd.read_csv(METRICS_PATH)
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    rf_rows = metrics.loc[metrics["model"].eq("random_forest")]
    baseline_rows = metrics.loc[metrics["model"].eq("baseline_prev10_mean")]
    comparison = []
    for season_id in ("9", "13", "19"):
        rf = rf_rows.loc[rf_rows["test_season_id"].astype(str).eq(season_id)]
        baseline = baseline_rows.loc[baseline_rows["test_season_id"].astype(str).eq(season_id)]
        if rf.empty or baseline.empty:
            continue
        rf_row, base_row = rf.iloc[0], baseline.iloc[0]
        comparison.append({
            "season_id": season_id,
            "season": str(rf_row["test_season"]),
            "model_mae": float(rf_row["mae"]),
            "baseline_prev10_mae": float(base_row["mae"]),
            "mae_improvement_abs": float(base_row["mae"] - rf_row["mae"]),
            "mae_improvement_pct": float(100.0 * (base_row["mae"] - rf_row["mae"]) / base_row["mae"]),
            "model_rmse": float(rf_row["rmse"]),
            "baseline_prev10_rmse": float(base_row["rmse"]),
        })

    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model_artifact": str(MODEL_PATH),
        "model_type": "sklearn RandomForestRegressor pipeline",
        "model_scope": "experimental V2 historical PDK predictor; not loaded by the production pipeline",
        "training_dataset": str(DATA_PATH),
        "training_rows": len(df),
        "target": TARGET,
        "training_seasons": sorted(df["season_id"].unique(), key=int),
        "safe_numeric_features": NUMERIC_FEATURES,
        "safe_categorical_features": CATEGORICAL_FEATURES,
        "model_parameters": {
            "n_estimators": 160,
            "max_depth": 9,
            "min_samples_leaf": 5,
            "max_features": 0.8,
            "random_state": 42,
        },
        "preprocessing": "Numeric median imputation with missingness indicators + scaling; categorical most-frequent imputation + one-hot encoding with unknown categories ignored.",
        "walk_forward_validation": comparison,
        "mean_walk_forward_mae": float(rf_rows["mae"].mean()) if not rf_rows.empty else None,
        "mean_baseline_prev10_mae": float(baseline_rows["mae"].mean()) if not baseline_rows.empty else None,
        "walk_forward_audit": str(AUDIT_PATH),
        "limitations": [
            "Artifact is experimental and has not been integrated with the Dunkest production prediction pipeline.",
            "Training targets are official PDK values for gameValidForDunkest=True records in seasons 2020/21–2024/25.",
            "The validation is expanding season-level walk-forward with prior game outcomes available as lagged features; it is an online one-step-ahead test.",
            "NBA boxscore features use the latest NBA game strictly before the target date, including prior games that were not marked Dunkest-valid.",
            "Seasons 2018/19 and 2019/20 are excluded from strict target training because all returned gameValidForDunkest values are False.",
            "This model predicts a player's PDK for a game; it does not solve lineup, coach, price, availability, or transfer optimization.",
        ],
    }
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print("MODEL SAVED:", MODEL_PATH)
    print("METADATA:", META_PATH)
    print("Training rows:", len(df))
    print("Walk-forward RF vs previous-10 mean:")
    print(pd.DataFrame(comparison).to_string(index=False))


if __name__ == "__main__":
    main()
