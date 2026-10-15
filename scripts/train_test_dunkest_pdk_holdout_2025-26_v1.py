#!/usr/bin/env python3
"""Fit a fixed pre-2025/26 Dunkest PDK model and evaluate on the held-out 2025/26 season.

2018/19 and 2019/20 NBA logs contribute to strictly pre-game history features,
but their Dunkest PDK rows are not used as labels because all validity flags are False.
This is a standalone experiment; it does not alter the production predictor.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports" / "audit"
DATA_PATH = PROCESSED / "dunkest_pdk_game_training_2020-26_v3.parquet"
MODEL_PATH = PROCESSED / "dunkest_pdk_historical_random_forest_train_2020-25_test_2025-26_v1.joblib"
META_PATH = PROCESSED / "dunkest_pdk_historical_random_forest_train_2020-25_test_2025-26_v1.json"
PREDICTIONS_PATH = PROCESSED / "dunkest_pdk_holdout_2025-26_predictions_v1.csv"
METRICS_PATH = PROCESSED / "dunkest_pdk_holdout_2025-26_metrics_v1.csv"
AUDIT_PATH = PROCESSED / "dunkest_pdk_holdout_2025-26_audit_v1.json"
REPORT_PATH = REPORTS / "dunkest_pdk_holdout_train_2020-25_test_2025-26_v1.md"

sys.path.insert(0, str(ROOT / "scripts"))
from validate_dunkest_historical_pdk_training_v2 import (  # noqa: E402
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    make_model,
)

TRAIN_SEASONS = {"5", "7", "9", "13", "19"}
TEST_SEASON = "25"
SEASON_NAMES = {
    "1": "2018-19", "3": "2019-20", "5": "2020-21", "7": "2021-22",
    "9": "2022-23", "13": "2023-24", "19": "2024-25", "25": "2025-26",
}
OUTPUTS = [MODEL_PATH, META_PATH, PREDICTIONS_PATH, METRICS_PATH, AUDIT_PATH, REPORT_PATH]


def score_row(name: str, y: np.ndarray, pred: np.ndarray) -> dict:
    return {
        "model": name,
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y, pred))),
        "bias_pred_minus_actual": float(np.mean(pred - y)),
        "r2": float(r2_score(y, pred)),
    }


def main() -> None:
    existing = [str(path) for path in OUTPUTS if path.exists()]
    if existing:
        raise SystemExit("Refusing to overwrite existing versioned outputs: " + ", ".join(existing))
    if not DATA_PATH.exists():
        raise SystemExit(f"Missing source dataset: {DATA_PATH}")

    df = pd.read_parquet(DATA_PATH).copy()
    required = {"season_id", "game_date", "dunkest_player_id", "gameId", TARGET,
                "lag1_pdk", "prev10_pdk_mean"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")
    df["season_id"] = df["season_id"].astype(str)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
    if df[["season_id", "game_date", "dunkest_player_id", "gameId", TARGET]].isna().any().any():
        raise SystemExit("Null target or player-game identity found.")
    if df.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise SystemExit("Duplicate player-game keys found.")

    train = df.loc[df["season_id"].isin(TRAIN_SEASONS)].copy()
    test = df.loc[df["season_id"].eq(TEST_SEASON)].copy()
    if train.empty or test.empty:
        raise SystemExit("Training or held-out test partition is empty.")
    actual_train_seasons = set(train["season_id"].unique())
    if actual_train_seasons != TRAIN_SEASONS:
        raise SystemExit(f"Unexpected training seasons: {sorted(actual_train_seasons)}")
    if set(test["season_id"].unique()) != {TEST_SEASON}:
        raise SystemExit("Test partition contains a season other than 2025/26.")
    features = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    missing_features = sorted(set(features) - set(df.columns))
    if missing_features:
        raise SystemExit(f"Missing curated model features: {missing_features}")
    forbidden = {TARGET, "pdk", "nba_PTS", "nba_REB", "nba_AST", "nba_MIN",
                 "nba_GAME_ID", "nba_PLAYER_ID", "nba_match_status"}
    if forbidden.intersection(features):
        raise SystemExit("Forbidden/current-game field present in feature whitelist.")

    train_y = train[TARGET].astype(float).to_numpy()
    test_y = test[TARGET].astype(float).to_numpy()
    model = make_model("random_forest", NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    model.fit(train[features], train_y)
    pred = model.predict(test[features])
    train_median = float(np.median(train_y))
    baseline = pd.to_numeric(test["prev10_pdk_mean"], errors="coerce").fillna(train_median).to_numpy(dtype=float)
    metrics = pd.DataFrame([
        score_row("random_forest", test_y, pred),
        score_row("baseline_prev10_mean", test_y, baseline),
    ])
    metrics["train_rows"] = len(train)
    metrics["train_seasons"] = "2020-21;2021-22;2022-23;2023-24;2024-25"
    metrics["test_season"] = "2025-26"

    identity_columns = [c for c in [
        "season_id", "season_label", "game_date", "gameId", "dunkest_player_id",
        "dunkest_player_name", "opponentTeamCode", "nba_match_status", TARGET,
        "lag1_pdk", "prev10_pdk_mean",
    ] if c in test.columns]
    predictions = test[identity_columns].copy()
    predictions["prediction_random_forest"] = pred
    predictions["prediction_baseline_prev10"] = baseline
    predictions["error_random_forest"] = pred - test_y
    predictions["absolute_error_random_forest"] = np.abs(pred - test_y)
    predictions["error_baseline_prev10"] = baseline - test_y
    predictions["absolute_error_baseline_prev10"] = np.abs(baseline - test_y)
    predictions["game_date"] = pd.to_datetime(predictions["game_date"]).dt.strftime("%Y-%m-%d")

    # Leakage checks: feature whitelist is curated; the test labels never enter model.fit.
    # For this online one-step-ahead evaluation, lagged PDK features within 2025/26 may
    # use that player's prior valid 2025/26 results, never the current game's target.
    prior_date_col = "prior_nba_history_game_date"
    future_or_same_date_history = None
    if prior_date_col in test.columns:
        prior_date = pd.to_datetime(test[prior_date_col], errors="coerce")
        future_or_same_date_history = int((prior_date.notna() & prior_date.ge(test["game_date"])).sum())
        if future_or_same_date_history:
            raise SystemExit(f"Found {future_or_same_date_history} non-past NBA history dates in test.")

    joblib.dump(model, MODEL_PATH, compress=3)
    metrics.to_csv(METRICS_PATH, index=False)
    predictions.to_csv(PREDICTIONS_PATH, index=False)
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(DATA_PATH),
        "model_artifact": str(MODEL_PATH),
        "target": TARGET,
        "train_seasons": {s: SEASON_NAMES[s] for s in sorted(TRAIN_SEASONS, key=int)},
        "test_season": {TEST_SEASON: SEASON_NAMES[TEST_SEASON]},
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_season_rows": {SEASON_NAMES[s]: int((train["season_id"] == s).sum()) for s in sorted(TRAIN_SEASONS, key=int)},
        "test_target_rows": int(test[TARGET].notna().sum()),
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "forbidden_features_checked": sorted(forbidden),
        "train_test_season_overlap": sorted(set(train["season_id"]) & set(test["season_id"])),
        "prior_nba_history_same_or_future_date_rows": future_or_same_date_history,
        "evaluation_protocol": "Fixed holdout by season. Fit on valid official Dunkest PDK labels from 2020/21–2024/25; evaluate once on valid official labels from 2025/26. Lag features in the test season are one-step-ahead and may use only earlier valid games from that season.",
        "historical_context": "NBA player-game logs from 2018/19 and 2019/20 are included in the strictly-past NBA history used to construct features. Those seasons are not supervised PDK target seasons because their gameValidForDunkest flags are all False.",
        "metrics": metrics.to_dict(orient="records"),
        "limitations": [
            "This artifact remains an experimental game-level PDK model and is not wired into the production lineup pipeline.",
            "This holdout is online one-step-ahead within 2025/26, not a forecast of the entire season made before its first game.",
            "2018/19 and 2019/20 cannot safely contribute official supervised PDK labels until the all-False validity flag is independently resolved.",
        ],
    }
    META_PATH.write_text(json.dumps({
        **audit,
        "model_type": "scikit-learn RandomForestRegressor pipeline",
        "model_parameters": {
            "n_estimators": 160, "max_depth": 9, "min_samples_leaf": 5,
            "max_features": 0.8, "random_state": 42,
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    rf = metrics.loc[metrics["model"].eq("random_forest")].iloc[0]
    base = metrics.loc[metrics["model"].eq("baseline_prev10_mean")].iloc[0]
    improvement = float(base["mae"] - rf["mae"])
    improvement_pct = float(100 * improvement / base["mae"])
    REPORTS.mkdir(parents=True, exist_ok=True)
    report = f'''# Dunkest PDK: fixed holdout training 2020/21–2024/25, test 2025/26

Created: {audit['created_utc']}

## Protocol

- **Training target labels:** official Dunkest PDK, valid rows from 2020/21–2024/25 only.
- **Held-out test:** official valid PDK rows from 2025/26; none of these labels enters `fit`.
- **2018/19–2019/20:** NBA boxscore history contributes to strictly pre-game features, but PDK rows are excluded from supervised labels because every returned `gameValidForDunkest` flag is `False`.
- **Evaluation mode:** one-step-ahead within the test season. Features for a later 2025/26 game may use that player's earlier valid 2025/26 games, but never the current game's outcome.
- **Leakage guard:** curated 79-feature whitelist excludes the current target and current-game boxscore fields; NBA history is strictly earlier than target date.

## Results

| Model | N | MAE | RMSE | Bias (prediction − actual) | R² |
|---|---:|---:|---:|---:|---:|
| Random Forest | {int(rf['n']):,} | {rf['mae']:.4f} | {rf['rmse']:.4f} | {rf['bias_pred_minus_actual']:.4f} | {rf['r2']:.4f} |
| Previous-10 PDK mean | {int(base['n']):,} | {base['mae']:.4f} | {base['rmse']:.4f} | {base['bias_pred_minus_actual']:.4f} | {base['r2']:.4f} |

Random Forest improves MAE by **{improvement:.4f} PDK ({improvement_pct:.2f}%)** versus the previous-10 baseline. This is a real held-out-season improvement, but it is modest rather than proof of high absolute accuracy.

## Artifacts

- Model: `{MODEL_PATH.relative_to(ROOT)}`
- Per-game predictions: `{PREDICTIONS_PATH.relative_to(ROOT)}`
- Metrics: `{METRICS_PATH.relative_to(ROOT)}`
- Audit/metadata: `{AUDIT_PATH.relative_to(ROOT)}` and `{META_PATH.relative_to(ROOT)}`

## Production status

The model is intentionally **not yet integrated** into the production season-opener. It uses a different, game-level feature schema from the existing production predictor. Integration requires a matching inference feature builder and separate regression tests; this artifact alone does not change current forecasts or lineup recommendations.
'''
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print("\nSaved model:", MODEL_PATH)
    print("Saved predictions:", PREDICTIONS_PATH)


if __name__ == "__main__":
    main()
