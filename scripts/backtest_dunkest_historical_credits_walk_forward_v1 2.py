#!/usr/bin/env python3
"""Leakage-safe walk-forward test of lagged Dunkest credits and player form.

Uses historical player-week/round outcome tables. Current-round CR and statistics
are never used as features: all numeric history and CR inputs are shifted from
strictly earlier rounds. Official-valid target seasons only are included.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet"
OUT = ROOT / "reports/audit"
STEM = "dunkest_lagged_credit_walk_forward_20261013_v1"
METRICS = OUT / f"{STEM}_metrics.csv"
PREDICTIONS = OUT / f"{STEM}_predictions.csv"
AUDIT = OUT / f"{STEM}.json"
REPORT = OUT / f"{STEM}.md"
# 2020/21–2024/25 have verified official Dunkest targets in this source.
VALID_SEASONS = ["5", "7", "9", "13", "19"]
TEST_SEASONS = ["9", "13", "19"]


def metric_row(y: np.ndarray, p: np.ndarray, season: str, family: str, n: int) -> dict:
    err = p - y
    return {
        "test_season_id": season,
        "test_season": {"9": "2022-23", "13": "2023-24", "19": "2024-25"}.get(season, season),
        "feature_family": family,
        "n": int(n),
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(mean_squared_error(y, p) ** 0.5),
        "bias_pred_minus_actual": float(np.mean(err)),
    }


def build_features(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    d["season_id"] = d["source_season_id"].astype(str)
    d["player_name"] = d["player_name"].astype(str).str.strip()
    d["player_key"] = d["player_name"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    d["source_week"] = pd.to_numeric(d["source_week"], errors="coerce")
    d["source_round"] = pd.to_numeric(d["source_round"], errors="coerce")
    d["round_key"] = d["source_week"].astype("Int64").astype(str) + ":" + d["source_round"].astype("Int64").astype(str)
    round_order = d[["season_id", "source_week", "source_round"]].drop_duplicates().sort_values(
        ["season_id", "source_week", "source_round"]
    )
    round_order["round_index"] = round_order.groupby("season_id").cumcount() + 1
    d = d.merge(round_order, on=["season_id", "source_week", "source_round"], how="left", validate="many_to_one")
    d = d.sort_values(["season_id", "player_key", "round_index"]).reset_index(drop=True)

    numeric_history = {
        "cr": "lag1_cr",
        "target_pdk_round_total": "lag1_pdk",
        "min_avg": "lag1_min_avg",
        "min_tot": "lag1_min_tot",
        "plus": "lag1_plus",
        "gp": "lag1_gp",
        "pts_avg": "lag1_pts_avg",
        "reb_avg": "lag1_reb_avg",
        "ast_avg": "lag1_ast_avg",
        "stl_avg": "lag1_stl_avg",
        "blk_avg": "lag1_blk_avg",
        "tov_avg": "lag1_tov_avg",
        "plus_minus_avg": "lag1_plus_minus_avg",
    }
    for source, dest in numeric_history.items():
        values = pd.to_numeric(d[source], errors="coerce")
        d[dest] = values.groupby([d["season_id"], d["player_key"]]).shift(1)

    for window in (3, 5, 10):
        d[f"prev{window}_pdk_mean"] = d.groupby(["season_id", "player_key"])["lag1_pdk"].transform(
            lambda s: s.shift(0).rolling(window, min_periods=1).mean()
        )
        d[f"prev{window}_min_mean"] = d.groupby(["season_id", "player_key"])["lag1_min_avg"].transform(
            lambda s: s.shift(0).rolling(window, min_periods=1).mean()
        )
    # Explicit recency/gap features; the last known CR is always from an earlier round.
    d["last_seen_round_index"] = d["round_index"] - d.groupby(["season_id", "player_key"])["round_index"].shift(1)
    d["credit_age_rounds"] = d["last_seen_round_index"]
    d["prior_round_present"] = d["last_seen_round_index"].eq(1).astype(int)
    d["history_rounds_before_target"] = d.groupby(["season_id", "player_key"]).cumcount()
    # All category values come from the player's most recent earlier observed round.
    for source, dest in (("role", "lagged_role"), ("team_code", "lagged_team")):
        d[dest] = d.groupby(["season_id", "player_key"])[source].shift(1).astype(object)
        d[dest] = d[dest].where(pd.notna(d[dest]), np.nan)
    d["season_round_index"] = d["round_index"]
    return d


def make_model(numeric: list[str], categorical: list[str]) -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True))]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                              ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ],
        remainder="drop",
    )
    return Pipeline([("preprocess", pre), ("model", ExtraTreesRegressor(
        n_estimators=180, min_samples_leaf=8, max_features=0.85,
        random_state=42, n_jobs=-1,
    ))])


def main() -> int:
    for p in (METRICS, PREDICTIONS, AUDIT, REPORT):
        if p.exists():
            raise SystemExit(f"Refusing to overwrite versioned artifact: {p}")
    if not INPUT.is_file():
        raise FileNotFoundError(INPUT)
    raw = pd.read_parquet(INPUT)
    raw["source_season_id"] = raw["source_season_id"].astype(str)
    raw = raw.loc[raw["source_season_id"].isin(VALID_SEASONS)].copy()
    raw["target_pdk_round_total"] = pd.to_numeric(raw["target_pdk_round_total"], errors="coerce")
    raw = raw.loc[np.isfinite(raw["target_pdk_round_total"])].copy()
    d = build_features(raw)

    # These feature groups are deliberately nested to measure the incremental
    # value of lagged CR, not to select a production change automatically.
    form_num = ["lag1_pdk", "prev3_pdk_mean", "prev5_pdk_mean", "prev10_pdk_mean",
                "lag1_min_avg", "prev3_min_mean", "prev5_min_mean", "lag1_plus",
                "lag1_pts_avg", "lag1_reb_avg", "lag1_ast_avg", "lag1_stl_avg",
                "lag1_blk_avg", "lag1_tov_avg", "lag1_plus_minus_avg",
                "lag1_gp", "history_rounds_before_target", "credit_age_rounds", "prior_round_present"]
    credit_num = ["lag1_cr"]
    categorical = ["lagged_role", "lagged_team"]
    families = {
        "historical_form_only": (form_num, []),
        "historical_form_plus_lagged_credit": (form_num + credit_num, categorical),
        "historical_form_plus_credit_no_team": (form_num + credit_num, ["lagged_role"]),
    }
    metrics = []
    predictions = []
    fold_audit = []
    for test_season in TEST_SEASONS:
        train = d.loc[d["season_id"].isin(VALID_SEASONS[:VALID_SEASONS.index(test_season)])].copy()
        test = d.loc[d["season_id"].eq(test_season)].copy()
        if train.empty or test.empty:
            fold_audit.append({"test_season_id": test_season, "status": "skipped_empty_fold", "train_rows": len(train), "test_rows": len(test)})
            continue
        y_train = train["target_pdk_round_total"].to_numpy(float)
        y_test = test["target_pdk_round_total"].to_numpy(float)
        # Simple lagged baselines: they are based only on previous-round scores.
        for name, pred in (
            ("baseline_last_round", pd.to_numeric(test["lag1_pdk"], errors="coerce")),
            ("baseline_previous5_mean", pd.to_numeric(test["prev5_pdk_mean"], errors="coerce")),
            ("baseline_train_median", pd.Series(np.full(len(test), float(np.median(y_train))), index=test.index)),
        ):
            valid = pred.notna().to_numpy() & np.isfinite(pred.to_numpy(float))
            if valid.any():
                metrics.append(metric_row(y_test[valid], pred.to_numpy(float)[valid], test_season, name, int(valid.sum())))
                for ix in np.flatnonzero(valid):
                    row = test.iloc[ix]
                    predictions.append({"season_id": test_season, "season": row.get("source_season_label", test_season),
                        "round_index": int(row["round_index"]), "source_week": int(row["source_week"]),
                        "source_round": int(row["source_round"]), "player_name": row["player_name"],
                        "actual_pdk_round_total": float(y_test[ix]), "predicted_pdk_round_total": float(pred.iloc[ix]),
                        "feature_family": name, "lagged_cr": row.get("lag1_cr"), "lag1_pdk": row.get("lag1_pdk")})
        for family, (numeric, cats) in families.items():
            model = make_model(numeric, cats)
            model.fit(train[numeric + cats], y_train)
            pred = model.predict(test[numeric + cats])
            metrics.append(metric_row(y_test, pred, test_season, family, len(test)))
            for ix, p in enumerate(pred):
                row = test.iloc[ix]
                predictions.append({"season_id": test_season, "season": row.get("source_season_label", test_season),
                    "round_index": int(row["round_index"]), "source_week": int(row["source_week"]),
                    "source_round": int(row["source_round"]), "player_name": row["player_name"],
                    "actual_pdk_round_total": float(y_test[ix]), "predicted_pdk_round_total": float(p),
                    "feature_family": family, "lagged_cr": row.get("lag1_cr"), "lag1_pdk": row.get("lag1_pdk")})
        fold_audit.append({
            "test_season_id": test_season, "status": "evaluated", "train_rows": len(train), "test_rows": len(test),
            "train_seasons": sorted(train["season_id"].unique().tolist()),
            "test_rounds": int(test[["source_week", "source_round"]].drop_duplicates().shape[0]),
            "test_rows_with_lagged_cr": int(test["lag1_cr"].notna().sum()),
            "test_rows_with_exact_previous_round_cr": int(test["prior_round_present"].eq(1).sum()),
            "test_rows_with_lagged_pdk": int(test["lag1_pdk"].notna().sum()),
        })
    m = pd.DataFrame(metrics)
    p = pd.DataFrame(predictions)
    m.to_csv(METRICS, index=False)
    p.to_csv(PREDICTIONS, index=False)
    summary = m.groupby("feature_family").agg(n_rows=("n", "sum"), folds=("test_season_id", "nunique"),
        mean_fold_mae=("mae", "mean"), mean_fold_rmse=("rmse", "mean"), mean_fold_bias=("bias_pred_minus_actual", "mean")).reset_index()
    # Pooled out-of-fold metrics weighted by actual prediction rows; no training predictions included.
    pooled = []
    for family, g in p.groupby("feature_family"):
        err = g["predicted_pdk_round_total"].astype(float) - g["actual_pdk_round_total"].astype(float)
        pooled.append({"feature_family": family, "n": len(g), "pooled_mae": float(err.abs().mean()),
                       "pooled_rmse": float(np.sqrt(np.mean(err ** 2))), "pooled_bias": float(err.mean())})
    pooled_df = pd.DataFrame(pooled)
    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "input": str(INPUT.relative_to(ROOT)),
        "target_definition": "Official-valid Dunkest PDK total from each archived player-week/round row.",
        "feature_policy": "Every CR/form feature is shifted from the player's last observed earlier round. The current-round CR, PDK, minutes, boxscore stats, plusvalenza, and starter status are never features.",
        "round_price_semantics": "Historical weekly-round tables are not timestamped market snapshots. Lagged CR is a prior-observed-round proxy, not proof of exact pre-lock credit for every player. Rows also report whether the prior archived round had a player row.",
        "season_policy": {"valid_target_season_ids": VALID_SEASONS, "test_season_ids": TEST_SEASONS,
                          "invalid_official_target_seasons_excluded": ["1", "3"]},
        "folds": fold_audit, "rows_input": len(raw), "rows_with_lagged_cr": int(d["lag1_cr"].notna().sum()),
        "rows_with_exact_previous_round_row": int(d["prior_round_present"].eq(1).sum()),
        "feature_families": {k: {"numeric": v[0], "categorical": v[1]} for k, v in families.items()},
        "fold_metrics": m.to_dict("records"), "pooled_oof_metrics": pooled_df.to_dict("records"),
        "production_changed": False,
        "limitations": [
            "This phase validates round-level player score prediction with lagged historical credits; it does not yet claim a complete historical optimal-lineup result.",
            "Historical player-round archives list observed player rows, not a complete timestamped pre-lock player universe. Full lineup optimization needs a verified candidate universe and historically correct role/budget rules.",
            "Historical coach credit markets are not present in these player archives. Coach outcome components can be reconstructed from final NBA team scores, but exact credit-adjusted coach PDK requires historical coach CRs or a separately validated reconstruction."
        ]
    }
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = ["# Dunkest historical lagged-credit walk-forward — V1", "",
        f"Generated (UTC): {audit['generated_at_utc']}", "",
        "## Method", "",
        "Each target is the official-valid player PDK total in a historical Dunkest week/round. Features are built by shifting player CR, PDK, minutes, plusvalenza and box-score summaries from earlier observed rounds only. No current-round CR or statistics enter the predictor.", "",
        "The test is expanding-origin by season: train on earlier valid seasons and predict a later season. Seasons 2018/19 and 2019/20 are excluded as supervised targets because their official validity flags are false in the local archive.", "",
        "## Pooled out-of-fold metrics", "",
        pooled_df.to_string(index=False), "", "## Metrics by held-out season", "", m.to_string(index=False), "",
        "## Coverage and interpretation", ""]
    for f in fold_audit:
        lines.append(f"- Season ID {f['test_season_id']}: {f['test_rows']:,} test rows over {f.get('test_rounds', 0)} rounds; lagged CR present on {f.get('test_rows_with_lagged_cr', 0):,} rows; exact prior archived-round row on {f.get('test_rows_with_exact_previous_round_cr', 0):,} rows.")
    lines += ["", "## Limitations", "",
        "This is the first market-aware player-score backtest, not yet a complete optimal-lineup backtest. The weekly-round files contain outcome rows rather than a full timestamped pre-lock market universe. A valid lineup backtest must avoid using the target-round player list as if it were known before lock.", "",
        "The local player archives also lack historical coach CR markets. NBA final team points and margins can reconstruct the coach score before the credit-difference multiplier; exact historical coach PDK needs the historical coach prices or a validated reconstruction.", "",
        "Production model/configuration remains unchanged.", "", "## Artifacts", "",
        f"- Metrics: `{METRICS.relative_to(ROOT)}`", f"- Predictions: `{PREDICTIONS.relative_to(ROOT)}`", f"- Audit JSON: `{AUDIT.relative_to(ROOT)}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "rows_input": len(raw), "metrics": str(METRICS.relative_to(ROOT)),
        "predictions": str(PREDICTIONS.relative_to(ROOT)), "audit": str(AUDIT.relative_to(ROOT)),
        "report": str(REPORT.relative_to(ROOT)), "pooled_oof_metrics": pooled_df.to_dict("records"), "folds": fold_audit}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
