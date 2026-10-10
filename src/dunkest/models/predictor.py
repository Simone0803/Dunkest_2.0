from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from scipy.optimize import minimize

from dunkest.config import Settings
from dunkest.data.temporal import validate_prematch_features
from dunkest.names import player_key
from dunkest.rules.eligibility import play_probability
from dunkest.rules.pdk import normalize_position
from dunkest.uncertainty.quantiles import (
    add_uncertainty_columns,
    interval_coverage_by_cohort,
)
from dunkest.models.rookie_prior import COLLEGE_PRIOR_BASE_WEIGHT, COLLEGE_PRIOR_FADE_GAMES
from dunkest.models.capital_gain import add_capital_gain_forecasts

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


def train_models(settings: Settings, features: pd.DataFrame) -> tuple[dict, pd.Series]:
    if features.empty or "target_pdk" not in features:
        raise ValueError(
            "Training features are empty or lack target_pdk. Check the NBA game-log "
            "cache and the selected feature season."
        )
    df = features.copy()
    df["target_pdk"] = pd.to_numeric(df["target_pdk"], errors="coerce")
    finite_target = np.isfinite(df["target_pdk"].to_numpy(dtype=float, na_value=np.nan))
    df = df.loc[finite_target].copy()
    if df.empty:
        raise ValueError("No finite historical target_pdk values are available for model training.")

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
    target_pdk = pd.to_numeric(df["target_pdk"], errors="coerce")
    baseline = pd.to_numeric(
        df.get("expected_pdk_minutes_model", pd.Series(0.0, index=df.index)),
        errors="coerce",
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(lower=0.0)
    y = target_pdk - baseline
    y_min = df["target_min"] if "target_min" in df else pd.Series(np.nan, index=df.index)
    X, medians = _fit_matrix(df, cols)

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
        for fold_index, validation_dates in enumerate(validation_date_folds):
            if not len(validation_dates):
                continue
            train_idx = dates < validation_dates[0]
            val_idx = dates.isin(validation_dates)
            if int(train_idx.sum()) < 80 or int(val_idx.sum()) < 40:
                continue
            fold_X, fold_medians = _fit_matrix(df.loc[train_idx], cols)
            val_X = df.loc[val_idx, cols].apply(pd.to_numeric, errors="coerce")
            val_X = val_X.fillna(fold_medians).fillna(0.0)
            for name, model in zoo.items():
                model.fit(fold_X, y.loc[train_idx])
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
            ),
        },
        index=df.index,
    )
    projection_weights = _fit_projection_weights(target_pdk, projection_components)
    cross_fitted_residuals: list[pd.Series] = []
    for fold_index in sorted(validation_fold[validation_fold >= 0].unique()):
        val_idx = validation_fold.eq(fold_index)
        prior_idx = validation_fold.lt(fold_index)
        if int(prior_idx.sum()) < 40:
            continue
        fold_projection_weights = _fit_projection_weights(
            target_pdk.loc[prior_idx], projection_components.loc[prior_idx]
        )
        fold_blend = _apply_projection_weights(
            projection_components.loc[val_idx], fold_projection_weights
        )
        fold_residuals = target_pdk.loc[val_idx] - fold_blend
        cross_fitted_residuals.append(fold_residuals.dropna())
    projection_residuals = (
        pd.concat(cross_fitted_residuals).to_numpy(dtype=float)
        if cross_fitted_residuals
        else np.array([], dtype=float)
    )

    fitted: dict = {}
    for name, model in zoo.items():
        model.fit(X, y)
        fitted[name] = model

    fitted["_feature_cols"] = cols
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
    interval_diagnostics = []
    calibration_rows = validation_output.notna()
    if calibration_rows.any():
        validation_frame = df.loc[calibration_rows]
        interval_inputs = pd.DataFrame(
            {
                "expected_pdk": validation_output.loc[calibration_rows],
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
        validation_intervals = add_uncertainty_columns(
            interval_inputs,
            residual_std=fitted["_residual_std"],
            residual_q10=fitted["_residual_q10"],
            residual_q50=fitted["_residual_q50"],
            residual_q90=fitted["_residual_q90"],
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
        "Cross-fitted point predictions; residual quantiles share the pooled cross-fitted calibration sample. "
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
    """Give requested minutes to higher-priority players first; squeeze the rest."""
    out = out.copy()
    out["competition_scale"] = 1.0
    playable = out["p_play"] > 0
    for (_, _), group in out.loc[playable].groupby(["team", "role"], sort=False):
        if group.empty:
            continue
        cap = ROLE_CAPACITY.get(str(group["role"].iloc[0]), 96.0)
        lineup = group.get("lineup_group", pd.Series("", index=group.index)).map(
            _normalize_lineup_group
        )
        order = pd.DataFrame(
            {
                "starter": lineup.eq("QUINTETTO").astype(int),
                # Use projected opportunity as the tiebreaker. Dunkest price
                # reflects market value and must not itself manufacture minutes.
                "req": pd.to_numeric(group["expected_min"], errors="coerce").fillna(0.0),
                "name": group["player_name"].astype(str),
            },
            index=group.index,
        ).sort_values(["starter", "req", "name"], ascending=[False, False, True])
        remaining = float(cap)
        allocated = pd.Series(0.0, index=group.index)
        for idx in order.index:
            req = float(order.loc[idx, "req"])
            give = min(max(req, 0.0), remaining)
            allocated.loc[idx] = give
            remaining = max(0.0, remaining - give)
        req = order["req"].replace(0, np.nan)
        scale = (allocated / req).fillna(1.0).clip(0.0, 1.0)
        out.loc[group.index, "expected_min"] = allocated
        out.loc[group.index, "competition_scale"] = scale
    out.loc[out["p_play"] <= 0, "expected_min"] = 0.0
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
                "name": group["player_name"].astype(str),
            },
            index=group.index,
        ).sort_values(
            ["starter", "bench", "expected_min", "name"],
            ascending=[False, False, False, True],
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
    if not latest.empty:
        latest["_key"] = latest["PLAYER_NAME"].map(player_key)
        residual = _ensemble_predict(models, latest)
        baseline = pd.to_numeric(
            latest.get("expected_pdk_minutes_model", pd.Series(0.0, index=latest.index)),
            errors="coerce",
        ).fillna(0.0)
        latest["ensemble_pdk"] = (baseline + residual).clip(lower=0.0)
        hist_lookup = latest.drop_duplicates("_key", keep="last").set_index("_key")
    else:
        hist_lookup = pd.DataFrame()

    injury_prob: dict[str, float] = {}
    injury_status: dict[str, str] = {}
    if injuries is not None and not injuries.empty and "player_name" in injuries.columns:
        for _, inj in injuries.iterrows():
            key = player_key(inj.get("player_name", ""))
            injury_prob[key] = play_probability(
                inj.get("status", ""), inj.get("lineup_group", "")
            )
            injury_status[key] = str(inj.get("status", "")).strip()

    rookie_lookup: dict[str, pd.Series] = {}
    if college_rookie_priors is not None and not college_rookie_priors.empty:
        rookie_rows = college_rookie_priors.copy()
        if "player_key" not in rookie_rows and "player_name" in rookie_rows:
            rookie_rows["player_key"] = rookie_rows["player_name"].map(player_key)
        if {"player_key", "college_projected_pdk_per_min", "nba_rookie_rate_baseline"}.issubset(rookie_rows.columns):
            rookie_lookup = rookie_rows.drop_duplicates("player_key", keep="last").set_index(
                "player_key"
            ).to_dict("index")

    dk = dunkest_df.copy()
    dk = dk[dk["cr"].between(settings.min_cr, settings.max_cr)]
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
        if key in injury_prob:
            p_play = min(p_play, injury_prob[key])
        status = "Out" if p_play <= 0 else "Available"
        if 0 < p_play < 1:
            status_source = str(d.get("status", "")).strip()
            if key in injury_status and injury_prob.get(key, 1.0) <= play_probability(
                d.get("status", ""), lineup_group
            ):
                status_source = injury_status[key]
            status = status_source or "Questionable"
            status = f"{status} ({p_play:.0%})"

        ensemble = pd.to_numeric(hist.get("ensemble_pdk"), errors="coerce") if hist is not None else np.nan
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
        if pd.notna(rate) and pd.notna(peer_rate) and pd.notna(n_games):
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
            college_minutes_weight = float(np.clip(minute_base_weight, 0.0, 0.35)) * (
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
                "expected_pdk": float(ensemble) if pd.notna(ensemble) else (
                    float(prior_pdk) if pd.notna(prior_pdk) else np.nan
                ),
                "ensemble_pdk": float(ensemble) if pd.notna(ensemble) else np.nan,
                "prior_pdk": float(prior_pdk) if pd.notna(prior_pdk) else np.nan,
                "expected_min": emin,
                "requested_min": emin,
                "minutes_projection_basis": minute_basis,
                "implied_min": float(implied_min) if pd.notna(implied_min) else emin,
                "historical_pdk_per_min": historical_rate,
                "pdk_rate_for_projection": rate,
                "cr_market_pdk_per_min": peer_rate,
                "cr_market_minutes_per_game": peer_minutes,
                "college_projected_pdk_per_min": float(college_rate) if pd.notna(college_rate) else np.nan,
                "college_prior_weight": college_weight,
                "college_cv_mae": pd.to_numeric(rookie.get("college_cv_mae"), errors="coerce") if rookie else np.nan,
                "college_baseline_cv_mae": pd.to_numeric(rookie.get("college_baseline_cv_mae"), errors="coerce") if rookie else np.nan,
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
    out = add_uncertainty_columns(
        out,
        residual_std=models.get("_residual_std", 5.0),
        residual_q10=models.get("_residual_q10"),
        residual_q50=models.get("_residual_q50"),
        residual_q90=models.get("_residual_q90"),
    )
    out = add_capital_gain_forecasts(out, plusvalenza_history)
    return out
