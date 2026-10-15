#!/usr/bin/env python3
"""Compare single-season and expanding multi-season PDK training windows.

The 2025/26 fold trains only on certified 2020/21-2024/25 targets and is used
only for evaluation. No production files are modified.
"""
from __future__ import annotations
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
OUT = ROOT / "reports/audit"
STAMP = "20261014_v1"
METRICS = OUT / f"dunkest_single_vs_multiseason_train_window_{STAMP}_metrics.csv"
PREDICTIONS = OUT / f"dunkest_single_vs_multiseason_train_window_{STAMP}_predictions.csv"
REPORT = OUT / f"dunkest_single_vs_multiseason_train_window_{STAMP}.md"
AUDIT = OUT / f"dunkest_single_vs_multiseason_train_window_{STAMP}.json"
LABELS = {"5": "2020-21", "7": "2021-22", "9": "2022-23", "13": "2023-24", "19": "2024-25", "25": "2025-26"}
TRAIN_SEASONS = ["5", "7", "9", "13", "19"]
TEST_SEASONS = ["9", "13", "19", "25"]

spec = importlib.util.spec_from_file_location(
    "dunkest_train_only_search",
    ROOT / "scripts/tune_dunkest_pdk_predictor_train_only_v1.py",
)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load the audited train-only feature adapter.")
search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search)


def metric_row(y: np.ndarray, pred: np.ndarray) -> dict:
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "bias_pred_minus_actual": float(np.mean(pred - y)),
    }


