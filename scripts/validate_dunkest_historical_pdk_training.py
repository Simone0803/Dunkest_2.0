#!/usr/bin/env python3
"""Leakage-aware walk-forward validation for official Dunkest game PDK targets.

This is an isolated historical experiment. It does not change production forecasts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
DATA_PATH = PROCESSED / "dunkest_pdk_game_training_2020-25_v1.parquet"
PRED_PATH = PROCESSED / "dunkest_pdk_game_walk_forward_predictions_2020-25_v1.csv"
METRICS_PATH = PROCESSED / "dunkest_pdk_game_walk_forward_metrics_2020-25_v1.csv"
AUDIT_PATH = PROCESSED / "dunkest_pdk_game_walk_forward_audit_2020-25_v1.json"

NUMERIC_FEATURES = [
    "history_games_before_target",
    "lag1_pdk", "lag2_pdk", "lag3_pdk", "lag4_pdk", "lag5_pdk",
    "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean", "prev5_pdk_std",
]
for alias in [
    "nba_min", "nba_pts", "nba_reb", "nba_ast", "nba_stl", "nba_blk",
    "nba_tov", "nba_fg3m", "nba_fga", "nba_ftm", "nba_oreb",
    "nba_dreb", "nba_plus_minus",
]:
    NUMERIC_FEATURES.extend([
        f"lag1_{alias}", f"lag2_{alias}", f"lag3_{alias}",
        f"prev3_{alias}_mean", f"prev5_{alias}_mean",
    ])
CATEGORICAL_FEATURES = ["opponentTeamCode", "opponentTeamPosition"]
TARGET = "target_pdk"
TEST_SEASONS = ["9", "13", "19"]
SEASON_LABELS = {
    "5": "2020-21", "7": "2021-22", "9": "2022-23",
    "13": "2023-24", "19": "2024-25",
}


def metrics(y: pd.Series, pred: np.ndarray, baseline_median: float, name: str) -> dict:
    valid = y.notna() & np.isfinite(pred)
    yt = y.loc[valid].astype(float)
    yp = pd.Series(pred, index=y.index).loc[valid].astype(float)
    if not len(yt):
        return {"model": name, "n": 0}
    return {
        "model": name,
        "n": int(len(yt)),
        "mae": float(mean_absolute_error(yt, yp)),
        "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
        "bias_pred_minus_actual": float((yp - yt).mean()),
        "r2": float(r2_score(yt, yp)),
    }


def make_model(kind: str, numeric: list[str], categorical: list[str]):
    numeric_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
    ])
    categorical_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    transform = ColumnTransformer([
        ("numeric", numeric_pipe, numeric),
        ("categorical", categorical_pipe, categorical),
    ])
    if kind == "ridge":
        estimator = Ridge(alpha=3.0)
    elif kind == "random_forest":
        estimator = RandomForestRegressor(
            n_estimators=160, max_depth=9, min_samples_leaf=5,
            max_features=0.8, n_jobs=-1, random_state=42,
        )
    else:
        raise ValueError(kind)
    return Pipeline([("preprocess", transform), ("model", estimator)])


def main() -> None:
    for path in [PRED_PATH, METRICS_PATH, AUDIT_PATH]:
        if path.exists():
            raise SystemExit("Refusing to overwrite existing output: " + str(path))
    if not DATA_PATH.exists():
        raise SystemExit("Training dataset not found: " + str(DATA_PATH))
    df = pd.read_parquet(DATA_PATH).copy()
    required = {"season_id", "game_date", "dunkest_player_id", "gameId", TARGET}
    if not required.issubset(df.columns):
        raise SystemExit("Required columns missing: " + str(sorted(required - set(df.columns))))
    df["season_id"] = df["season_id"].astype(str)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
    if df[["season_id", "game_date", "dunkest_player_id", "gameId"]].isna().any().any():
        raise SystemExit("Null season/date/player/game identity found in training data.")
    if df.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise SystemExit("Duplicate player-game identity in training dataset.")
    if df[TARGET].isna().any():
        raise SystemExit("Null target values in training dataset.")

    # Verify every lag directly from the preceding target-valid rows.
    df = df.sort_values(["game_date", "season_id", "dunkest_player_id", "gameId"], kind="stable").reset_index(drop=True)
    expected_lag = df.groupby("dunkest_player_id", sort=False)[TARGET].shift(1)
    stored_lag = pd.to_numeric(df["lag1_pdk"], errors="coerce")
    both = expected_lag.notna() & stored_lag.notna()
    lag_mismatch = int(((expected_lag[both] - stored_lag[both]).abs() > 1e-9).sum())
    lag_missing_mismatch = int((expected_lag.isna() != stored_lag.isna()).sum())
    if lag_mismatch or lag_missing_mismatch:
        raise SystemExit(f"lag1_pdk temporal integrity failed: values={lag_mismatch}, missingness={lag_missing_mismatch}")

    # Ensure the feature whitelist contains no same-game target, game ID or current boxscore.
    all_features = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    missing_features = sorted(set(all_features) - set(df.columns))
    if missing_features:
        raise SystemExit("Declared safe features missing: " + str(missing_features))
    forbidden = [
        TARGET, "pdk", "nba_PTS", "nba_REB", "nba_AST", "nba_MIN",
        "nba_GAME_ID", "nba_PLAYER_ID", "nba_match_status",
    ]
    leakage_features = sorted(set(all_features) & set(forbidden))
    if leakage_features:
        raise SystemExit("Leakage risk in declared features: " + str(leakage_features))

    metrics_rows = []
    prediction_parts = []
    fold_details = []
    for test_season in TEST_SEASONS:
        season_order = sorted(SEASON_LABELS, key=lambda x: int(x))
        test_pos = season_order.index(test_season)
        prior_seasons = set(season_order[:test_pos])
        train = df[df["season_id"].isin(prior_seasons)].copy()
        test = df[df["season_id"].eq(test_season)].copy()
        if train.empty or test.empty:
            continue
        train_y = train[TARGET].astype(float)
        test_y = test[TARGET].astype(float)
        train_median = float(train_y.median())
        fold_pred = test[[
            "season_id", "season_label", "game_date", "gameId",
            "dunkest_player_id", "dunkest_player_name", "nba_match_status",
            TARGET, "lag1_pdk", "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean",
        ]].copy()
        fold_pred["prediction_season"] = SEASON_LABELS[test_season]

        baselines = {
            "baseline_lag1_pdk": pd.to_numeric(test["lag1_pdk"], errors="coerce").fillna(train_median).to_numpy(),
            "baseline_prev3_mean": pd.to_numeric(test["prev3_pdk_mean"], errors="coerce").fillna(train_median).to_numpy(),
            "baseline_prev5_mean": pd.to_numeric(test["prev5_pdk_mean"], errors="coerce").fillna(train_median).to_numpy(),
            "baseline_prev10_mean": pd.to_numeric(test["prev10_pdk_mean"], errors="coerce").fillna(train_median).to_numpy(),
            "baseline_train_median": np.full(len(test), train_median),
        }
        for name, pred in baselines.items():
            row = metrics(test_y, pred, train_median, name)
            row.update({
                "test_season_id": test_season,
                "test_season": SEASON_LABELS[test_season],
                "train_rows": len(train), "test_rows": len(test),
                "train_seasons": " ".join(sorted(prior_seasons, key=int)),
            })
            metrics_rows.append(row)
            fold_pred[name] = pred

        x_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
        for kind in ("ridge", "random_forest"):
            model = make_model(kind, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
            model.fit(train[x_cols], train_y)
            pred = model.predict(test[x_cols])
            name = kind
            row = metrics(test_y, pred, train_median, name)
            row.update({
                "test_season_id": test_season,
                "test_season": SEASON_LABELS[test_season],
                "train_rows": len(train), "test_rows": len(test),
                "train_seasons": " ".join(sorted(prior_seasons, key=int)),
            })
            metrics_rows.append(row)
            fold_pred[name] = pred
            fold_details.append({
                "test_season_id": test_season, "model": kind,
                "train_rows": len(train), "test_rows": len(test),
                "train_target_mean": float(train_y.mean()),
                "train_target_median": train_median,
                "test_target_mean": float(test_y.mean()),
                "test_prediction_mean": float(np.mean(pred)),
                "test_prediction_std": float(np.std(pred)),
            })
        prediction_parts.append(fold_pred)

    if not prediction_parts:
        raise SystemExit("No chronological folds could be evaluated.")
    predictions = pd.concat(prediction_parts, ignore_index=True)
    report = pd.DataFrame(metrics_rows)
    predictions["game_date"] = pd.to_datetime(predictions["game_date"]).dt.strftime("%Y-%m-%d")
    predictions.to_csv(PRED_PATH, index=False)
    report.to_csv(METRICS_PATH, index=False)

    # Strict no-same-day leakage audit: each player's prior target must be earlier than the target date.
    target_rows = df[df["season_id"].astype(str).isin(TEST_SEASONS)]
    duplicate_player_dates = int(target_rows.duplicated(["dunkest_player_id", "game_date"]).sum())
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(DATA_PATH),
        "target": TARGET,
        "test_seasons": {s: SEASON_LABELS[s] for s in TEST_SEASONS},
        "train_policy": "Expanding season-level walk-forward: train only on preceding seasons; test on the next season.",
        "within_test_season_policy": "Precomputed lagged features update after each prior target-valid game for that player; this is a one-step-ahead setting, not a whole-season batch forecast.",
        "rows": len(df),
        "lag1_mismatch_count": lag_mismatch,
        "lag1_missingness_mismatch_count": lag_missing_mismatch,
        "duplicate_player_dates_in_test_seasons": duplicate_player_dates,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "forbidden_columns_checked": forbidden,
        "fold_details": fold_details,
        "metrics": metrics_rows,
        "best_model_each_fold": {},
        "limitations": [
            "This is a stand-alone experiment; it does not change production prediction or lineup optimization.",
            "Target is official per-game Dunkest PDK for rows marked gameValidForDunkest=True.",
            "No current-game boxscore is used as a predictor; NBA stats enter only as shifted lagged features.",
            "Predictions are walk-forward within each test season; later test rows may use earlier test-season outcomes as historical features.",
            "Game-valid flags are all false in seasons 2018/19 and 2019/20, so those seasons remain outside the strict target definition pending separate semantic verification.",
        ],
    }
    for season in TEST_SEASONS:
        subset = report[report["test_season_id"].astype(str).eq(season)]
        if not subset.empty:
            best = subset.loc[subset["mae"].idxmin()]
            audit["best_model_each_fold"][SEASON_LABELS[season]] = {
                "model": str(best["model"]), "mae": float(best["mae"]),
                "rmse": float(best["rmse"]), "r2": float(best["r2"]),
            }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== WALK-FORWARD VALIDATION ===")
    print(report.sort_values(["test_season_id", "mae"]).to_string(index=False))
    print("\nTemporal checks:")
    print("lag1 exact-value mismatches:", lag_mismatch)
    print("lag1 missingness mismatches:", lag_missing_mismatch)
    print("duplicate player/date rows in test seasons:", duplicate_player_dates)
    print("\nOutputs:")
    print(PRED_PATH)
    print(METRICS_PATH)
    print(AUDIT_PATH)


if __name__ == "__main__":
    main()
