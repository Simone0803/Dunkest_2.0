#!/usr/bin/env python3
"""Paired walk-forward test of fixed recency weighting for the minutes HGB.

The 2020/21–2024/25 folds are robustness/selection history. The 2025/26 fold is
the predeclared final minutes holdout; its labels are never used to set the
two-season half-life. Production minutes and PDK logic are not modified.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import experiment_dunkest_minutes_rate_decomposition_v1 as base
from dunkest.evaluation.minutes_comparison import paired_game_bootstrap_delta
from dunkest.evaluation.minutes_recency import (
    recency_sample_weights,
    validate_feature_names,
    validate_temporal_fold,
)

TRAIN_PATH = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
HISTORICAL_LABEL_PATH = ROOT / "data/processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
FINAL_LABEL_PATH = ROOT / "data/processed/official_dunkest_vs_nba_matched_2025-26.parquet"
OUT = ROOT / "reports/audit"
STAMP = "dunkest_minutes_hgb_recency_walk_forward_20261024_v1"
REPORT = OUT / f"{STAMP}.md"
METRICS = OUT / f"{STAMP}_metrics.csv"
PREDICTIONS = OUT / f"{STAMP}_predictions.csv"
AUDIT = OUT / f"{STAMP}.json"
FOLDS = {"9": "2022-23", "13": "2023-24", "19": "2024-25", "25": "2025-26"}
FINAL_FOLD = "25"
HALF_LIFE_YEARS = 2.0  # fixed before opening the final fold
BOOTSTRAP_REPS = 2000

FEATURES = (
    base.BASE_NUM
    + [
        "pdk_trend_3v10", "min_trend_3v5", "min_last_vs_prev5",
        "lag1_pdk_per_min", "prev3_pdk_per_min", "prev5_pdk_per_min",
        "lag1_pts_per_min", "prev3_pts_per_min", "prev5_pts_per_min",
        "lag1_reb_per_min", "prev3_reb_per_min", "prev5_reb_per_min",
        "lag1_ast_per_min", "prev3_ast_per_min", "prev5_ast_per_min",
        "lag1_usage_proxy", "prev3_usage_proxy", "prev5_usage_proxy",
    ]
    + base.CAT
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key_types(frame: pd.DataFrame, game_col: str, player_col: str) -> pd.DataFrame:
    out = frame.copy()
    out[game_col] = out[game_col].astype("string").str.strip()
    out[player_col] = pd.to_numeric(out[player_col], errors="coerce").astype("Int64")
    return out


def _load_rows() -> tuple[pd.DataFrame, dict]:
    if not all(path.is_file() for path in (TRAIN_PATH, HISTORICAL_LABEL_PATH, FINAL_LABEL_PATH)):
        raise FileNotFoundError("required local historical minutes inputs are missing")
    frame = pd.read_parquet(TRAIN_PATH)
    frame["season_id"] = frame["season_id"].astype(str)
    frame = frame.loc[frame["season_id"].isin(["5", "7", "9", "13", "19", "25"])].copy()
    frame["game_date"] = pd.to_datetime(frame["game_date"], utc=True, errors="coerce")
    frame = _key_types(frame, "nba_GAME_ID", "nba_PLAYER_ID")
    if frame.duplicated(["season_id", "dunkest_player_id", "gameId"]).any():
        raise ValueError("duplicate Dunkest player-game target rows")

    historical = pd.read_parquet(
        HISTORICAL_LABEL_PATH,
        columns=["nba_GAME_ID", "nba_PLAYER_ID", "nba_MIN", "nba_match_status"],
    )
    historical = historical.loc[
        historical["nba_match_status"].eq("matched_player_date_opponent")
    ].copy()
    historical = _key_types(historical, "nba_GAME_ID", "nba_PLAYER_ID")
    historical["target_minutes"] = pd.to_numeric(historical["nba_MIN"], errors="coerce")
    hist_valid_keys = historical["nba_GAME_ID"].notna() & historical["nba_PLAYER_ID"].notna()
    historical = historical.loc[hist_valid_keys].copy()
    historical_duplicates = historical.loc[
        historical.duplicated(["nba_GAME_ID", "nba_PLAYER_ID"], keep=False)
    ]
    conflicts = historical_duplicates.groupby(
        ["nba_GAME_ID", "nba_PLAYER_ID"], dropna=False
    )["target_minutes"].nunique(dropna=False)
    if conflicts.gt(1).any():
        raise ValueError("conflicting historical NBA target minutes for an identity key")
    historical = historical.drop_duplicates(["nba_GAME_ID", "nba_PLAYER_ID"], keep="first")

    final = pd.read_parquet(
        FINAL_LABEL_PATH,
        columns=["game_id_nba", "PLAYER_ID", "MIN", "gameValidForDunkest", "join_status"],
    )
    final = final.loc[
        final["gameValidForDunkest"].eq(True)
        & final["join_status"].eq("matched_name_date_opponent")
    ].copy()
    final = _key_types(final, "game_id_nba", "PLAYER_ID")
    final["target_minutes"] = pd.to_numeric(final["MIN"], errors="coerce")
    if final.duplicated(["game_id_nba", "PLAYER_ID"]).any():
        raise ValueError("2025/26 official crosswalk has duplicate player-game labels")

    old = frame.loc[frame["season_id"].ne(FINAL_FOLD)].copy()
    old = old.merge(
        historical[["nba_GAME_ID", "nba_PLAYER_ID", "target_minutes"]],
        on=["nba_GAME_ID", "nba_PLAYER_ID"], how="left", validate="many_to_one",
    )
    new = frame.loc[frame["season_id"].eq(FINAL_FOLD)].copy()
    new = new.merge(
        final[["game_id_nba", "PLAYER_ID", "target_minutes"]],
        left_on=["nba_GAME_ID", "nba_PLAYER_ID"],
        right_on=["game_id_nba", "PLAYER_ID"], how="left", validate="many_to_one",
    )
    combined = pd.concat([old, new], ignore_index=True, sort=False)
    combined["target_minutes"] = pd.to_numeric(combined["target_minutes"], errors="coerce")
    bad_target = combined["target_minutes"].notna() & (
        ~np.isfinite(combined["target_minutes"]) | combined["target_minutes"].lt(0)
    )
    if bad_target.any():
        raise ValueError("minutes target has non-finite or negative values")
    target_missing = int(combined["target_minutes"].isna().sum())
    combined = combined.loc[combined["target_minutes"].notna()].copy()
    if combined[["nba_GAME_ID", "nba_PLAYER_ID", "dunkest_player_id"]].isna().any().any():
        raise ValueError("scored rows require stable player ID and NBA player-game identity")
    if combined.duplicated(["nba_GAME_ID", "nba_PLAYER_ID"]).any():
        raise ValueError("scored player-game target identity is ambiguous")
    combined = base.make_features(combined).replace([np.inf, -np.inf], np.nan)
    return combined, {
        "source_rows": int(len(frame)),
        "rows_after_target_link": int(len(combined)),
        "rows_without_target_minutes_excluded": target_missing,
        "historical_label_rows_unique": int(len(historical)),
        "historical_label_duplicate_keys_same_minutes_collapsed": int(len(historical_duplicates)),
        "final_2025_26_official_valid_label_rows": int(len(final)),
        "valid_dunkest_player_id_rows": int(combined["dunkest_player_id"].notna().sum()),
        "unique_nba_games": int(combined["nba_GAME_ID"].nunique()),
        "season_rows": combined.groupby("season_id").size().astype(int).to_dict(),
    }


def _score(y: np.ndarray, prediction: np.ndarray) -> dict:
    error = prediction - y
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, prediction)),
        "rmse": float(mean_squared_error(y, prediction) ** 0.5),
        "bias_pred_minus_actual": float(error.mean()),
    }


def _previous5_bootstrap(frame: pd.DataFrame, prediction_col: str, *, seed: int) -> dict | None:
    paired = frame.loc[frame["previous5_baseline"].notna()].copy()
    if paired["nba_GAME_ID"].nunique() < 2:
        return None
    paired = paired.rename(columns={
        "target_minutes": "minutes_actual",
        "previous5_baseline": "minutes_hybrid",
        prediction_col: "minutes_hgb",
        "nba_GAME_ID": "nba_game_id",
    })
    return paired_game_bootstrap_delta(
        paired, game_col="nba_game_id", n_bootstrap=BOOTSTRAP_REPS, seed=seed
    )


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render small audit tables without an optional tabulate dependency."""
    columns = [str(column) for column in frame.columns]

    def cell(value: object) -> str:
        if isinstance(value, (float, np.floating)):
            value = f"{value:.4f}"
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines.extend(
        "| " + " | ".join(cell(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame, *, weighted: bool) -> np.ndarray:
    estimator = base.model("hgb")
    y = train["target_minutes"].to_numpy(float)
    fit_kwargs = {}
    if weighted:
        origin = pd.to_datetime(test["game_date"], utc=True).min()
        fit_kwargs["model__sample_weight"] = recency_sample_weights(
            train["game_date"], as_of=origin, half_life_years=HALF_LIFE_YEARS
        ).to_numpy(float)
    estimator.fit(train[FEATURES], y, **fit_kwargs)
    return np.clip(estimator.predict(test[FEATURES]), 0.0, 48.0)


def _cohort_metrics(frame: pd.DataFrame, *, fold: str) -> list[dict]:
    cohorts = {
        "all": np.ones(len(frame), dtype=bool),
        "zero_minutes_verified_label": frame["target_minutes"].eq(0).to_numpy(),
        "positive_minutes": frame["target_minutes"].gt(0).to_numpy(),
        "low_history_lt5_proxy_not_rookie_label": pd.to_numeric(
            frame["history_games_before_target"], errors="coerce"
        ).fillna(0).lt(5).to_numpy(),
        "history_ge5": pd.to_numeric(
            frame["history_games_before_target"], errors="coerce"
        ).fillna(0).ge(5).to_numpy(),
        "actual_minutes_ge25": frame["target_minutes"].ge(25).to_numpy(),
    }
    rows = []
    for cohort, mask in cohorts.items():
        subset = frame.loc[mask]
        if subset.empty:
            continue
        for model_name, column in (("hgb_initial", "prediction_initial"), ("hgb_recency", "prediction_recency")):
            rows.append({
                "fold_id": fold, "fold": FOLDS[fold], "cohort": cohort,
                "model": model_name, "n_games": int(subset["nba_GAME_ID"].nunique()),
                **_score(subset["target_minutes"].to_numpy(float), subset[column].to_numpy(float)),
            })
    return rows


def main() -> None:
    for path in (REPORT, METRICS, PREDICTIONS, AUDIT):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing experiment output: {path}")
    validate_feature_names(FEATURES)
    data, coverage = _load_rows()
    fold_rows: list[dict] = []
    prediction_frames: list[pd.DataFrame] = []
    fold_audits: dict[str, dict] = {}
    for fold in FOLDS:
        train = data.loc[data["season_id"].map(lambda value: int(value) < int(fold))].copy()
        test = data.loc[data["season_id"].eq(fold)].copy()
        fold_check = validate_temporal_fold(train, test)
        if (train["nba_GAME_ID"].astype(str).isin(test["nba_GAME_ID"].astype(str))).any():
            raise ValueError(f"player-game identity leaks across fold {FOLDS[fold]}")
        initial = _fit_predict(train, test, weighted=False)
        recency = _fit_predict(train, test, weighted=True)
        if len(initial) != len(recency) or not np.isfinite(initial).all() or not np.isfinite(recency).all():
            raise ValueError("HGB forecasts are missing or non-finite on the shared test cohort")
        scored = test[[
            "season_id", "game_date", "gameId", "dunkest_player_id", "nba_GAME_ID",
            "nba_PLAYER_ID", "target_minutes", "history_games_before_target",
        ]].copy()
        scored["prediction_initial"] = initial
        scored["prediction_recency"] = recency
        scored["previous5_baseline"] = pd.to_numeric(
            test["prev5_nba_min_mean"], errors="coerce"
        ).to_numpy(float)
        scored["train_max_date_utc"] = fold_check["train_max_date_utc"]
        scored["test_min_date_utc"] = fold_check["test_min_date_utc"]
        prediction_frames.append(scored)
        pair = scored.rename(columns={
            "target_minutes": "minutes_actual",
            "prediction_initial": "minutes_hybrid",
            "prediction_recency": "minutes_hgb",
            "nba_GAME_ID": "nba_game_id",
        })
        ci = paired_game_bootstrap_delta(
            pair,
            game_col="nba_game_id",
            n_bootstrap=BOOTSTRAP_REPS,
            seed=20261024 + int(fold),
        )
        y = scored["target_minutes"].to_numpy(float)
        row = {
            "fold_id": fold, "fold": FOLDS[fold], "n_games": int(scored["nba_GAME_ID"].nunique()),
            "train_rows": int(len(train)), "shared_test_rows": int(len(scored)),
            "initial": _score(y, initial), "recency": _score(y, recency),
            "delta_recency_minus_initial": {
                key: float(_score(y, recency)[key] - _score(y, initial)[key])
                for key in ("mae", "rmse", "bias_pred_minus_actual")
            },
            "paired_game_bootstrap_ci95_delta": ci,
            "paired_rows_with_prev5_for_baseline": int(scored["previous5_baseline"].notna().sum()),
            "prev5_metrics_on_shared_prev5_cohort": None,
        }
        prev5_valid = scored["previous5_baseline"].notna()
        if prev5_valid.any():
            baseline_y = y[prev5_valid.to_numpy()]
            row["prev5_metrics_on_shared_prev5_cohort"] = _score(
                baseline_y, scored.loc[prev5_valid, "previous5_baseline"].to_numpy(float)
            )
            row["hgb_initial_metrics_on_shared_prev5_cohort"] = _score(
                baseline_y, initial[prev5_valid.to_numpy()]
            )
            row["hgb_recency_metrics_on_shared_prev5_cohort"] = _score(
                baseline_y, recency[prev5_valid.to_numpy()]
            )
        fold_rows.extend(_cohort_metrics(scored, fold=fold))
        fold_audits[fold] = {
            **fold_check,
            "train_min_date_utc": pd.to_datetime(train["game_date"], utc=True).min().isoformat(),
            "train_max_date_utc": pd.to_datetime(train["game_date"], utc=True).max().isoformat(),
            "test_games": int(scored["nba_GAME_ID"].nunique()),
            "test_actual_zero_minutes": int(scored["target_minutes"].eq(0).sum()),
            "test_low_history_lt5": int(pd.to_numeric(
                scored["history_games_before_target"], errors="coerce"
            ).fillna(0).lt(5).sum()),
            "weights": {
                "rule": "2 ** (-age_years / half_life_years)",
                "half_life_years": HALF_LIFE_YEARS,
                "weight_at_fold_origin": pd.to_datetime(test["game_date"], utc=True).min().isoformat(),
                "min": float(recency_sample_weights(
                    train["game_date"], as_of=pd.to_datetime(test["game_date"], utc=True).min(),
                    half_life_years=HALF_LIFE_YEARS,
                ).min()),
                "max": float(recency_sample_weights(
                    train["game_date"], as_of=pd.to_datetime(test["game_date"], utc=True).min(),
                    half_life_years=HALF_LIFE_YEARS,
                ).max()),
            },
        }
        print(f"{FOLDS[fold]}: train={len(train):,} test={len(test):,} games={scored['nba_GAME_ID'].nunique():,}", flush=True)

    predictions = pd.concat(prediction_frames, ignore_index=True)
    if predictions.duplicated(["nba_GAME_ID", "nba_PLAYER_ID"]).any():
        raise ValueError("duplicate paired prediction identity")
    metrics = pd.DataFrame(fold_rows)
    predictions.to_csv(PREDICTIONS, index=False)
    metrics.to_csv(METRICS, index=False)
    fold_results = []
    for fold in FOLDS:
        group = predictions.loc[predictions["season_id"].eq(fold)]
        y = group["target_minutes"].to_numpy(float)
        initial = group["prediction_initial"].to_numpy(float)
        recency = group["prediction_recency"].to_numpy(float)
        ci = paired_game_bootstrap_delta(
            group.rename(columns={
                "target_minutes": "minutes_actual",
                "prediction_initial": "minutes_hybrid",
                "prediction_recency": "minutes_hgb",
                "nba_GAME_ID": "nba_game_id",
            }), game_col="nba_game_id", n_bootstrap=BOOTSTRAP_REPS,
            seed=20261024 + int(fold),
        )
        result = {
            "fold_id": fold, "fold": FOLDS[fold],
            "train_rows": fold_audits[fold]["train_rows"],
            "n": int(len(group)), "n_games": int(group["nba_GAME_ID"].nunique()),
            "hgb_initial": _score(y, initial), "hgb_recency": _score(y, recency),
            "delta_recency_minus_initial": {
                key: float(_score(y, recency)[key] - _score(y, initial)[key])
                for key in ("mae", "rmse", "bias_pred_minus_actual")
            },
            "paired_game_bootstrap_ci95_delta": ci,
            "previous5_baseline_on_available_cohort": None,
        }
        previous5_valid = group["previous5_baseline"].notna()
        if previous5_valid.any():
            shared_y = group.loc[previous5_valid, "target_minutes"].to_numpy(float)
            result["previous5_baseline_on_available_cohort"] = {
                "n": int(previous5_valid.sum()),
                "n_games": int(group.loc[previous5_valid, "nba_GAME_ID"].nunique()),
                "previous5": _score(shared_y, group.loc[previous5_valid, "previous5_baseline"].to_numpy(float)),
                "hgb_initial": _score(shared_y, group.loc[previous5_valid, "prediction_initial"].to_numpy(float)),
                "hgb_recency": _score(shared_y, group.loc[previous5_valid, "prediction_recency"].to_numpy(float)),
                "ci95_initial_minus_prev5": _previous5_bootstrap(
                    group, "prediction_initial", seed=20300000 + int(fold)
                ),
                "ci95_recency_minus_prev5": _previous5_bootstrap(
                    group, "prediction_recency", seed=20400000 + int(fold)
                ),
            }
        result["subgroups"] = {
            cohort: {
                r["model"]: r for r in fold_rows
                if r["fold_id"] == fold and r["cohort"] == cohort
            }
            for cohort in sorted({r["cohort"] for r in fold_rows if r["fold_id"] == fold})
        }
        fold_results.append(result)

    # Pooled rows combine disjoint held-out seasons with a common target definition.
    pooled_y = predictions["target_minutes"].to_numpy(float)
    pooled_initial = predictions["prediction_initial"].to_numpy(float)
    pooled_recency = predictions["prediction_recency"].to_numpy(float)
    pooled_ci = paired_game_bootstrap_delta(
        predictions.rename(columns={
            "target_minutes": "minutes_actual",
            "prediction_initial": "minutes_hybrid",
            "prediction_recency": "minutes_hgb",
            "nba_GAME_ID": "nba_game_id",
        }), game_col="nba_game_id", n_bootstrap=BOOTSTRAP_REPS, seed=20261024,
    )
    audit = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "fixed two-season exponential recency weighting of existing HGB minutes estimator",
        "hypothesis": "recent minutes relationships drift across seasons; recency weighting may improve held-out MAE without altering features or estimator hyperparameters",
        "intervention_predeclared": True,
        "production_model_changed": False,
        "production_hybrid_changed": False,
        "optimizer_changed": False,
        "input_files": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
            for path in (TRAIN_PATH, HISTORICAL_LABEL_PATH, FINAL_LABEL_PATH)
        ],
        "dataset_coverage": coverage,
        "seasons_with_target_data": ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"],
        "excluded_seasons": {
            "2018-19": "official Dunkest labels invalid for target scoring per existing historical-data audit",
            "2019-20": "official Dunkest labels invalid for target scoring per existing historical-data audit",
        },
        "folds": fold_audits,
        "final_holdout_fold": FINAL_FOLD,
        "final_holdout_used_for_selection": False,
        "feature_names": FEATURES,
        "feature_policy": "existing past-only expanded-lag history from the audited walk-forward; target-game minutes are labels only",
        "model": {
            "implementation": "existing historical-walk-forward base.model('hgb') from experiment_dunkest_minutes_rate_decomposition_v1.py; same HGB estimator parameters as production shadow, but not an exact production feature/preprocessing replay",
            "estimator": "HistGradientBoostingRegressor(max_iter=180, learning_rate=0.06, max_leaf_nodes=31, l2_regularization=5, min_samples_leaf=40, random_state=2026)",
            "preprocessing": "fold-local numeric median imputation with missing indicators and categorical one-hot encoding",
            "production_parity_limit": "historical archive supplies an expanded-lag schema with a one-hot/imputer pipeline; current predictor uses selected FEATURE_COLS and _fit_matrix numeric medians. The stored historical table does not contain all current production inputs, so exact shadow replay is not claimed",
        },
        "recency_rule": {
            "formula": "weight = 2 ** (-age_years / half_life_years)",
            "half_life_years": HALF_LIFE_YEARS,
            "selection": "fixed a priori; no tuning against any holdout fold",
        },
        "primary_metrics": "paired HGB initial vs recency on identical labeled NBA player-game rows",
        "paired_cluster_bootstrap_replicates": BOOTSTRAP_REPS,
        "pooled": {
            "n": int(len(predictions)), "n_games": int(predictions["nba_GAME_ID"].nunique()),
            "hgb_initial": _score(pooled_y, pooled_initial),
            "hgb_recency": _score(pooled_y, pooled_recency),
            "delta_recency_minus_initial": {
                key: float(_score(pooled_y, pooled_recency)[key] - _score(pooled_y, pooled_initial)[key])
                for key in ("mae", "rmse", "bias_pred_minus_actual")
            },
            "paired_game_bootstrap_ci95_delta": pooled_ci,
            "previous5_baseline_on_available_cohort": None,
        },
        "fold_results": fold_results,
        "baseline_prev5_note": "reported only on rows with a real prev-five value; not presented as the production hybrid",
        "production_hybrid_reconstruction": "not possible from this archive: historical per-game Dunkest role, lineup, credit, availability, same-team competition, and positional allocation inputs are not preserved as-of each game",
        "pdk_impact": "not evaluated; the saved histories lack the exact historical market/availability/rotation inputs needed to replay the production PDK path with only minutes changed",
        "subgroup_policy": {
            "rookie": "not directly identifiable; history_games_before_target < 5 is a low-history proxy only",
            "team_change": "not scored as a cohort because the target-row current NBA team lacks independent as-of provenance in this dataset",
            "role_rotation_availability": "not evaluable from these historical training rows",
            "zero_minutes": "observed target label zero; only present when explicitly represented by matched log data",
        },
    }
    pooled_prev5 = predictions["previous5_baseline"].notna()
    if pooled_prev5.any():
        shared_y = predictions.loc[pooled_prev5, "target_minutes"].to_numpy(float)
        audit["pooled"]["previous5_baseline_on_available_cohort"] = {
            "n": int(pooled_prev5.sum()),
            "n_games": int(predictions.loc[pooled_prev5, "nba_GAME_ID"].nunique()),
            "previous5": _score(shared_y, predictions.loc[pooled_prev5, "previous5_baseline"].to_numpy(float)),
            "hgb_initial": _score(shared_y, predictions.loc[pooled_prev5, "prediction_initial"].to_numpy(float)),
            "hgb_recency": _score(shared_y, predictions.loc[pooled_prev5, "prediction_recency"].to_numpy(float)),
            "ci95_initial_minus_prev5": _previous5_bootstrap(
                predictions, "prediction_initial", seed=20300000
            ),
            "ci95_recency_minus_prev5": _previous5_bootstrap(
                predictions, "prediction_recency", seed=20400000
            ),
        }
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    pooled_delta = audit["pooled"]["delta_recency_minus_initial"]
    report = [
        "# HGB minuti — recency weighting walk-forward V1", "",
        f"Generato UTC: {audit['generated_utc']}", "",
        "## Ipotesi e protocollo", "",
        "Intervento unico preregistrato: pesare il training HGB per recenza con emivita fissa di due anni (`2 ** (-age_years / 2)`). Non si aggiungono feature e non si cambiano estimator, imputazione o schema. I fold 2022/23–2024/25 misurano robustezza storica; il 2025/26 è il test finale minuti separato e non seleziona l'intervento. In ogni fold il training termina prima della prima data di test; le mediane e gli encoder sono rifittati sul solo training.", "",
        "## Dati e copertura", "",
        f"Dataset base: {coverage['source_rows']:,} righe; dopo link target verificato e date valide: {coverage['rows_after_target_link']:,}. Righe senza label escluse: {coverage['rows_without_target_minutes_excluded']:,}. Righe finali hanno ID Dunkest, `nba_GAME_ID` e `nba_PLAYER_ID` univoci. 2018/19 e 2019/20 sono esclusi perché le etichette ufficiali Dunkest non sono valide; dati 2020/21–2025/26 sono presenti. Il 2025/26 usa il crosswalk ufficiale locale univoco (`gameValidForDunkest=True`, `matched_name_date_opponent`).", "",
        "## Risultati appaiati", "",
        f"Cohort comune: {len(predictions):,} player-game, {predictions['nba_GAME_ID'].nunique():,} partite. Delta pooled recency − HGB iniziale: MAE {pooled_delta['mae']:+.4f}, RMSE {pooled_delta['rmse']:+.4f}, bias {pooled_delta['bias_pred_minus_actual']:+.4f} minuti. IC 95% bootstrap appaiato per partita: `{json.dumps(pooled_ci, sort_keys=True)}`. Valore negativo di MAE/RMSE favorisce recency; bias è differenza tra i bias dei modelli.", "",
        "### Per fold", "",
        _markdown_table(pd.DataFrame([{
            "fold": item["fold"], "n": item["n"], "games": item["n_games"],
            "initial_MAE": item["hgb_initial"]["mae"], "recency_MAE": item["hgb_recency"]["mae"],
            "delta_MAE": item["delta_recency_minus_initial"]["mae"],
            "initial_RMSE": item["hgb_initial"]["rmse"], "recency_RMSE": item["hgb_recency"]["rmse"],
            "delta_RMSE": item["delta_recency_minus_initial"]["rmse"],
            "initial_bias": item["hgb_initial"]["bias_pred_minus_actual"],
            "recency_bias": item["hgb_recency"]["bias_pred_minus_actual"],
            "CI95_delta_MAE": item["paired_game_bootstrap_ci95_delta"]["mae"],
        } for item in fold_results])), "",
        "### Baseline prev5 sul sottoinsieme comune con storico disponibile", "",
        _markdown_table(pd.DataFrame([
            {"cohort": "all_folds_prev5_available", **audit["pooled"]["previous5_baseline_on_available_cohort"]["previous5"]},
            {"cohort": "all_folds_HGB_initial_same_rows", **audit["pooled"]["previous5_baseline_on_available_cohort"]["hgb_initial"]},
            {"cohort": "all_folds_HGB_recency_same_rows", **audit["pooled"]["previous5_baseline_on_available_cohort"]["hgb_recency"]},
            {"cohort": "2025_26_prev5_available", **fold_results[-1]["previous5_baseline_on_available_cohort"]["previous5"]},
            {"cohort": "2025_26_HGB_initial_same_rows", **fold_results[-1]["previous5_baseline_on_available_cohort"]["hgb_initial"]},
            {"cohort": "2025_26_HGB_recency_same_rows", **fold_results[-1]["previous5_baseline_on_available_cohort"]["hgb_recency"]},
        ])), "",
        "### Sottogruppi", "",
        _markdown_table(metrics.loc[metrics["cohort"].ne("all")]), "",
        "## Baseline, PDK e limiti", "",
        "La media degli ultimi cinque minuti è riportata solo sul suo sottoinsieme con valore disponibile; non viene chiamata modello ibrido. La formula ibrida di produzione non è ricostruibile fedelmente per queste partite: mancano snapshot storici as-of di ruolo Dunkest, gruppo lineup, crediti, disponibilità, concorrenza e allocazione per posizione. Per lo stesso motivo non si stima l'impatto PDK con una moltiplicazione minuti × rate. Rookie reali, cambi di squadra as-of, ruolo e disponibilità non sono etichette affidabili in questi record; sono marcati non valutabili. I casi a zero sono solo target zero esplicitamente presenti nel log collegato.", "",
        "## Decisione", "",
        f"**Scartare la modifica recency.** Nel test finale 2025/26 peggiora MAE di {next(item for item in fold_results if item['fold_id'] == FINAL_FOLD)['delta_recency_minus_initial']['mae']:+.4f} minuti (IC95% appaiato per partita `{next(item for item in fold_results if item['fold_id'] == FINAL_FOLD)['paired_game_bootstrap_ci95_delta']['mae']}`) e RMSE di {next(item for item in fold_results if item['fold_id'] == FINAL_FOLD)['delta_recency_minus_initial']['rmse']:+.4f}. La MAE migliora marginalmente in 2022/23 e 2024/25, ma peggiora in 2023/24 e 2025/26. HGB resta in shadow. Sul test 2025/26 il HGB iniziale batte la baseline prev5 sul sottoinsieme comune, ma ciò non dimostra superiorità sull'ibrido di produzione. Nessuna promozione o modifica PDK è giustificata.", "",
        "## Riproduzione", "",
        "```bash\nPYTHONPATH=src .venv/bin/python scripts/experiment_dunkest_minutes_hgb_recency_v1.py\n```", "",
        f"Metriche: `{METRICS.relative_to(ROOT)}`; predizioni appaiate: `{PREDICTIONS.relative_to(ROOT)}`; audit macchina: `{AUDIT.relative_to(ROOT)}`.", "",
        "No production model/config/optimizer changes; no commit or push.", "",
    ]
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(report[0], flush=True)
    print(f"Pooled delta: MAE={pooled_delta['mae']:+.4f}; RMSE={pooled_delta['rmse']:+.4f}; bias={pooled_delta['bias_pred_minus_actual']:+.4f}", flush=True)
    print(f"Final 2025/26: {next(item for item in fold_results if item['fold_id'] == FINAL_FOLD)['delta_recency_minus_initial']}", flush=True)
    print(f"Audit: {REPORT.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