def main() -> int:
    for path in (METRICS, PREDICTIONS, REPORT, AUDIT):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite versioned output: {path}")
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(DATA)
    df["season_id"] = df["season_id"].astype(str)
    allowed = set(TRAIN_SEASONS + ["25"])
    df = df.loc[df["season_id"].isin(allowed)].copy()
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce", utc=True)
    df["target_pdk"] = pd.to_numeric(df["target_pdk"], errors="coerce")
    required = {"season_id", "game_date", "dunkest_player_id", "gameId", "target_pdk"}
    if not required.issubset(df.columns):
        raise SystemExit(f"Missing required columns: {sorted(required - set(df.columns))}")
    if df[list(required)].isna().any().any():
        raise SystemExit("Missing target/key values in eligible seasons")
    if df.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise SystemExit("Duplicate player-game key")
    if set(search.BASE + search.EXTRA + ["prev3_nba_min_mean", "prev5_nba_min_mean", "lag1_nba_min"]) - set(df.columns):
        raise SystemExit("Expected past-only feature columns are missing")

    # Verify the official PDK lag is exactly the previous target within a
    # player's season timeline; this is an integrity check, not a model feature.
    ordered = df.sort_values(["dunkest_player_id", "game_date", "gameId"], kind="stable")
    prior = ordered.groupby("dunkest_player_id", sort=False)["target_pdk"].shift(1)
    lag = pd.to_numeric(ordered["lag1_pdk"], errors="coerce")
    valid = prior.notna() & lag.notna()
    lag_mismatches = int(((prior[valid] - lag[valid]).abs() > 1e-9).sum())
    if lag_mismatches:
        raise SystemExit(f"Lag-1 integrity check failed: {lag_mismatches} mismatches")

    rows: list[dict] = []
    predictions: list[pd.DataFrame] = []
    for test_season in TEST_SEASONS:
        prior_seasons = [season for season in TRAIN_SEASONS if int(season) < int(test_season)]
        if not prior_seasons:
            raise SystemExit(f"No eligible prior seasons for test fold {test_season}")
        test = df.loc[df["season_id"].eq(test_season)].copy()
        if test.empty:
            raise SystemExit(f"No test rows for {LABELS[test_season]}")
        y = test["target_pdk"].to_numpy(dtype=float)
        fallback = float(df.loc[df["season_id"].isin(prior_seasons), "target_pdk"].median())
        baseline = pd.to_numeric(test["prev10_pdk_mean"], errors="coerce").fillna(fallback).to_numpy(float)
        rows.append({
            "training_window": "previous_10_mean",
            "test_season_id": test_season,
            "test_season": LABELS[test_season],
            "training_seasons": "none",
            "train_rows": 0,
            **metric_row(y, baseline),
        })
        windows = {
            "single_season": [max(prior_seasons, key=int)],
            "multi_season": prior_seasons,
        }
        for window_name, train_seasons in windows.items():
            train = df.loc[df["season_id"].isin(train_seasons)].copy()
            X_train, numeric, categorical = search.feature_frame(train, "history_flags_trends")
            X_test, _, _ = search.feature_frame(test, "history_flags_trends")
            model = search.build("et_leaf12", numeric, categorical)
            model.fit(X_train, train["target_pdk"].to_numpy(dtype=float))
            pred = np.asarray(model.predict(X_test), dtype=float)
            rows.append({
                "training_window": window_name,
                "test_season_id": test_season,
                "test_season": LABELS[test_season],
                "training_seasons": ";".join(LABELS[s] for s in train_seasons),
                "train_rows": int(len(train)),
                **metric_row(y, pred),
            })
            predictions.append(pd.DataFrame({
                "test_season_id": test_season,
                "test_season": LABELS[test_season],
                "game_date": test["game_date"].dt.strftime("%Y-%m-%d").to_numpy(),
                "dunkest_player_id": test["dunkest_player_id"].astype(str).to_numpy(),
                "gameId": test["gameId"].astype(str).to_numpy(),
                "target_pdk": y,
                "training_window": window_name,
                "training_seasons": ";".join(LABELS[s] for s in train_seasons),
                "prediction": pred,
                "abs_error": np.abs(pred - y),
                "squared_error": np.square(pred - y),
            }))
            print(
                f"{LABELS[test_season]} {window_name} ({len(train):,} train rows): "
                f"MAE={mean_absolute_error(y, pred):.5f}; "
                f"RMSE={mean_squared_error(y, pred) ** 0.5:.5f}",
                flush=True,
            )

    metrics = pd.DataFrame(rows)
    pred_df = pd.concat(predictions, ignore_index=True)
    paired = pred_df.pivot_table(
        index=["test_season_id", "game_date", "dunkest_player_id", "gameId", "target_pdk"],
        columns="training_window", values="abs_error", aggfunc="first",
    ).dropna(subset=["single_season", "multi_season"]).reset_index()
    paired["difference_multi_minus_single"] = paired["multi_season"] - paired["single_season"]
    cluster = paired.groupby(["test_season_id", "game_date"], sort=False)["difference_multi_minus_single"].agg(["sum", "count"])
    rng = np.random.default_rng(20261014)
    sums = cluster["sum"].to_numpy(float)
    counts = cluster["count"].to_numpy(float)
    boot = np.empty(4000, dtype=float)
    for i in range(len(boot)):
        idx = rng.integers(0, len(cluster), size=len(cluster))
        boot[i] = sums[idx].sum() / counts[idx].sum()
    pooled = pred_df.groupby("training_window").apply(
        lambda g: pd.Series({
            "n": len(g),
            "mae": float(g["abs_error"].mean()),
            "rmse": float(np.sqrt(g["squared_error"].mean())),
            "bias_pred_minus_actual": float((g["prediction"] - g["target_pdk"]).mean()),
        }), include_groups=False,
    ).reset_index()
    test_2025 = metrics.loc[metrics["test_season_id"].eq("25")].set_index("training_window")
    multi_2025 = float(test_2025.loc["multi_season", "mae"])
    single_2025 = float(test_2025.loc["single_season", "mae"])
    audit = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(DATA.relative_to(ROOT)),
        "label_source": "certified official Dunkest PDK targets",
        "training_feature_adapter": "history_flags_trends from train-only V1; all features past-only",
        "model": "ExtraTreesRegressor(n_estimators=220, min_samples_leaf=12, max_features=0.85, random_state=2026)",
        "test_folds": {s: LABELS[s] for s in TEST_SEASONS},
        "multi_season_training_policy": "all certified seasons strictly earlier than the test season",
        "single_season_training_policy": "only the immediately preceding certified season",
        "2025_26_fold_training_seasons": [LABELS[s] for s in TRAIN_SEASONS],
        "2025_26_fold_training_rows": int(metrics.loc[(metrics.test_season_id.eq("25")) & metrics.training_window.eq("multi_season"), "train_rows"].iloc[0]),
        "lag1_pdk_mismatches": lag_mismatches,
        "paired_rows": int(len(paired)),
        "paired_date_clusters": int(len(cluster)),
        "bootstrap_replicates": int(len(boot)),
        "mae_difference_multi_minus_single_pooled": float(paired["difference_multi_minus_single"].mean()),
        "mae_difference_95pct_date_cluster_bootstrap": [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))],
        "2025_26_single_season_mae": single_2025,
        "2025_26_multi_season_mae": multi_2025,
        "2025_26_mae_difference_multi_minus_single": multi_2025 - single_2025,
        "production_changed": False,
        "holdout_interpretation": "2025/26 labels are used only to evaluate this fold; they do not enter its fit or model selection. The season has been examined by prior project experiments, so it is not claimed globally untouched.",
    }
    metrics.to_csv(METRICS, index=False)
    pred_df.to_csv(PREDICTIONS, index=False)
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Single-season vs multi-season Dunkest PDK training — V1", "",
        f"Generated UTC: {audit['created_utc']}", "",
        "## Design", "",
        "Both training windows use the same audited past-only feature adapter and the same ExtraTrees configuration. The single-season model sees only the immediately preceding season; the multi-season model sees every certified prior season. No production model/configuration is changed.", "",
        "## Results by test season", "",
        metrics.to_string(index=False, float_format=lambda value: f"{value:.5f}"), "",
        "## Pooled comparison", "",
        pooled.to_string(index=False, float_format=lambda value: f"{value:.5f}"), "",
        f"- Paired pooled MAE difference (multi minus single): {audit['mae_difference_multi_minus_single_pooled']:.5f}.",
        f"- 95% date-cluster bootstrap interval: [{audit['mae_difference_95pct_date_cluster_bootstrap'][0]:.5f}, {audit['mae_difference_95pct_date_cluster_bootstrap'][1]:.5f}].",
        f"- 2025/26 single-season MAE: {single_2025:.5f}; multi-season MAE: {multi_2025:.5f}; difference: {multi_2025-single_2025:+.5f}.", "",
        "## Interpretation", "",
        "A negative difference favours multi-season training. Promote a production change only if the gain is stable across season folds/cohorts and the production-equivalent inference path reproduces the same feature definitions. The 2025/26 fold trains on 2020/21–2024/25 and is the closest match to the requested historical holdout experiment, but it is not globally untouched because other project audits have inspected this season.", "",
        "## Artifacts", "",
        f"- Metrics: `{METRICS.relative_to(ROOT)}`",
        f"- Predictions: `{PREDICTIONS.relative_to(ROOT)}`",
        f"- Audit: `{AUDIT.relative_to(ROOT)}`", "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\nPOOLED METRICS\n" + pooled.to_string(index=False), flush=True)
    print(f"2025/26 paired result: single={single_2025:.5f}; multi={multi_2025:.5f}", flush=True)
    print(f"REPORT={REPORT.relative_to(ROOT)}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
