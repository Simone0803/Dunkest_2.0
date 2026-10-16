from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import warnings
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from scipy.optimize import minimize

from dunkest.config import Settings
from dunkest.data.temporal import validate_prematch_features
from dunkest.names import player_key, player_surname
from dunkest.rules.eligibility import play_probability
from dunkest.rules.pdk import normalize_position
from dunkest.uncertainty.quantiles import (
    add_uncertainty_columns,
    interval_coverage_by_cohort,
)
from dunkest.models.rookie_prior import (
    COLLEGE_MINUTES_BASE_WEIGHT,
    COLLEGE_PRIOR_BASE_WEIGHT,
    COLLEGE_PRIOR_FADE_GAMES,
)
from dunkest.models.capital_gain import add_capital_gain_forecasts
from dunkest.models.historical_pdk import predict_historical_pdk

try:
    from xgboost import XGBRegressor
except ImportError:
    XGBRegressor = None

try:
    from lightgbm import LGBMRegressor
except ImportError:
    LGBMRegressor = None


FEATURE_COLS = [
    "pdk_mean_3",
    "pdk_mean_5",
    "pdk_mean_10",
    "pdk_mean_15",
    "pdk_std_5",
    "pdk_median_5",
    "pdk_season_mean",
    "min_mean_5",
    "min_mean_10",
    "pdk_per_min_season",
    "expected_pdk_minutes_model",
    "pts_mean_5",
    "reb_mean_5",
    "ast_mean_5",
    "stl_per36_5",
    "blk_per36_5",
    "tov_per36_5",
    "oreb_per36_5",
    "dreb_per36_5",
    "fg3m_per36_5",
    "fga_per36_5",
    "fta_per36_5",
    "fg3_pct_5",
    "ft_pct_5",
    "three_point_bonus_mean_5",
    "pdk_category_bonus_mean_5",
    "rest_days",
    "is_b2b",
    "is_home",
    "opp_pts_allowed_mean_5",
    "opp_plus_minus_mean_5",
    "opp_def_rating_mean_5",
    "opp_pace_mean_5",
    "opp_dreb_rate_mean_5",
    "player_opp_pdk_per_min",
    "player_opp_games",
    # Explicit recent-game lags capture abrupt role/form changes that rolling
    # averages can hide; all are shifted so the target game is never exposed.
    "lag1_pdk",
    "lag2_pdk",
    "lag3_pdk",
    "lag4_pdk",
    "lag5_pdk",
    "pdk_trend_3v10",
    "min_trend_3v5",
    "min_last_vs_prev5",
    "abs_min_last_vs_prev5",
    "min_std_5",
    "min_zero_rate_5",
    "team_changed_from_previous_game",
    "team_history_known",
    "team_games_since_change",
    "lag1_nba_min",
    "lag2_nba_min",
    "lag3_nba_min",
    "prev3_nba_min_mean",
    "lag1_nba_pts",
    "lag2_nba_pts",
    "lag3_nba_pts",
    "prev3_nba_pts_mean",
    "lag1_nba_reb",
    "lag2_nba_reb",
    "lag3_nba_reb",
    "prev3_nba_reb_mean",
    "lag1_nba_ast",
    "lag2_nba_ast",
    "lag3_nba_ast",
    "prev3_nba_ast_mean",
    "history_games_before_target",
    "nba_history_games_before_target",
]

ROLE_CAPACITY = {"G": 96.0, "F": 96.0, "C": 48.0}


