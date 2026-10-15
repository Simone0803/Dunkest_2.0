#!/usr/bin/env python3
"""Train-only walk-forward search for the Dunkest player PDK predictor.

Uses only verified target seasons through 2024/25. The 2025/26 holdout is not
loaded into the experiment, and no production artifacts are overwritten.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
OUT = ROOT / "reports/audit"
STAMP = "20261013_train_only_v1"
METRICS = OUT / f"dunkest_pdk_train_only_search_{STAMP}_metrics.csv"
PREDICTIONS = OUT / f"dunkest_pdk_train_only_search_{STAMP}_predictions.csv"
REPORT = OUT / f"dunkest_pdk_train_only_search_{STAMP}.md"
AUDIT = OUT / f"dunkest_pdk_train_only_search_{STAMP}.json"
LABELS = {"5":"2020-21", "7":"2021-22", "9":"2022-23", "13":"2023-24", "19":"2024-25"}
TRAIN_SEASONS = ["5", "7", "9", "13", "19"]
VALIDATION_SEASONS = ["9", "13", "19"]
NUM = ["history_games_before_target", "rest_days_from_nba_logs", "lag1_pdk", "lag2_pdk", "lag3_pdk", "lag4_pdk", "lag5_pdk", "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean", "prev5_pdk_std"]
for stat in ["nba_min","nba_pts","nba_reb","nba_ast","nba_stl","nba_blk","nba_tov","nba_fg3m","nba_fga","nba_ftm","nba_oreb","nba_dreb","nba_plus_minus"]:
    NUM += [f"lag1_{stat}",f"lag2_{stat}",f"lag3_{stat}",f"prev3_{stat}_mean",f"prev5_{stat}_mean"]
CAT = ["opponentTeamCode", "opponentTeamPosition"]
BASE = NUM + CAT
EXTRA = ["nba_history_games_before_target", "lag1_had_nba_match"]


def feature_frame(df: pd.DataFrame, family: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    x = df[BASE].copy()
    nums = list(NUM)
    cats = list(CAT)
    if family in {"history_flags", "history_flags_trends"}:
        x["nba_history_games_before_target"] = pd.to_numeric(df["nba_history_games_before_target"], errors="coerce")
        x["lag1_had_nba_match"] = pd.to_numeric(df["lag1_had_nba_match"], errors="coerce")
        nums += EXTRA
    if family == "history_flags_trends":
        x["pdk_trend_3v10"] = pd.to_numeric(df["prev3_pdk_mean"], errors="coerce") - pd.to_numeric(df["prev10_pdk_mean"], errors="coerce")
        x["minutes_trend_3v5"] = pd.to_numeric(df["prev3_nba_min_mean"], errors="coerce") - pd.to_numeric(df["prev5_nba_min_mean"], errors="coerce")
        x["minutes_last_vs_prev5"] = pd.to_numeric(df["lag1_nba_min"], errors="coerce") - pd.to_numeric(df["prev5_nba_min_mean"], errors="coerce")
        nums += ["pdk_trend_3v10", "minutes_trend_3v5", "minutes_last_vs_prev5"]
    return x, nums, cats


def build(kind: str, nums: list[str], cats: list[str]) -> Pipeline:
    # Dense one-hot output supports both tree families and histogram boosting.
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True))])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
    prep = ColumnTransformer([("num", numeric, nums), ("cat", categorical, cats)], remainder="drop", sparse_threshold=0)
    if kind == "et_leaf5":
        model = ExtraTreesRegressor(n_estimators=220, max_depth=None, min_samples_leaf=5, max_features=0.85, n_jobs=-1, random_state=2026)
    elif kind == "et_leaf8":
        model = ExtraTreesRegressor(n_estimators=220, max_depth=None, min_samples_leaf=8, max_features=0.85, n_jobs=-1, random_state=2026)
    elif kind == "et_leaf12":
        model = ExtraTreesRegressor(n_estimators=220, max_depth=None, min_samples_leaf=12, max_features=0.85, n_jobs=-1, random_state=2026)
    elif kind == "et_depth16_leaf5":
        model = ExtraTreesRegressor(n_estimators=220, max_depth=16, min_samples_leaf=5, max_features=0.85, n_jobs=-1, random_state=2026)
    elif kind == "rf_depth12_leaf5":
        model = RandomForestRegressor(n_estimators=220, max_depth=12, min_samples_leaf=5, max_features=0.85, n_jobs=-1, random_state=2026)
    elif kind == "hist_gradient":
        model = HistGradientBoostingRegressor(max_iter=240, learning_rate=0.06, max_leaf_nodes=31, l2_regularization=5.0, min_samples_leaf=40, random_state=2026)
    else:
        raise ValueError(kind)
    return Pipeline([("preprocess", prep), ("model", model)])


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {"n": int(len(y)), "mae": float(mean_absolute_error(y, p)), "rmse": float(mean_squared_error(y, p) ** 0.5), "bias_pred_minus_actual": float(np.mean(p-y))}


def main() -> int:
    for path in (METRICS, PREDICTIONS, REPORT, AUDIT):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite versioned output: {path}")
    OUT.mkdir(parents=True, exist_ok=True)
    # Explicitly load only target seasons through 2024/25. Holdout rows never enter this run.
    df = pd.read_parquet(DATA)
    df["season_id"] = df["season_id"].astype(str)
    df = df.loc[df["season_id"].isin(TRAIN_SEASONS)].copy()
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce", utc=True)
    df["target_pdk"] = pd.to_numeric(df["target_pdk"], errors="coerce")
    if df[["season_id", "game_date", "dunkest_player_id", "gameId", "target_pdk"]].isna().any().any():
        raise SystemExit("Missing target/key in eligible training seasons")
    if df.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise SystemExit("Duplicate player-game key")
    if set(BASE + EXTRA + ["prev3_nba_min_mean", "prev5_nba_min_mean", "lag1_nba_min"]) - set(df.columns):
        raise SystemExit("Expected feature columns are missing")
    # Leakage guard: lag1 PDK must equal the prior target within each Dunkest player timeline.
    ordered = df.sort_values(["dunkest_player_id", "game_date", "gameId"], kind="stable")
    prev_target = ordered.groupby("dunkest_player_id", sort=False)["target_pdk"].shift(1)
    lag = pd.to_numeric(ordered["lag1_pdk"], errors="coerce")
    valid = prev_target.notna() & lag.notna()
    mismatch = int(((prev_target[valid] - lag[valid]).abs() > 1e-9).sum())
    if mismatch:
        raise SystemExit(f"Leakage/integrity guard failed: {mismatch} lag mismatches")

    candidates = [(family, kind) for family in ["base", "history_flags_trends"] for kind in ["et_leaf8", "et_leaf12", "hist_gradient"]]
    rows, predictions = [], []
    for season in VALIDATION_SEASONS:
        train_seasons = [s for s in TRAIN_SEASONS if int(s) < int(season)]
        tr = df.loc[df["season_id"].isin(train_seasons)].copy()
        te = df.loc[df["season_id"].eq(season)].copy()
        y = te["target_pdk"].to_numpy(float)
        baseline = pd.to_numeric(te["prev10_pdk_mean"], errors="coerce").fillna(float(tr["target_pdk"].median())).to_numpy(float)
        rows.append({"feature_family":"baseline", "model":"prev10_mean", "fold_season_id":season, "fold_season":LABELS[season], "train_rows":len(tr), **metrics(y, baseline)})
        for family, kind in candidates:
            Xtr, nums, cats = feature_frame(tr, family)
            Xte, _, _ = feature_frame(te, family)
            model = build(kind, nums, cats)
            model.fit(Xtr, tr["target_pdk"].to_numpy(float))
            pred = np.asarray(model.predict(Xte), dtype=float)
            result = {"feature_family":family, "model":kind, "fold_season_id":season, "fold_season":LABELS[season], "train_rows":len(tr), **metrics(y, pred)}
            rows.append(result)
            predictions.append(pd.DataFrame({"season_id":season, "season":LABELS[season], "game_date":te["game_date"].dt.strftime("%Y-%m-%d").to_numpy(), "dunkest_player_id":te["dunkest_player_id"].astype(str).to_numpy(), "gameId":te["gameId"].astype(str).to_numpy(), "target_pdk":y, "feature_family":family, "model":kind, "prediction":pred}))
            print(f"{LABELS[season]} {family}/{kind}: MAE={result['mae']:.5f}; RMSE={result['rmse']:.5f}", flush=True)
    detail = pd.DataFrame(rows)
    model_rows = detail.loc[detail["model"].ne("prev10_mean")].copy()
    summary = model_rows.groupby(["feature_family", "model"], as_index=False).apply(lambda g: pd.Series({"weighted_mae":np.average(g["mae"], weights=g["n"]), "weighted_rmse":np.sqrt(np.average(np.square(g["rmse"]), weights=g["n"])), "weighted_bias":np.average(g["bias_pred_minus_actual"], weights=g["n"]), "folds":g["fold_season_id"].nunique()}), include_groups=False).reset_index(drop=True)
    baseline_summary = detail.loc[detail["model"].eq("prev10_mean")].agg({"n":"sum", "mae":"mean", "rmse":"mean"}).to_dict()
    detail.to_csv(METRICS, index=False)
    pd.concat(predictions, ignore_index=True).to_csv(PREDICTIONS, index=False)
    summary = summary.sort_values(["weighted_mae", "weighted_rmse"]).reset_index(drop=True)
    best = summary.iloc[0].to_dict()
    audit = {"created_utc":datetime.now(timezone.utc).isoformat(), "dataset":str(DATA.relative_to(ROOT)), "seasons_loaded":{s:LABELS[s] for s in TRAIN_SEASONS}, "validation_seasons":{s:LABELS[s] for s in VALIDATION_SEASONS}, "holdout_season_2025_26_loaded":False, "feature_families":{"base":BASE, "history_flags":BASE+EXTRA, "history_flags_trends":BASE+EXTRA+["pdk_trend_3v10", "minutes_trend_3v5", "minutes_last_vs_prev5"]}, "candidate_count":len(candidates), "best_validation_candidate":best, "all_candidates":summary.to_dict("records"), "lag1_pdk_mismatches":mismatch, "selection_rule":"lowest player-game weighted MAE over expanding-origin 2022/23-2024/25 folds; RMSE tie-breaker", "production_changed":False, "holdout_note":"2025/26 rows were filtered out before fitting and scoring. Historical project reports have previously inspected that season, so it is not claimed globally untouched."}
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Dunkest PDK predictor search — train-only V1", "", f"Generated UTC: {audit['created_utc']}", "", "## Objective", "", "Improve player-game PDK prediction with expanding-origin validation only through 2024/25. Season 2025/26 is filtered out before fitting/scoring and is not used for model selection.", "", "## Leakage / data checks", "", f"- Training rows loaded: {len(df):,} across 2020/21–2024/25.", f"- Lag-1 PDK integrity mismatches: {mismatch}.", f"- Validation folds: 2022/23, 2023/24, 2024/25; each fold trains only on earlier target seasons.", "- Metrics are player-game level; no claim of lineup-level improvement is made.", "", "## Candidate summary", "", summary.to_string(index=False, float_format=lambda value: f"{value:.5f}"), "", "## Best candidate by validation MAE", "", json.dumps(best, indent=2), "", "## Interpretation", "", "The winning candidate is selected on pooled out-of-fold MAE, with RMSE as a tie-breaker. Any small gain should be considered provisional until paired, season/round-clustered uncertainty is computed and a production-equivalent inference path is validated. No production model/configuration is changed by this experiment.", "", "## Artifacts", "", f"- Metrics: `{METRICS.relative_to(ROOT)}`", f"- Predictions: `{PREDICTIONS.relative_to(ROOT)}`", f"- Audit: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\nTOP CANDIDATES\n" + summary.head(10).to_string(index=False), flush=True)
    print(f"REPORT={REPORT.relative_to(ROOT)}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