def _normalize_lineup_group(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    group = str(value).strip().upper()
    return "" if group in {"", "NAN", "NONE", "<NA>"} else group


@dataclass
class PlayerForecast:
    player_name: str
    team: str
    role: str
    opponent: str
    cr: float
    expected_pdk: float
    p10: float
    p50: float
    p90: float
    expected_min: float
    p_play: float
    status: str = "Available"


def _model_zoo(settings: Settings) -> dict:
    models = {
        "ridge": Ridge(alpha=3.0, random_state=settings.random_state),
        "rf": RandomForestRegressor(
            n_estimators=200, max_depth=6, random_state=settings.random_state, n_jobs=-1
        ),
        "gbr": GradientBoostingRegressor(random_state=settings.random_state),
    }
    if XGBRegressor is not None:
        models["xgb"] = XGBRegressor(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            random_state=settings.random_state,
            n_jobs=-1,
        )
    if LGBMRegressor is not None:
        models["lgbm"] = LGBMRegressor(
            n_estimators=300,
            max_depth=-1,
            learning_rate=0.05,
            random_state=settings.random_state,
        )
    return models


def _fit_matrix(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    validate_prematch_features(df, cols)
    X = df[cols].apply(pd.to_numeric, errors="coerce")
    X = X.replace([np.inf, -np.inf], np.nan)
    medians = X.median()
    X = X.fillna(medians).fillna(0.0)
    return X, medians


def _fit_projection_weights(target: pd.Series, components: pd.DataFrame) -> dict[str, float]:
    names = ["minutes", "ensemble", "prior"]
    available = [name for name in names if name in components]
    fallback = {name: float(name == "minutes") for name in names}
    if len(available) != len(names):
        return fallback

    aligned = pd.concat([target.rename("target"), components[names]], axis=1).dropna()
    if len(aligned) < 40:
        return fallback
    matrix = aligned[names].to_numpy(dtype=float)
    outcomes = aligned["target"].to_numpy(dtype=float)
    result = minimize(
        lambda weights: float(np.mean((matrix @ weights - outcomes) ** 2)),
        x0=np.full(len(names), 1.0 / len(names)),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * len(names),
        constraints=[{"type": "eq", "fun": lambda weights: float(weights.sum() - 1.0)}],
        options={"maxiter": 500, "ftol": 1e-9},
    )
    if not result.success or not np.isfinite(result.x).all():
        return fallback
    fitted = np.clip(result.x, 0.0, 1.0)
    fitted /= fitted.sum()
    return dict(zip(names, fitted.tolist()))


def _apply_projection_weights(
    components: pd.DataFrame, weights: dict[str, float]
) -> pd.Series:
    weight_series = pd.Series(weights)
    weighted_sum = components.fillna(0.0).mul(weight_series).sum(axis=1)
    available_weight = components.notna().mul(weight_series).sum(axis=1)
    return weighted_sum.div(available_weight.replace(0.0, np.nan))


_RESIDUAL_SCORE_BINS = [-np.inf, 5.0, 10.0, 15.0, 20.0, 25.0, np.inf]
_RESIDUAL_SCORE_LABELS = ["<5", "5-10", "10-15", "15-20", "20-25", "25+"]


def _fit_residual_quantiles_by_prediction_band(
    predictions: pd.Series, targets: pd.Series, *, shrinkage_rows: float = 1000.0
) -> dict:
    """Fit past-only OOF residual quantiles conditioned on forecast score band."""
    aligned = pd.concat(
        [pd.to_numeric(predictions, errors="coerce").rename("prediction"),
         pd.to_numeric(targets, errors="coerce").rename("target")], axis=1
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if aligned.empty:
        return {}
    aligned["residual"] = aligned["target"] - aligned["prediction"]
    global_q = np.quantile(aligned["residual"].to_numpy(float), [0.10, 0.50, 0.90])
    aligned["score_band"] = pd.cut(
        aligned["prediction"], bins=_RESIDUAL_SCORE_BINS,
        labels=_RESIDUAL_SCORE_LABELS, right=False,
    )
    bands = {}
    for label in _RESIDUAL_SCORE_LABELS:
        residuals = aligned.loc[aligned["score_band"].astype(str).eq(label), "residual"].to_numpy(float)
        n = len(residuals)
        if n < 100:
            quantiles = global_q
        else:
            alpha = n / (n + float(shrinkage_rows))
            quantiles = alpha * np.quantile(residuals, [0.10, 0.50, 0.90]) + (1.0 - alpha) * global_q
        bands[label] = {"q10": float(quantiles[0]), "q50": float(quantiles[1]), "q90": float(quantiles[2]), "n": int(n)}
    return {
        "shrinkage_rows": float(shrinkage_rows), "n": int(len(aligned)),
        "global": {"q10": float(global_q[0]), "q50": float(global_q[1]), "q90": float(global_q[2])},
        "bands": bands,
    }


def _residual_quantiles_for_predictions(models: dict, predictions: pd.Series) -> dict[str, pd.Series]:
    """Return empirical residual quantiles aligned to each forecast score band."""
    calibration = models.get("_residual_quantiles_by_prediction_band", {})
    global_q = calibration.get("global", {})
    bands = calibration.get("bands", {})
    if not global_q or not bands:
        return {
            "q10": pd.Series(models.get("_residual_q10", np.nan), index=predictions.index, dtype=float),
            "q50": pd.Series(models.get("_residual_q50", np.nan), index=predictions.index, dtype=float),
            "q90": pd.Series(models.get("_residual_q90", np.nan), index=predictions.index, dtype=float),
        }
    score_band = pd.cut(
        pd.to_numeric(predictions, errors="coerce"), bins=calibration.get("bins", _RESIDUAL_SCORE_BINS),
        labels=calibration.get("labels", _RESIDUAL_SCORE_LABELS), right=False,
    ).astype("string")
    result = {}
    for quantile in ("q10", "q50", "q90"):
        lookup = {label: values[quantile] for label, values in bands.items()}
        result[quantile] = score_band.map(lookup).astype(float).fillna(float(global_q[quantile])).reindex(predictions.index)
    return result


MIN_OFFICIAL_PDK_TRAINING_ROWS = 1000


def _resolve_training_target(
    settings: Settings,
    features: pd.DataFrame,
    target_column: str | None = None,
) -> str:
    """Resolve the supervised label without mixing official and proxy scores."""
    if target_column is not None:
        return target_column
    mode = getattr(settings, "training_target", "auto")
    if mode == "target_pdk":
        return "target_pdk"
    if mode == "target_pdk_official":
        return "target_pdk_official"
    if mode != "auto":
        raise ValueError(
            "training_target must be one of: auto, target_pdk, target_pdk_official."
        )
    if "target_pdk_official" in features:
        official = pd.to_numeric(features["target_pdk_official"], errors="coerce")
        official = official.replace([np.inf, -np.inf], np.nan)
        count = int(official.notna().sum())
        if count >= MIN_OFFICIAL_PDK_TRAINING_ROWS:
            print(
                f"Training target: target_pdk_official ({count:,} finite official labels)."
            )
            return "target_pdk_official"
        print(
            "Training target: target_pdk "
            f"(official labels available: {count:,}; requires "
            f"{MIN_OFFICIAL_PDK_TRAINING_ROWS:,} for auto-selection)."
        )
    else:
        print("Training target: target_pdk (no official PDK labels in feature matrix).")
    return "target_pdk"


def train_models(
    settings: Settings,
    features: pd.DataFrame,
    target_column: str | None = None,
    sample_weight: pd.Series | None = None,
) -> tuple[dict, pd.Series]:
    target_column = _resolve_training_target(settings, features, target_column)
    if features.empty or target_column not in features:
        raise ValueError(
            f"Training features are empty or lack {target_column}. Check the NBA game-log "
            "cache and the selected feature season."
        )
    df = features.copy()
    df[target_column] = pd.to_numeric(df[target_column], errors="coerce")
    sample_weights = None
    if sample_weight is not None:
        sample_weights = pd.to_numeric(sample_weight.reindex(df.index), errors="coerce")
        if sample_weights.notna().any() and (sample_weights.dropna() <= 0).any():
            raise ValueError("sample_weight values must be positive when provided.")
    finite_target = np.isfinite(df[target_column].to_numpy(dtype=float, na_value=np.nan))
    df = df.loc[finite_target].copy()
    if sample_weights is not None:
        sample_weights = sample_weights.loc[df.index].fillna(1.0).astype(float)
    if df.empty:
        raise ValueError(f"No finite historical {target_column} values are available for model training.")

    # Ignore features that are absent or entirely missing in the training slice.
    # An all-missing feature otherwise becomes a synthetic constant zero column.
    cols = [c for c in FEATURE_COLS if c in df.columns]
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    cols = [
        c for c in cols
        if np.isfinite(df[c].to_numpy(dtype=float, na_value=np.nan)).any()
    ]
    if not cols:
        raise ValueError(
            "No usable model features are available: expected at least one finite "
            "column from FEATURE_COLS. Check feature generation and historical data."
        )
    target_pdk = pd.to_numeric(df[target_column], errors="coerce")
    baseline = pd.to_numeric(
        df.get("expected_pdk_minutes_model", pd.Series(0.0, index=df.index)),
        errors="coerce",
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(lower=0.0)
    y = target_pdk - baseline
    y_min = pd.to_numeric(
        df["target_min"] if "target_min" in df else pd.Series(np.nan, index=df.index),
        errors="coerce",
    )
    X, medians = _fit_matrix(df, cols)
    minutes_model = None
    minutes_valid = np.isfinite(y_min.to_numpy(dtype=float, na_value=np.nan))
    if int(minutes_valid.sum()) >= 200:
        minutes_model = HistGradientBoostingRegressor(
            max_iter=180,
            learning_rate=0.06,
            max_leaf_nodes=31,
            l2_regularization=5.0,
            min_samples_leaf=40,
            random_state=settings.random_state,
        )
        minutes_model.fit(X.loc[minutes_valid], y_min.loc[minutes_valid].clip(0.0, 60.0))

    zoo = _model_zoo(settings)
    weights = {name: 1.0 / len(zoo) for name in zoo}
    validation_output = pd.Series(np.nan, index=df.index, dtype=float)
    validation_fold = pd.Series(-1, index=df.index, dtype=int)
    if "GAME_DATE" in df.columns and len(df) >= 200:
        dates = pd.to_datetime(df["GAME_DATE"])
        unique_dates = np.sort(dates.dropna().unique())
        first_validation_date = int(len(unique_dates) * 0.4)
        validation_date_folds = np.array_split(unique_dates[first_validation_date:], 3)
        oof_predictions = {
            name: pd.Series(np.nan, index=df.index, dtype=float) for name in zoo
        }
        # Tune Ridge regularization on the earliest temporal fold only. That
        # fold is deliberately excluded from OOF ensemble-weight/calibration
        # fitting below, so its labels cannot both choose alpha and score it.
        ridge_tuning_fold_index = None
        selected_ridge_alpha = float(zoo["ridge"].alpha)
        if validation_date_folds and len(validation_date_folds[0]):
            tuning_dates = validation_date_folds[0]
            tuning_train = dates < tuning_dates[0]
            tuning_valid = dates.isin(tuning_dates)
            if int(tuning_train.sum()) >= 80 and int(tuning_valid.sum()) >= 40:
                tuning_X, tuning_medians = _fit_matrix(df.loc[tuning_train], cols)
                tuning_val_X = df.loc[tuning_valid, cols].apply(pd.to_numeric, errors="coerce")
                tuning_val_X = tuning_val_X.replace([np.inf, -np.inf], np.nan)
                tuning_val_X = tuning_val_X.fillna(tuning_medians).fillna(0.0)
                alpha_scores = {}
                for alpha in (0.3, 1.0, 3.0, 10.0, 30.0):
                    candidate = Ridge(alpha=alpha, random_state=settings.random_state)
                    candidate.fit(
                        tuning_X,
                        y.loc[tuning_train],
                        **({"sample_weight": sample_weights.loc[tuning_train]} if sample_weights is not None else {}),
                    )
                    candidate_prediction = candidate.predict(tuning_val_X)
                    alpha_scores[alpha] = float(
                        mean_absolute_error(y.loc[tuning_valid], candidate_prediction)
                    )
                selected_ridge_alpha = min(alpha_scores, key=alpha_scores.get)
                zoo["ridge"] = Ridge(
                    alpha=selected_ridge_alpha, random_state=settings.random_state
                )
                ridge_tuning_fold_index = 0
        for fold_index, validation_dates in enumerate(validation_date_folds):
            if not len(validation_dates):
                continue
            train_idx = dates < validation_dates[0]
            val_idx = dates.isin(validation_dates)
            if int(train_idx.sum()) < 80 or int(val_idx.sum()) < 40:
                continue
            fold_X, fold_medians = _fit_matrix(df.loc[train_idx], cols)
            val_X = df.loc[val_idx, cols].apply(pd.to_numeric, errors="coerce")
            val_X = val_X.replace([np.inf, -np.inf], np.nan)
            val_X = val_X.fillna(fold_medians).fillna(0.0)
            for name, model in zoo.items():
                if name == "ridge" and fold_index == ridge_tuning_fold_index:
                    # Selection fold is not a valid evaluation sample for its chosen alpha.
                    continue
                model.fit(
                    fold_X,
                    y.loc[train_idx],
                    **({"sample_weight": sample_weights.loc[train_idx]} if sample_weights is not None else {}),
                )
                oof_predictions[name].loc[val_idx] = model.predict(val_X)
            validation_fold.loc[val_idx] = fold_index

        valid_idx = pd.Index(df.index)
        for predictions in oof_predictions.values():
            valid_idx = valid_idx.intersection(predictions.index[predictions.notna()])
        if len(valid_idx):
            mae = {
                name: float(mean_absolute_error(y.loc[valid_idx], predictions.loc[valid_idx]))
                for name, predictions in oof_predictions.items()
            }
            inv = {name: 1.0 / max(err, 1e-3) for name, err in mae.items()}
            total = sum(inv.values())
            weights = {name: inv[name] / total for name in zoo}
        for fold_index in sorted(validation_fold[validation_fold >= 0].unique()):
            val_idx = validation_fold.eq(fold_index)
            prior_idx = validation_fold.lt(fold_index)
            prior_idx &= pd.concat(oof_predictions, axis=1).notna().all(axis=1)
            if int(prior_idx.sum()) >= 40:
                fold_mae = {
                    name: float(
                        mean_absolute_error(y.loc[prior_idx], predictions.loc[prior_idx])
                    )
                    for name, predictions in oof_predictions.items()
                }
                inverse = {
                    name: 1.0 / max(error, 1e-3)
                    for name, error in fold_mae.items()
                }
                fold_total = sum(inverse.values())
                fold_weights = {
                    name: inverse[name] / fold_total for name in zoo
                }
            else:
                fold_weights = {name: 1.0 / len(zoo) for name in zoo}
            fold_prediction = sum(
                fold_weights[name] * oof_predictions[name].loc[val_idx]
                for name in zoo
            )
            validation_output.loc[val_idx] = fold_prediction + baseline.loc[val_idx]

    projection_components = pd.DataFrame(
        {
            "minutes": baseline,
            "ensemble": validation_output,
            "prior": pd.to_numeric(
                df.get("pdk_season_mean", pd.Series(np.nan, index=df.index)),
                errors="coerce",
            ).replace([np.inf, -np.inf], np.nan),
        },
        index=df.index,
    )
    projection_weights = _fit_projection_weights(target_pdk, projection_components)
    cross_fitted_residuals: list[pd.Series] = []
    cross_fitted_validation_output = pd.Series(np.nan, index=df.index, dtype=float)
    for fold_index in sorted(validation_fold[validation_fold >= 0].unique()):
        val_idx = validation_fold.eq(fold_index)
        # The earliest fold tuned Ridge alpha and is deliberately excluded from
        # calibration. Later folds may only use earlier *valid OOF predictions*;
        # training rows and folds with missing model predictions are never used
        # to fit the fold-specific projection weights.
        if fold_index == ridge_tuning_fold_index:
            continue
        prior_idx = (
            validation_fold.lt(fold_index)
            & validation_output.notna()
            & target_pdk.notna()
        )
        if int(prior_idx.sum()) >= 40:
            fold_projection_weights = _fit_projection_weights(
                target_pdk.loc[prior_idx], projection_components.loc[prior_idx]
            )
        else:
            # Predeclared fallback when no prior OOF slate exists: use the
            # cross-fitted ensemble directly rather than the zero minutes prior.
            fold_projection_weights = {"minutes": 0.0, "ensemble": 1.0, "prior": 0.0}
        fold_blend = _apply_projection_weights(
            projection_components.loc[val_idx], fold_projection_weights
        )
        cross_fitted_validation_output.loc[val_idx] = fold_blend
        fold_residuals = target_pdk.loc[val_idx] - fold_blend
        cross_fitted_residuals.append(fold_residuals.dropna())
    projection_residuals = (
        pd.concat(cross_fitted_residuals).to_numpy(dtype=float)
        if cross_fitted_residuals
        else np.array([], dtype=float)
    )

    fitted: dict = {}
    for name, model in zoo.items():
        model.fit(
            X,
            y,
            **({"sample_weight": sample_weights} if sample_weights is not None else {}),
        )
        fitted[name] = model

    fitted["_feature_cols"] = cols
    fitted["_minutes_shadow_model"] = minutes_model
    fitted["_minutes_shadow_training_rows"] = int(minutes_valid.sum()) if minutes_model is not None else 0
    fitted["_minutes_shadow_target"] = "target_min"
    fitted["_training_target"] = target_column
    fitted["_training_target_source"] = (
        "official_dunkest_pdk" if target_column == "target_pdk_official" else "nba_boxscore_pdk_proxy"
    )
    fitted["_training_rows"] = int(len(df))
    fitted["_sample_weighted_training"] = sample_weights is not None
    fitted["_sample_weight_mean"] = float(sample_weights.mean()) if sample_weights is not None else None
    fitted["_training_rows_before_target_filter"] = int(len(features))
    fitted["_official_labels_available_before_filter"] = int(
        pd.to_numeric(
            features.get("target_pdk_official", pd.Series(np.nan, index=features.index)),
            errors="coerce",
        ).replace([np.inf, -np.inf], np.nan).notna().sum()
    )
    if "GAME_DATE" in df:
        training_dates = pd.to_datetime(df["GAME_DATE"], errors="coerce", utc=True).dropna()
        fitted["_training_date_min_utc"] = training_dates.min().isoformat() if not training_dates.empty else None
        fitted["_training_date_max_utc"] = training_dates.max().isoformat() if not training_dates.empty else None
    fitted["_selected_ridge_alpha"] = selected_ridge_alpha if "selected_ridge_alpha" in locals() else float(zoo["ridge"].alpha)
    fitted["_ridge_tuning_fold_excluded_from_oof"] = ridge_tuning_fold_index if "ridge_tuning_fold_index" in locals() else None
    fitted["_weights"] = weights
    fitted["_projection_weights"] = projection_weights
    fitted["_feature_medians"] = medians
    fitted["_residual_std"] = (
        float(np.std(projection_residuals)) if len(projection_residuals) else 5.0
    )
    fitted["_calibration_samples"] = len(projection_residuals)
    fitted["_residual_q10"] = (
        float(np.quantile(projection_residuals, 0.10)) if len(projection_residuals) else np.nan
    )
    fitted["_residual_q50"] = (
        float(np.quantile(projection_residuals, 0.50)) if len(projection_residuals) else np.nan
    )
    fitted["_residual_q90"] = (
        float(np.quantile(projection_residuals, 0.90)) if len(projection_residuals) else np.nan
    )
    calibration_rows = cross_fitted_validation_output.notna() & target_pdk.notna()
    fitted["_residual_quantiles_by_prediction_band"] = _fit_residual_quantiles_by_prediction_band(
        cross_fitted_validation_output.loc[calibration_rows], target_pdk.loc[calibration_rows]
    )
    interval_diagnostics = []
    if calibration_rows.any():
        validation_frame = df.loc[calibration_rows]
        interval_inputs = pd.DataFrame(
            {
                "expected_pdk": cross_fitted_validation_output.loc[calibration_rows],
                "p_play": 1.0,
                "pdk_std_5": pd.to_numeric(
                    validation_frame.get(
                        "pdk_std_5", pd.Series(np.nan, index=validation_frame.index)
                    ),
                    errors="coerce",
                ),
            },
            index=validation_frame.index,
        )
        interval_quantiles = _residual_quantiles_for_predictions(
            fitted, interval_inputs["expected_pdk"]
        )
        validation_intervals = add_uncertainty_columns(
            interval_inputs,
            residual_std=fitted["_residual_std"],
            residual_q10=interval_quantiles["q10"],
            residual_q50=interval_quantiles["q50"],
            residual_q90=interval_quantiles["q90"],
        )
        interval_diagnostics = interval_coverage_by_cohort(
            target_pdk.loc[calibration_rows],
            validation_intervals,
            history_games=pd.to_numeric(
                validation_frame.get(
                    "n_games", pd.Series(np.nan, index=validation_frame.index)
                ),
                errors="coerce",
            ),
            observed_minutes=pd.to_numeric(
                validation_frame.get(
                    "target_min", pd.Series(np.nan, index=validation_frame.index)
                ),
                errors="coerce",
            ),
        )
    fitted["_interval_diagnostics"] = interval_diagnostics
    fitted["_interval_diagnostic_scope"] = (
        "Cross-fitted point predictions; score-band residual quantiles are fitted from the same OOF calibration sample. "
        "Use as a cohort diagnostic, not independent test-set coverage."
    )
    return fitted, validation_output


def _inference_rows(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return features
    if "is_inference" in features.columns:
        latest = features.loc[features["is_inference"].fillna(False)].copy()
        if not latest.empty:
            return latest
    return features.sort_values("GAME_DATE").groupby("PLAYER_NAME", as_index=False).tail(1)


def _inference_minutes_baseline(models: dict, latest: pd.DataFrame) -> pd.Series:
    """Return the baseline that must be added to the model's prediction scale."""
    if models.get("_prediction_is_absolute", False):
        return pd.Series(0.0, index=latest.index, dtype=float)
    return pd.to_numeric(
        latest.get("expected_pdk_minutes_model", pd.Series(0.0, index=latest.index)),
        errors="coerce",
    ).fillna(0.0)


def _ensemble_predict(models: dict, latest: pd.DataFrame) -> np.ndarray:
    cols: list[str] = models.get("_feature_cols", [])
    if not cols or latest.empty:
        return np.full(len(latest), np.nan)
    X = latest.copy()
    for c in cols:
        if c not in X.columns:
            X[c] = np.nan
    X = X[cols].apply(pd.to_numeric, errors="coerce")
    X = X.replace([np.inf, -np.inf], np.nan)
    medians = models.get("_feature_medians")
    if medians is not None:
        X = X.fillna(medians)
    X = X.fillna(0.0)
    preds = np.zeros(len(X))
    weights = models.get("_weights", {})
    for name, w in weights.items():
        if name.startswith("_") or name not in models:
            continue
        preds += w * models[name].predict(X)
    return preds


def _cr_minutes(cr: float) -> float:
    """Map current Dunkest price to a realistic minutes prior.

    Opening-list credits are a role signal. 4-5 CR is end-of-bench / two-way,
    not a 10-minute rotation player. The old linear rule had a 6-minute floor
    and ignored that cheap rookies almost never play.
    """
    x = float(np.clip(cr, 0.0, 35.0))
    if x <= 4.5:
        return float(np.clip(0.5 + 2.0 * (x - 4.0), 0.5, 1.5))
    if x <= 6.0:
        return float(1.5 + 6.0 * (x - 4.5) / 1.5)
    if x <= 8.0:
        return float(7.5 + 7.5 * (x - 6.0) / 2.0)
    if x <= 11.0:
        return float(15.0 + 12.0 * (x - 8.0) / 3.0)
    return float(np.clip(27.0 + 2.2 * (x - 11.0), 27.0, 38.0))


def _cr_minutes_cap(cr: float, lineup_group: str) -> float:
    """Hard ceiling so last year's role cannot outrun this year's price."""
    group = _normalize_lineup_group(lineup_group)
    prior = _cr_minutes(cr)
    if group == "QUINTETTO":
        return 38.0
    if group == "PANCHINA":
        return float(np.clip(prior * 1.20 + 2.0, 0.0, 22.0))
    return float(np.clip(prior * 1.25 + 2.0, 0.0, 34.0))


def _cap_minutes_to_current_role(emin: float, cr: float, lineup_group: str) -> float:
    return float(np.clip(float(emin), 0.0, _cr_minutes_cap(cr, lineup_group)))


def _lineup_minutes_prior(lineup_group: str, has_history: bool, cr: float | None) -> float | None:
    group = _normalize_lineup_group(lineup_group)
    cr_min = _cr_minutes(cr) if cr is not None and pd.notna(cr) else np.nan
    if group == "QUINTETTO":
        if pd.notna(cr_min) and cr is not None and float(cr) <= 4.5:
            # CR 4 players are usually fringe rotation players. A Lineups
            # quintet tag can refer to one fixture in a multi-game round, so
            # it should not create a ~20 MPG prior by itself. NBA history and
            # the validated rookie prior are blended later as separate evidence.
            starter = 18.0 if has_history else 14.0
            return float(np.clip(0.5 * starter + 0.5 * cr_min, 0.0, 24.0))
        starter = 32.0 if has_history else 28.0
        if pd.notna(cr_min):
            # A lineup tag is useful role evidence, but it must not erase the
            # salary signal. The former 22-minute floor made a CR 4 rookie
            # project at ~26 minutes solely because it was tagged as a starter.
            return float(np.clip(0.65 * starter + 0.35 * cr_min, 0.0, 36.0))
        return starter
    if group == "PANCHINA":
        bench = 16.0 if has_history else 8.0
        if pd.notna(cr_min):
            # Price decides whether this is a sixth man or a DNP. A listed
            # bench tag alone must not manufacture rotation minutes.
            return float(np.clip(0.25 * bench + 0.75 * cr_min, 0.0, 20.0))
        return bench
    return None


def _sample_confidence(games: object, prior_strength: float = 12.0) -> float:
    count = pd.to_numeric(games, errors="coerce")
    if pd.isna(count):
        # Preserve behavior for callers without sample-count metadata. The
        # feature builder supplies n_games for production predictions.
        return 1.0
    return float(np.clip(count, 0.0, None) / (np.clip(count, 0.0, None) + prior_strength))


def _base_minutes(hist: pd.Series | None, d: pd.Series) -> tuple[float, bool]:
    recent = pd.to_numeric(hist.get("e_min_5"), errors="coerce") if hist is not None else np.nan
    season = pd.to_numeric(hist.get("e_min_season"), errors="coerce") if hist is not None else np.nan
    has_history = pd.notna(recent) or pd.notna(season)
    if pd.notna(recent) and pd.notna(season):
        emin = float(0.65 * recent + 0.35 * season)
    elif pd.notna(recent):
        emin = float(recent)
    elif pd.notna(season):
        emin = float(season)
    else:
        emin = np.nan

    cr = pd.to_numeric(d.get("cr"), errors="coerce")
    lineup_group = _normalize_lineup_group(d.get("lineup_group", ""))
    role_prior = _lineup_minutes_prior(lineup_group, has_history, float(cr) if pd.notna(cr) else None)
    cr_min = _cr_minutes(cr) if pd.notna(cr) else np.nan

    if not has_history:
        if role_prior is not None:
            return _cap_minutes_to_current_role(role_prior, float(cr) if pd.notna(cr) else 4.0, lineup_group), False
        if pd.notna(cr_min):
            return _cap_minutes_to_current_role(cr_min, float(cr), lineup_group), False
        return 1.0, False

    confidence = _sample_confidence(hist.get("n_games")) if hist is not None else 0.0
    if role_prior is not None:
        # Current lineup designation is stronger evidence than last season's
        # role. Let historical minutes add evidence without overriding it.
        history_weight = 0.35 * confidence
        emin = history_weight * emin + (1.0 - history_weight) * role_prior
    elif pd.notna(cr_min):
        # Current Dunkest credit is the timely role signal. Full-season
        # history must not keep a now-cheap bench player at 25 minutes.
        emin = confidence * emin + (1.0 - confidence) * cr_min
    cr_value = float(cr) if pd.notna(cr) else 4.0
    return _cap_minutes_to_current_role(float(np.clip(emin, 0.0, 42.0)), cr_value, lineup_group), True


def _production_rate(hist: pd.Series | None) -> float:
    rate = pd.to_numeric(hist.get("pdk_per_min_season"), errors="coerce") if hist is not None else np.nan
    if pd.isna(rate) or float(rate) <= 0:
        return np.nan
    return float(rate)


def _blend_current_season_rate(
    prior_rate: object,
    current_rate: object,
    current_games: object,
    prior_strength: float = 12.0,
) -> tuple[float, float]:
    """Shrink current-season production toward a prior-season/market baseline.

    Prior strength is calibrated on historical, past-only player-game observations.
    With one current-season game the new evidence has 1/13 weight; sustained
    production gradually dominates as the current-season sample grows.
    """
    prior = pd.to_numeric(prior_rate, errors="coerce")
    current = pd.to_numeric(current_rate, errors="coerce")
    games = pd.to_numeric(current_games, errors="coerce")
    if pd.isna(current) or float(current) < 0 or pd.isna(games) or float(games) <= 0:
        return (float(prior) if pd.notna(prior) and float(prior) >= 0 else np.nan, 0.0)
    weight = float(np.clip(games, 0.0, None) / (np.clip(games, 0.0, None) + prior_strength))
    if pd.isna(prior) or float(prior) < 0:
        # Do not let a tiny current-season sample become an unshrunk forecast.
        # The caller can fall back to player-market or CR/role priors. If no
        # independent prior exists, require a full prior-strength sample before
        # trusting the season-only estimate; this avoids a one-game spike without
        # suppressing a player who builds a substantial sample during the season.
        if float(games) >= prior_strength:
            return float(current), 1.0
        return np.nan, 0.0
    return float((1.0 - weight) * float(prior) + weight * float(current)), weight


def _market_reference_slice(
    history: pd.DataFrame | None, cr: float, role: str
) -> pd.DataFrame:
    if history is None or history.empty or not 4.0 <= cr <= 35.0:
        return pd.DataFrame()
    required = {"cr", "pdk", "min"}
    if not required.issubset(history.columns):
        return pd.DataFrame()
    reference = history.copy()
    reference["cr"] = pd.to_numeric(reference["cr"], errors="coerce")
    reference["pdk"] = pd.to_numeric(reference["pdk"], errors="coerce")
    reference["min"] = pd.to_numeric(reference["min"], errors="coerce")
    reference = reference.loc[
        reference["cr"].between(4.0, 25.0)
        & reference["pdk"].gt(0.0)
        & reference["min"].gt(0.0)
    ].copy()
    if reference.empty:
        return reference
    role_column = "role" if "role" in reference and reference["role"].notna().any() else "position"
    if role_column in reference:
        reference["_role"] = reference[role_column].map(normalize_position)
        same_role = reference.loc[reference["_role"].eq(role)]
        if len(same_role) >= 5:
            reference = same_role
    reference["_distance"] = (reference["cr"] - float(cr)).abs()
    local = reference.loc[reference["_distance"].le(2.5)]
    if len(local) < 8:
        local = reference.nsmallest(20, "_distance")
    return local


def _market_implied_rate(history: pd.DataFrame | None, cr: float, role: str) -> float:
    local = _market_reference_slice(history, cr, role)
    if local.empty:
        return np.nan
    weights = np.exp(-0.5 * (local["_distance"] / 1.5) ** 2)
    rates = local["pdk"] / local["min"]
    return float(np.average(rates, weights=weights))


def _market_minutes_prior(history: pd.DataFrame | None, cr: float, role: str) -> float:
    local = _market_reference_slice(history, cr, role)
    if local.empty:
        return np.nan
    weights = np.exp(-0.5 * (local["_distance"] / 1.5) ** 2)
    return float(np.average(local["min"], weights=weights))


def _player_market_prior(
    history: pd.DataFrame | None, name: str
) -> tuple[float, float, float]:
    """Return prior-season rate, minutes, and games played for this player."""
    if history is None or history.empty or "player_name" not in history.columns:
        return np.nan, np.nan, np.nan
    required = {"pdk", "min"}
    if not required.issubset(history.columns):
        return np.nan, np.nan, np.nan
    prior = history.copy()
    prior["_key"] = prior["player_name"].map(player_key)
    prior = prior.loc[prior["_key"].eq(player_key(name))].copy()
    if prior.empty:
        return np.nan, np.nan, np.nan
    for column in ("pdk", "min"):
        prior[column] = pd.to_numeric(prior[column], errors="coerce")
    prior = prior.loc[prior["pdk"].gt(0) & prior["min"].gt(0)]
    if prior.empty:
        return np.nan, np.nan, np.nan
    row = prior.iloc[-1]
    games = pd.to_numeric(row.get("gp"), errors="coerce")
    return float(row["pdk"] / row["min"]), float(row["min"]), float(games) if pd.notna(games) else np.nan


def _expanding_week_splits(
    sample: pd.DataFrame, min_train_rows: int = 40
) -> list[tuple[float, pd.Series, pd.Series]]:
    """Yield gameweek holdouts trained only from preceding weeks."""
    weeks = sorted(pd.to_numeric(sample["gameweek"], errors="coerce").dropna().unique())
    splits = []
    numeric_weeks = pd.to_numeric(sample["gameweek"], errors="coerce")
    for week in weeks[1:]:
        train, test = numeric_weeks.lt(week), numeric_weeks.eq(week)
        if int(train.sum()) >= min_train_rows and test.any():
            splits.append((float(week), train, test))
    return splits


def allocate_positional_minutes(out: pd.DataFrame) -> pd.DataFrame:
    """Scale projected minutes proportionally when a team's role budget is exceeded.

    A greedy allocation can assign zero minutes to every player below the first
    few entries even when they have positive projected opportunity. Proportional
    scaling preserves relative requests while enforcing the total role capacity.
    Starter/bench priors and per-player caps are applied before this function.
    """
    out = out.copy()
    out["competition_scale"] = 1.0
    playable = pd.to_numeric(out["p_play"], errors="coerce").fillna(0.0) > 0
    for _, group in out.loc[playable].groupby(["team", "role"], sort=False):
        if group.empty:
            continue
        cap = ROLE_CAPACITY.get(str(group["role"].iloc[0]), 96.0)
        requested = (
            pd.to_numeric(group["expected_min"], errors="coerce")
            .fillna(0.0)
            .clip(lower=0.0)
        )
        total_requested = float(requested.sum())
        if total_requested > cap and total_requested > 0.0:
            allocated = requested * (float(cap) / total_requested)
            # Correct floating-point roundoff so the sum never exceeds capacity.
            excess = float(allocated.sum() - cap)
            if excess > 0.0:
                largest_idx = allocated.idxmax()
                allocated.loc[largest_idx] = max(
                    0.0, float(allocated.loc[largest_idx]) - excess
                )
        else:
            allocated = requested
        row_scales = pd.Series(1.0, index=group.index, dtype=float)
        positive = requested.gt(0.0)
        row_scales.loc[positive] = (
            allocated.loc[positive] / requested.loc[positive]
        ).clip(0.0, 1.0)
        out.loc[group.index, "expected_min"] = allocated
        out.loc[group.index, "competition_scale"] = row_scales
    out.loc[~playable, "expected_min"] = 0.0
    return out


def _apply_current_role_competition(out: pd.DataFrame) -> pd.DataFrame:
    """Cap stale minutes using current roster depth and projected opportunity."""
    out = out.copy()
    out["role_competition_count"] = 0
    out["role_depth_rank"] = np.nan
    out["role_minutes_cap"] = np.nan
    if not {"team", "role", "cr", "expected_min", "p_play"}.issubset(out.columns):
        return out

    caps_by_depth = [36.0, 30.0, 24.0, 18.0, 13.0, 9.0, 6.0, 4.0]
    team_codes = out["team"].fillna("").astype(str).str.strip()
    eligible = out["p_play"].gt(0) & team_codes.ne("")
    for _, group in out.loc[eligible].groupby(["team", "role"], dropna=False):
        lineup = group.get("lineup_group", pd.Series("", index=group.index)).map(
            _normalize_lineup_group
        )
        starter = lineup.eq("QUINTETTO")
        bench = lineup.eq("PANCHINA")
        ranked = pd.DataFrame(
            {
                "starter": starter.astype(int),
                "bench": bench.astype(int),
                "expected_min": pd.to_numeric(group["expected_min"], errors="coerce").fillna(0.0),
                # Credit is a secondary signal for depth-chart competition,
                # not a standalone reason to inflate a player's minutes.
                "cr": pd.to_numeric(group["cr"], errors="coerce").fillna(0.0),
                "name": group["player_name"].astype(str),
            },
            index=group.index,
        ).sort_values(
            ["starter", "bench", "expected_min", "cr", "name"],
            ascending=[False, False, False, False, True],
        )
        count = len(ranked)
        for rank, idx in enumerate(ranked.index, start=1):
            if starter.loc[idx]:
                cap = 38.0
            elif bench.loc[idx]:
                # A listed bench player can be a sixth man, but a prior role
                # should not carry a 30+ minute projection into a new rotation.
                cap = min(22.0, caps_by_depth[min(rank - 1, len(caps_by_depth) - 1)])
            else:
                cap = caps_by_depth[min(rank - 1, len(caps_by_depth) - 1)]
            out.loc[idx, "role_competition_count"] = count
            out.loc[idx, "role_depth_rank"] = rank
            out.loc[idx, "role_minutes_cap"] = cap
            current_minutes = pd.to_numeric(out.at[idx, "expected_min"], errors="coerce")
            current_minutes = float(current_minutes) if pd.notna(current_minutes) else 0.0
            out.loc[idx, "expected_min"] = min(current_minutes, cap)
    return out


def _match_injury_record(player_name: object, team: object, records: list[dict]) -> dict | None:
    """Resolve full or abbreviated injury names without cross-team false matches."""
    name = "" if player_name is None or pd.isna(player_name) else str(player_name).strip()
    key = player_key(name)
    team_key = "" if team is None or pd.isna(team) else str(team).strip().upper()
    if not key:
        return None

    exact = [record for record in records if record["key"] == key]
    if team_key:
        exact_team = [record for record in exact if record["team"] == team_key]
        if exact_team:
            exact = exact_team
    if exact:
        # Duplicate sources can record the same identity in both abbreviated
        # and canonical form. Use the most conservative availability status.
        return min(exact, key=lambda record: record["p_play"])

    surname = player_surname(name)
    tokens = key.split()
    if not surname or not tokens:
        return None
    candidates = [record for record in records if record["surname"] == surname]
    if team_key:
        same_team = [record for record in candidates if record["team"] == team_key]
        if same_team:
            candidates = same_team
        else:
            return None
    narrowed = []
    for record in candidates:
        injury_tokens = record["key"].split()
        if not injury_tokens:
            continue
        # An initial+surname report (e.g. "C. White") must match the player's
        # first-name initial. If both full names are available, require exact.
        if len(injury_tokens[0]) == 1:
            if tokens[0].startswith(injury_tokens[0]):
                narrowed.append(record)
        elif len(tokens[0]) == 1:
            if injury_tokens[0].startswith(tokens[0]):
                narrowed.append(record)
        # When both first names are available and differ, surname uniqueness
        # alone is not enough evidence to mark a player unavailable. Full-name
        # reports must match exactly; only true first-initial reports use the
        # abbreviated-name branches above.
    # Repeated rows for one canonical player may be merged; never guess between
    # two different players sharing a surname and initial.
    identities = {record["key"] for record in narrowed}
    if len(identities) == 1 and narrowed:
        return min(narrowed, key=lambda record: record["p_play"])
    return None


def _sanitize_lineup_annotations(dunkest_df: pd.DataFrame) -> pd.DataFrame:
    """Preserve fixture-derived rotation labels after per-turn annotation selection.

    A team can appear in multiple NBA fixtures during one Dunkest gameweek, so
    counting starters team-wide is not a valid consistency check. The browser
    parser caps each visible lineup column at five starters and the opener
    selects the annotation for the player's verified turn. Do not erase those
    valid cross-fixture labels based on a gameweek-wide count.
    """
    return dunkest_df.copy()


def predict_players(
    settings: Settings,
    models: dict,
    features: pd.DataFrame,
    dunkest_df: pd.DataFrame,
    injuries: pd.DataFrame | None = None,
    market_value_history: pd.DataFrame | None = None,
    plusvalenza_history: pd.DataFrame | None = None,
    college_rookie_priors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    latest = _inference_rows(features)
    cols: list[str] = models.get("_feature_cols", [])
    for c in cols:
        if c not in latest.columns:
            latest[c] = np.nan
    minute_model = models.get("_minutes_shadow_model")
    if not latest.empty and minute_model is not None:
        minute_X = latest[cols].apply(pd.to_numeric, errors="coerce")
        minute_X = minute_X.replace([np.inf, -np.inf], np.nan)
        minute_X = minute_X.fillna(models.get("_feature_medians", pd.Series(dtype=float))).fillna(0.0)
        latest["expected_min_model_shadow"] = np.clip(minute_model.predict(minute_X), 0.0, 48.0)
    else:
        latest["expected_min_model_shadow"] = np.nan
    if not latest.empty:
        latest["_key"] = latest["PLAYER_NAME"].map(player_key)
        residual = _ensemble_predict(models, latest)
        # The certified multi-season adapter predicts absolute PDK, while the
        # legacy trainer predicts residuals around the minutes baseline.
        baseline = _inference_minutes_baseline(models, latest)
        latest["ensemble_pdk"] = (baseline + residual).clip(lower=0.0)
        hist_lookup = latest.drop_duplicates("_key", keep="last").set_index("_key")
    else:
        hist_lookup = pd.DataFrame()

    injury_records: list[dict] = []
    if injuries is not None and not injuries.empty and "player_name" in injuries.columns:
        for _, inj in injuries.iterrows():
            injury_name = str(inj.get("player_name", "")).strip()
            injury_key = player_key(injury_name)
            if not injury_key:
                continue
            injury_records.append({
                "key": injury_key,
                "surname": player_surname(injury_name),
                "team": str(inj.get("team", "")).strip().upper(),
                "p_play": play_probability(inj.get("status", ""), inj.get("lineup_group", "")),
                "status": str(inj.get("status", "")).strip(),
            })

    rookie_lookup: dict[str, pd.Series] = {}
    if college_rookie_priors is not None and not college_rookie_priors.empty:
        rookie_rows = college_rookie_priors.copy()
        if "player_key" not in rookie_rows and "player_name" in rookie_rows:
            rookie_rows["player_key"] = rookie_rows["player_name"].map(player_key)
        if {"player_key", "college_projected_pdk_per_min", "nba_rookie_rate_baseline"}.issubset(rookie_rows.columns):
            rookie_lookup = rookie_rows.drop_duplicates("player_key", keep="last").set_index(
                "player_key"
            ).to_dict("index")

    dk = _sanitize_lineup_annotations(dunkest_df)
    dk = dk[dk["cr"].between(settings.min_cr, settings.max_cr)]
    historical_model_weight = float(getattr(settings, "historical_pdk_blend_weight", 0.20))
    historical_forecasts = pd.DataFrame()
    if historical_model_weight > 0.0 and not dk.empty and not latest.empty:
        try:
            historical_forecasts = predict_historical_pdk(
                settings.data_path,
                latest,
                dk,
                fallback_target_date=getattr(settings, "nba_season_start", None),
            )
        except Exception as exc:
            warnings.warn(
                f"Historical PDK model unavailable; keeping the primary forecast unchanged: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
    historical_lookup: dict[str, dict] = {}
    if not historical_forecasts.empty:
        historical_forecasts = historical_forecasts.copy()
        historical_forecasts["_key"] = historical_forecasts["player_name"].map(player_key)
        historical_lookup = historical_forecasts.drop_duplicates("_key", keep="last").set_index("_key").to_dict("index")
    rows: list[dict] = []
    for _, d in dk.iterrows():
        name = d["player_name"]
        key = player_key(name)
        hist = hist_lookup.loc[key] if key in hist_lookup.index else None
        if isinstance(hist, pd.DataFrame):
            hist = hist.iloc[-1]
        prior_pdk = pd.to_numeric(d.get("prior_pdk", d.get("pdk")), errors="coerce")
        n_games = pd.to_numeric(hist.get("n_games"), errors="coerce") if hist is not None else np.nan
        cr = float(d.get("cr", settings.min_cr))
        role = normalize_position(
            d["position"]
            if pd.isna(d.get("role"))
            else d.get("role", d.get("position", "F"))
        )
        emin, has_history = _base_minutes(hist, d)
        lineup_group = _normalize_lineup_group(d.get("lineup_group", ""))
        if lineup_group == "QUINTETTO":
            minute_basis = "Tag quintetto + storico" if has_history else "Tag quintetto"
        elif lineup_group == "PANCHINA":
            minute_basis = "Tag panchina + storico" if has_history else "Tag panchina"
        elif has_history:
            minute_basis = "Storico recente/stagione"
        else:
            minute_basis = "Prior CR/ruolo"
        p_play = play_probability(d.get("status", ""), lineup_group)
        injury_record = _match_injury_record(name, d.get("team", ""), injury_records)
        if injury_record is not None:
            p_play = min(p_play, float(injury_record["p_play"]))
        status = "Out" if p_play <= 0 else "Available"
        if 0 < p_play < 1:
            raw_status = d.get("status", "")
            status_source = "" if raw_status is None or pd.isna(raw_status) else str(raw_status).strip()
            if injury_record is not None and float(injury_record["p_play"]) <= play_probability(
                raw_status, lineup_group
            ):
                injury_status = injury_record.get("status", "")
                if injury_status is not None and pd.notna(injury_status) and str(injury_status).strip():
                    status_source = str(injury_status).strip()
            status = status_source or "Questionable"
            status = f"{status} ({p_play:.0%})"

        ensemble = pd.to_numeric(hist.get("ensemble_pdk"), errors="coerce") if hist is not None else np.nan
        historical_row = historical_lookup.get(key, {})
        historical_rf_pdk = pd.to_numeric(historical_row.get("historical_rf_pdk"), errors="coerce")
        historical_rf_pdk_games_value = pd.to_numeric(
            historical_row.get("historical_rf_pdk_games", 0), errors="coerce"
        )
        historical_rf_nba_games_value = pd.to_numeric(
            historical_row.get("historical_rf_nba_games", 0), errors="coerce"
        )
        historical_rf_pdk_games = int(historical_rf_pdk_games_value) if pd.notna(historical_rf_pdk_games_value) else 0
        historical_rf_nba_games = int(historical_rf_nba_games_value) if pd.notna(historical_rf_nba_games_value) else 0
        historical_rf_eligible = bool(
            pd.notna(historical_rf_pdk)
            and (historical_rf_pdk_games >= 3 or historical_rf_nba_games >= 20)
        )
        implied_min = pd.to_numeric(hist.get("e_min_5"), errors="coerce") if hist is not None else np.nan
        if pd.isna(implied_min) or implied_min <= 1:
            implied_min = pd.to_numeric(hist.get("e_min_season"), errors="coerce") if hist is not None else emin
        opponent_value = hist.get("OPPONENT", "") if hist is not None else ""
        opponent = "" if pd.isna(opponent_value) else str(opponent_value).strip().upper()
        historical_rate = _production_rate(hist)
        rate = historical_rate
        projection_source = "player_history" if pd.notna(rate) else "no_history"
        sample_games = float(n_games) if pd.notna(n_games) else 0.0
        sample_confidence = _sample_confidence(n_games) if pd.notna(n_games) else 0.0
        peer_rate = _market_implied_rate(market_value_history, cr, role)
        peer_minutes = _market_minutes_prior(market_value_history, cr, role)
        current_season_rate = (
            pd.to_numeric(hist.get("pdk_per_min_current_season"), errors="coerce")
            if hist is not None else np.nan
        )
        prior_season_rate = (
            pd.to_numeric(hist.get("pdk_per_min_prior_seasons"), errors="coerce")
            if hist is not None else np.nan
        )
        current_season_games = (
            pd.to_numeric(hist.get("current_season_games"), errors="coerce")
            if hist is not None else np.nan
        )
        # Prefer a genuine prior-season rate, then a market/role prior. Never
        # let one hot game replace a multi-season baseline at full strength.
        season_baseline = (
            prior_season_rate
            if pd.notna(prior_season_rate) and float(prior_season_rate) > 0
            else peer_rate
        )
        season_adjusted_rate, current_season_weight = _blend_current_season_rate(
            season_baseline, current_season_rate, current_season_games
        )
        season_adjusted = pd.notna(current_season_rate) and pd.notna(current_season_games) and current_season_games > 0
        if season_adjusted and pd.notna(season_adjusted_rate):
            rate = season_adjusted_rate
            projection_source = "current_season_shrunk"
        elif season_adjusted and pd.isna(season_baseline):
            # The feature-level season mean may itself be this same tiny current
            # sample. Clear it and route through independent market/role priors.
            rate = np.nan
            projection_source = "current_season_without_baseline"
        elif pd.notna(prior_season_rate) and float(prior_season_rate) > 0:
            rate = float(prior_season_rate)
            projection_source = "prior_seasons"
        if pd.notna(rate) and pd.notna(peer_rate) and pd.notna(n_games) and not season_adjusted:
            rate = sample_confidence * rate + (1.0 - sample_confidence) * peer_rate
            if sample_confidence < 0.99:
                projection_source = "player_history_shrunk"
        if pd.isna(rate):
            player_rate, player_minutes, market_games = _player_market_prior(market_value_history, name)
            if pd.notna(player_rate):
                market_confidence = _sample_confidence(market_games)
                rate = (
                    market_confidence * player_rate
                    + (1.0 - market_confidence) * peer_rate
                    if pd.notna(peer_rate)
                    else player_rate
                )
                projection_source = (
                    "prior_season_player_market"
                    if market_confidence >= 0.99 or pd.isna(peer_rate)
                    else "prior_season_player_market_shrunk"
                )
                if pd.notna(player_minutes):
                    emin = market_confidence * float(np.clip(player_minutes, 0.0, 38.0)) + (
                        1.0 - market_confidence
                    ) * emin
        if pd.isna(rate):
            rate = _market_implied_rate(
                market_value_history,
                cr,
                role,
            )
            if pd.notna(rate):
                projection_source = "cr_market_prior"
                if (
                    pd.notna(peer_minutes)
                    and not has_history
                    and not lineup_group
                    and cr >= 6.5
                ):
                    # Similar-price veterans provide only a weak minute prior
                    # for an unproven player. Cheap peers who happened to play
                    # must not lift a 4 CR rookie into the rotation.
                    emin = 0.80 * emin + 0.20 * float(np.clip(peer_minutes, 0.0, 38.0))
        emin = _cap_minutes_to_current_role(emin, cr, lineup_group)

        college_rate = np.nan
        college_weight = 0.0
        college_minutes = np.nan
        college_minutes_weight = 0.0
        rookie = rookie_lookup.get(key)
        if rookie:
            college_rate = pd.to_numeric(rookie.get("college_projected_pdk_per_min"), errors="coerce")
            baseline_rate = pd.to_numeric(rookie.get("nba_rookie_rate_baseline"), errors="coerce")
            base_weight = pd.to_numeric(
                rookie.get("college_prior_base_weight", COLLEGE_PRIOR_BASE_WEIGHT),
                errors="coerce",
            )
            if pd.isna(base_weight):
                base_weight = 0.0
            college_weight = float(np.clip(base_weight, 0.0, COLLEGE_PRIOR_BASE_WEIGHT)) * (
                COLLEGE_PRIOR_FADE_GAMES
                / (max(sample_games, 0.0) + COLLEGE_PRIOR_FADE_GAMES)
            )
            if pd.notna(college_rate):
                base_rate = rate if pd.notna(rate) else (
                    peer_rate if pd.notna(peer_rate) else baseline_rate
                )
                if pd.notna(base_rate):
                    rate = (1.0 - college_weight) * float(base_rate) + college_weight * float(college_rate)
                    projection_source = (
                        "college_rookie_prior" if not has_history else "player_history+college_prior"
                    )

            college_minutes = pd.to_numeric(
                rookie.get("college_projected_minutes_per_game"), errors="coerce"
            )
            minute_base_weight = pd.to_numeric(
                rookie.get("college_minutes_prior_weight", 0.0), errors="coerce"
            )
            if pd.isna(minute_base_weight):
                minute_base_weight = 0.0
            college_minutes_weight = float(np.clip(minute_base_weight, 0.0, COLLEGE_MINUTES_BASE_WEIGHT)) * (
                COLLEGE_PRIOR_FADE_GAMES
                / (max(sample_games, 0.0) + COLLEGE_PRIOR_FADE_GAMES)
            )
            if pd.notna(college_minutes) and college_minutes_weight > 0.0:
                emin = (
                    (1.0 - college_minutes_weight) * float(emin)
                    + college_minutes_weight * float(college_minutes)
                )
                emin = _cap_minutes_to_current_role(emin, cr, lineup_group)

        rows.append(
            {
                "player_name": name,
                "team": str(d.get("team_code", "")),
                "role": role,
                "opponent": opponent,
                "cr": cr,
                "dunkest_turn": pd.to_numeric(d.get("dunkest_turn"), errors="coerce"),
                "cr_change_last_gameweek": pd.to_numeric(
                    d.get("cr_change_last_gameweek"), errors="coerce"
                ),
                "official_plusvalenza": pd.to_numeric(
                    d.get("official_plusvalenza"), errors="coerce"
                ),
                "historical_rf_pdk": float(historical_rf_pdk) if pd.notna(historical_rf_pdk) else np.nan,
                "historical_rf_pdk_games": historical_rf_pdk_games,
                "historical_rf_nba_games": historical_rf_nba_games,
                "historical_rf_blend_weight": historical_model_weight if historical_rf_eligible else 0.0,
                "expected_pdk": float(ensemble) if pd.notna(ensemble) else (
                    float(prior_pdk) if pd.notna(prior_pdk) else np.nan
                ),
                "ensemble_pdk": float(ensemble) if pd.notna(ensemble) else np.nan,
                "prior_pdk": float(prior_pdk) if pd.notna(prior_pdk) else np.nan,
                "expected_min": emin,
                "expected_min_model_shadow": pd.to_numeric(
                    hist.get("expected_min_model_shadow"), errors="coerce"
                ) if hist is not None else np.nan,
                "requested_min": emin,
                "minutes_projection_basis": minute_basis,
                "implied_min": float(implied_min) if pd.notna(implied_min) else emin,
                "historical_pdk_per_min": historical_rate,
                "pdk_per_min_current_season": float(current_season_rate) if pd.notna(current_season_rate) else np.nan,
                "pdk_per_min_prior_seasons": float(prior_season_rate) if pd.notna(prior_season_rate) else np.nan,
                "current_season_games": float(current_season_games) if pd.notna(current_season_games) else 0.0,
                "current_season_weight": float(current_season_weight),
                "pdk_rate_for_projection": rate,
                "cr_market_pdk_per_min": peer_rate,
                "cr_market_minutes_per_game": peer_minutes,
                "college_projected_pdk_per_min": float(college_rate) if pd.notna(college_rate) else np.nan,
                "college_prior_weight": college_weight,
                "college_cv_mae": pd.to_numeric(rookie.get("college_cv_mae"), errors="coerce") if rookie else np.nan,
                "college_baseline_cv_mae": pd.to_numeric(rookie.get("college_baseline_cv_mae"), errors="coerce") if rookie else np.nan,
                "college_target_source": str(rookie.get("college_target_source", "")) if rookie else "",
                "college_projected_minutes_per_game": float(college_minutes) if pd.notna(college_minutes) else np.nan,
                "college_minutes_prior_weight": college_minutes_weight,
                "college_minutes_cv_mae": pd.to_numeric(rookie.get("college_minutes_cv_mae"), errors="coerce") if rookie else np.nan,
                "college_minutes_baseline_cv_mae": pd.to_numeric(rookie.get("college_minutes_baseline_cv_mae"), errors="coerce") if rookie else np.nan,
                "projection_source": projection_source,
                "has_history": has_history,
                "n_games": float(n_games) if pd.notna(n_games) else 0.0,
                "history_confidence": sample_confidence,
                "pdk_std_5": pd.to_numeric(hist.get("pdk_std_5"), errors="coerce") if hist is not None else np.nan,
                "lineup_group": lineup_group,
                "competition_scale": 1.0,
                "p_play": p_play,
                "status": status,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = _apply_current_role_competition(out)
    out = allocate_positional_minutes(out)

    rate = pd.to_numeric(out["pdk_rate_for_projection"], errors="coerce").fillna(0.0)
    minutes_pdk = out["expected_min"] * rate
    ensemble = pd.to_numeric(out["ensemble_pdk"], errors="coerce")
    implied = pd.to_numeric(out["implied_min"], errors="coerce").replace(0, np.nan).clip(lower=8.0)
    scaled_ensemble = ensemble * (out["expected_min"] / implied)
    prior = pd.to_numeric(out["prior_pdk"], errors="coerce")
    scaled_prior = prior * (out["expected_min"] / implied)

    hist = out["has_history"].fillna(False).astype(bool)
    components = pd.DataFrame(
        {"minutes": minutes_pdk, "ensemble": scaled_ensemble, "prior": scaled_prior},
        index=out.index,
    )
    projection_weights = models.get(
        "_projection_weights", {"minutes": 1.0, "ensemble": 0.0, "prior": 0.0}
    )
    out["component_minutes_pdk"] = minutes_pdk
    out["component_ensemble_pdk"] = scaled_ensemble
    out["component_prior_pdk"] = scaled_prior
    out["projection_weight_minutes"] = projection_weights.get("minutes", 0.0)
    out["projection_weight_ensemble"] = projection_weights.get("ensemble", 0.0)
    out["projection_weight_prior"] = projection_weights.get("prior", 0.0)
    blended = _apply_projection_weights(components, projection_weights)
    blended = blended.fillna(minutes_pdk)
    blended.loc[~hist] = minutes_pdk.loc[~hist]
    # The historical model is a separately evaluated direct PDK estimator. Blend
    # conservatively only when player history is sufficient; preserve rookie/low-data
    # paths and the existing minute allocation logic.
    historical_values = pd.to_numeric(out["historical_rf_pdk"], errors="coerce")
    historical_weights = pd.to_numeric(out["historical_rf_blend_weight"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    # Historical RF predicts a game score at the player's historical role/minutes.
    # Scale it to the current allocator's expected minutes before blending, so a
    # player assigned zero minutes cannot receive a positive projection from the
    # historical component alone.
    historical_scale_denominator = implied.where(implied.gt(0.0))
    historical_scale_denominator = historical_scale_denominator.fillna(
        out["expected_min"].where(pd.to_numeric(out["expected_min"], errors="coerce").gt(0.0))
    )
    historical_minute_ratio = (
        pd.to_numeric(out["expected_min"], errors="coerce")
        .div(historical_scale_denominator)
        .replace([np.inf, -np.inf], np.nan)
    )
    historical_scaled = (historical_values * historical_minute_ratio).clip(lower=0.0)
    out["historical_rf_pdk_scaled"] = historical_scaled
    can_blend_historical = historical_scaled.notna() & historical_weights.gt(0.0)
    blended.loc[can_blend_historical] = (
        (1.0 - historical_weights.loc[can_blend_historical]) * blended.loc[can_blend_historical]
        + historical_weights.loc[can_blend_historical] * historical_scaled.loc[can_blend_historical]
    )
    has_sample_size = pd.to_numeric(out["n_games"], errors="coerce").fillna(0.0)
    confidence = has_sample_size.div(has_sample_size + 12.0).clip(0.0, 1.0)
    blended.loc[hist] = (
        confidence.loc[hist] * blended.loc[hist]
        + (1.0 - confidence.loc[hist]) * minutes_pdk.loc[hist]
    )

    # Keep the conditional performance estimate separate from availability.
    # `expected_pdk` is the value consumed by the optimizer: P(play) times the
    # expected Dunkest score conditional on playing.
    out["expected_pdk_conditional"] = blended.clip(lower=0.0)
    out["expected_pdk_before_play_probability"] = out["expected_pdk_conditional"]
    out["expected_pdk"] = (
        pd.to_numeric(out["p_play"], errors="coerce").fillna(1.0)
        * out["expected_pdk_conditional"]
    ).clip(lower=0.0)
    interval_quantiles = _residual_quantiles_for_predictions(
        models, pd.to_numeric(out["expected_pdk_before_play_probability"], errors="coerce")
    )
    out = add_uncertainty_columns(
        out,
        residual_std=models.get("_residual_std", 5.0),
        residual_q10=interval_quantiles["q10"],
        residual_q50=interval_quantiles["q50"],
        residual_q90=interval_quantiles["q90"],
    )
    out = add_capital_gain_forecasts(out, plusvalenza_history)
    return out
