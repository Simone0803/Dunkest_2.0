"""Empirical one-week Dunkest CR change forecasts.

The conversion model uses only the official starting CR and realized Dunkest
score. Player context belongs in the upstream score forecast, not in the CR
rule model. Historical residuals are strictly walk-forward errors and provide
an empirical uncertainty distribution for gain/loss probabilities.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _starting_credit_from_end_price(
    end_credit: pd.Series | np.ndarray,
    plusvalenza: pd.Series | np.ndarray,
) -> pd.Series:
    """Reconstruct the pre-gameweek price from official end price and ΔCR."""
    end = pd.to_numeric(pd.Series(end_credit), errors="coerce")
    delta = pd.to_numeric(pd.Series(plusvalenza), errors="coerce")
    return end - delta


def _features(score: pd.Series, cr: pd.Series) -> pd.DataFrame:
    score = pd.to_numeric(score, errors="coerce")
    cr = pd.to_numeric(cr, errors="coerce")
    return pd.DataFrame({"score": score, "cr": cr, "score_per_cr": score / cr.where(cr > 0)})


_CR_BAND_EDGES = [0.0, 5.0, 7.0, 9.0, 12.0, 16.0, np.inf]
_CR_BAND_NAMES = ["<5", "5-7", "7-9", "9-12", "12-16", "16+"]


def _cr_band_labels(values: np.ndarray | pd.Series) -> np.ndarray:
    series = pd.Series(np.asarray(values, dtype=float))
    return pd.cut(
        series, bins=_CR_BAND_EDGES, labels=_CR_BAND_NAMES,
        right=False, include_lowest=True,
    ).astype(object).to_numpy()


def _estimate_band_corrections(
    cr_values: np.ndarray | pd.Series,
    residual_values: np.ndarray | pd.Series,
    *,
    shrinkage: float = 300.0,
    min_total_rows: int = 100,
) -> dict[str, float]:
    """Estimate shrunken bias corrections from past-only OOF residuals in CR units."""
    residuals = np.asarray(residual_values, dtype=float)
    cr = np.asarray(cr_values, dtype=float)
    if len(residuals) < min_total_rows or len(cr) != len(residuals):
        return {}
    labels = _cr_band_labels(cr)
    corrections: dict[str, float] = {}
    for label in _CR_BAND_NAMES:
        mask = labels == label
        n = int(mask.sum())
        if n:
            corrections[label] = float(np.mean(residuals[mask]) * n / (n + shrinkage))
    return corrections


def _corrections_for_cr(
    cr_values: np.ndarray | pd.Series, corrections: dict[str, float]
) -> np.ndarray:
    labels = _cr_band_labels(cr_values)
    return np.asarray([corrections.get(str(label), 0.0) if label == label else 0.0 for label in labels], dtype=float)


def _delta_probability_matrix(
    predicted_delta_cr: np.ndarray | pd.Series,
    cr_values: np.ndarray | pd.Series,
    residual_values: np.ndarray | pd.Series,
    residual_cr_values: np.ndarray | pd.Series,
) -> np.ndarray:
    """Estimate gain/flat/loss probabilities from past-only ΔCR residuals."""
    predicted = np.asarray(predicted_delta_cr, dtype=float)
    cr = np.asarray(cr_values, dtype=float)
    residuals = np.asarray(residual_values, dtype=float)
    residual_cr = np.asarray(residual_cr_values, dtype=float)
    probabilities = np.zeros((len(predicted), 3), dtype=float)
    labels = _cr_band_labels(cr)
    residual_labels = _cr_band_labels(residual_cr) if len(residual_cr) else np.array([], dtype=object)
    for label in _CR_BAND_NAMES:
        indices = np.flatnonzero(labels == label)
        if not len(indices):
            continue
        pool = residuals[residual_labels == label] if len(residuals) else np.array([], dtype=float)
        if len(pool) < 50:
            pool = residuals
        samples = np.quantile(pool, np.linspace(0.0, 1.0, min(101, len(pool)))) if len(pool) else np.array([0.0])
        distribution = np.round((predicted[indices, None] + samples[None, :]) * 10.0) / 10.0
        probabilities[indices, 0] = np.mean(distribution > 0.0, axis=1)
        probabilities[indices, 1] = np.mean(distribution == 0.0, axis=1)
        probabilities[indices, 2] = np.mean(distribution < 0.0, axis=1)
    row_sums = probabilities.sum(axis=1, keepdims=True)
    return np.divide(probabilities, row_sums, out=np.full_like(probabilities, 1.0 / 3.0), where=row_sums > 0)


def _probability_logits(probabilities: np.ndarray | pd.DataFrame) -> np.ndarray:
    return np.log(np.clip(np.asarray(probabilities, dtype=float), 1e-4, 1.0))


def _fit_probability_calibrator(
    probabilities: np.ndarray | pd.DataFrame,
    actual_class: np.ndarray | pd.Series,
    *,
    min_rows: int = 1000,
) -> LogisticRegression | None:
    """Fit regularized multinomial calibration from historical OOF probabilities only."""
    probs = np.asarray(probabilities, dtype=float)
    labels = np.asarray(actual_class, dtype=int)
    if len(probs) < min_rows or len(labels) != len(probs) or len(np.unique(labels)) < 3:
        return None
    if probs.ndim != 2 or probs.shape[1] != 3 or not np.isfinite(probs).all():
        return None
    calibrator = LogisticRegression(C=0.5, max_iter=500, random_state=42)
    calibrator.fit(_probability_logits(probs), labels)
    return calibrator


def _apply_probability_calibrator(
    probabilities: np.ndarray | pd.DataFrame,
    calibrator: LogisticRegression | None,
) -> np.ndarray:
    probs = np.asarray(probabilities, dtype=float)
    if calibrator is None:
        return probs.copy()
    predicted = calibrator.predict_proba(_probability_logits(probs))
    calibrated = np.zeros_like(probs)
    for column, label in enumerate(calibrator.classes_):
        calibrated[:, int(label)] = predicted[:, column]
    calibrated = np.clip(calibrated, 0.0, 1.0)
    total = calibrated.sum(axis=1, keepdims=True)
    return np.divide(calibrated, total, out=np.full_like(calibrated, 1.0 / 3.0), where=total > 0)


class _CRAdaptiveCapitalGainRegressor:
    """Use nonlinear fit only in credit bands where walk-forward errors support it."""

    def __init__(self) -> None:
        self.ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        self.extra_trees = ExtraTreesRegressor(
            n_estimators=60,
            min_samples_leaf=20,
            max_features=1.0,
            n_jobs=-1,
            random_state=42,
        )

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "_CRAdaptiveCapitalGainRegressor":
        self.ridge.fit(x, y)
        self.extra_trees.fit(x, y)
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        ridge_pred = np.asarray(self.ridge.predict(x), dtype=float)
        extra_pred = np.asarray(self.extra_trees.predict(x), dtype=float)
        cr = pd.to_numeric(x["cr"], errors="coerce").to_numpy(dtype=float)
        prediction = ridge_pred.copy()
        low_credit = cr < 5.0
        mid_credit = (cr >= 5.0) & (cr < 9.0)
        prediction[low_credit] = extra_pred[low_credit]
        prediction[mid_credit] = 0.5 * ridge_pred[mid_credit] + 0.5 * extra_pred[mid_credit]
        return prediction


def _capital_gain_estimator() -> _CRAdaptiveCapitalGainRegressor:
    """Fit both challengers; blend only where temporal errors justify it."""
    return _CRAdaptiveCapitalGainRegressor()


def _temporal_splits(
    sample: pd.DataFrame, min_train_rows: int = 40, step: int = 5
):
    """Expanding-origin splits sampled every fifth observed gameweek."""
    ordered = sample.sort_values(["season_order", "gameweek"])
    dates = ordered[["season_order", "gameweek"]].drop_duplicates().to_records(index=False)
    start = 1 if step <= 1 else step - 1
    for season_order, week in dates[start::max(1, step)]:
        train = (sample["season_order"] < season_order) | (
            sample["season_order"].eq(season_order) & sample["gameweek"].lt(week)
        )
        test = sample["season_order"].eq(season_order) & sample["gameweek"].eq(week)
        if int(train.sum()) >= min_train_rows and test.any():
            yield train, test


MIN_COMPLETE_PLUSVALENZA_TEAMS = 28


def _filter_incomplete_plusvalenza_seasons(
    history: pd.DataFrame | None, *, min_teams: int = MIN_COMPLETE_PLUSVALENZA_TEAMS
) -> tuple[pd.DataFrame, list[str], dict[str, int]]:
    """Exclude season samples that do not cover nearly the full NBA league.

    The Dunkest historical endpoint can return a deceptively large number of
    player-week rows while containing only a couple of NBA teams. Such a sample
    is not a representative season for learning ΔCR. Keep it in the source
    archive for audit, but do not let it enter the production capital-gain fit.
    """
    if history is None or history.empty or not {"season_id", "team_code"}.issubset(history.columns):
        return (history.copy() if history is not None else pd.DataFrame()), [], {}
    sample = history.copy()
    team_key = sample["team_code"].astype("string").str.strip().str.upper()
    sample["_team_key"] = team_key.mask(
        team_key.isna() | team_key.isin(["", "NAN", "NONE", "<NA>"]), pd.NA
    )
    coverage_series = sample.groupby("season_id")["_team_key"].nunique(dropna=True)

    def season_label(value: object) -> str:
        try:
            numeric = float(value)
            if numeric.is_integer():
                return str(int(numeric))
        except (TypeError, ValueError):
            pass
        return str(value)

    coverage = {season_label(season): int(count) for season, count in coverage_series.items()}
    incomplete = [
        season_label(season) for season, count in coverage_series.items()
        if int(count) < int(min_teams)
    ]
    complete_seasons = coverage_series[coverage_series >= int(min_teams)].index
    if len(complete_seasons) == 0:
        return sample.iloc[0:0].drop(columns=["_team_key"]), incomplete, coverage
    filtered = sample.loc[sample["season_id"].isin(complete_seasons)].drop(columns=["_team_key"])
    return filtered, incomplete, coverage


def fit_capital_gain_model(history: pd.DataFrame | None) -> dict:
    """Fit ΔCR and past-only OOF calibration for gain/flat/loss probabilities."""
    required = {"cr", "pdk", "plus", "gameweek"}
    empty_result = {
        "model": None, "mae": np.nan, "baseline_mae": np.nan, "rows": 0,
        "source_rows": 0, "excluded_incomplete_seasons": [], "season_team_coverage": {},
        "training_gameweeks_by_season": {}, "validation_rows": 0,
        "residuals": np.array([]), "residual_cr": np.array([]),
        "residuals_by_cr_band": {}, "calibration_by_cr_band": {},
        "probability_calibrator": None, "probability_calibration_training_rows": 0,
        "probability_calibration_diagnostics": {},
        "cr_min": np.nan, "cr_max": np.nan,
    }
    if history is None or history.empty or not required.issubset(history.columns):
        return empty_result
    source_rows = int(len(history))
    filtered_history, excluded_incomplete_seasons, season_team_coverage = (
        _filter_incomplete_plusvalenza_seasons(history)
    )
    if filtered_history.empty:
        result = empty_result.copy()
        result["source_rows"] = source_rows
        result["excluded_incomplete_seasons"] = excluded_incomplete_seasons
        result["season_team_coverage"] = season_team_coverage
        return result
    history = filtered_history
    optional = ["season_id"] if "season_id" in history else []
    sample = history[[*sorted(required), *optional]].copy()
    for col in [*required, *optional]:
        sample[col] = pd.to_numeric(sample[col], errors="coerce")

    # The official Dunkest stats table reports the price after the selected
    # gameweek together with that game's price delta. Reconstruct the price
    # available BEFORE the target performance to avoid target leakage:
    # CR_start = CR_end - plusvalenza. The forecast path receives the current
    # pre-gameweek CR, so training and inference must use the same price basis.
    sample["cr"] = _starting_credit_from_end_price(sample["cr"], sample["plus"])
    # Negative official Dunkest scores are valid outcomes and are especially
    # informative for capital loss; do not discard them as invalid targets.
    sample = sample.dropna().query("cr > 0").sort_values("gameweek")
    if "season_id" in sample:
        sample["season_order"] = pd.to_numeric(sample["season_id"], errors="coerce")
    else:
        sample["season_order"] = 0
    sample = sample.dropna(subset=["season_order"]).sort_values(["season_order", "gameweek"])
    training_gameweeks_by_season = {
        str(int(season)): sorted(pd.to_numeric(group["gameweek"], errors="coerce").dropna().astype(int).unique().tolist())
        for season, group in sample.groupby("season_order", sort=True)
    }
    if len(sample) < 60 or sample.gameweek.nunique() < 4:
        result = empty_result.copy()
        result["rows"] = len(sample)
        result["source_rows"] = source_rows
        result["excluded_incomplete_seasons"] = excluded_incomplete_seasons
        result["season_team_coverage"] = season_team_coverage
        result["training_gameweeks_by_season"] = training_gameweeks_by_season
        return result

    x = _features(sample.pdk, sample.cr)
    y = sample.plus.astype(float)
    errors: list[float] = []
    baseline_errors: list[float] = []
    calibrated_residuals: list[float] = []
    validation_cr: list[float] = []
    raw_oof_residuals: list[float] = []
    raw_oof_cr: list[float] = []
    probability_history: list[dict[str, float | int]] = []
    probability_eval_rows: list[dict[str, float | int]] = []

    for train, test in _temporal_splits(sample, step=5):
        fold_model = _capital_gain_estimator().fit(x.loc[train], y.loc[train])
        raw_pred = fold_model.predict(x.loc[test])
        actual = y.loc[test].to_numpy(dtype=float)
        test_cr = sample.loc[test, "cr"].to_numpy(dtype=float)

        # Estimate bias only from residuals of earlier OOF folds; never use the
        # current fold's outcomes to calibrate its own predictions.
        corrections = _estimate_band_corrections(raw_oof_cr, raw_oof_residuals)
        calibrated_pred = raw_pred + _corrections_for_cr(test_cr, corrections)

        # Calibrate gain/flat/loss probabilities using only earlier OOF outcomes.
        # The input score is the observed score here, so this evaluates the CR
        # conversion component only; it does not claim end-to-end score calibration.
        prior_residuals = np.asarray(calibrated_residuals, dtype=float)
        prior_residual_cr = np.asarray(validation_cr, dtype=float)
        fold_probabilities = _delta_probability_matrix(
            calibrated_pred, test_cr, prior_residuals, prior_residual_cr
        )
        fold_actual_class = np.where(actual > 0.0, 0, np.where(actual < 0.0, 2, 1)).astype(int)
        if len(prior_residuals) >= 500:
            fold_history = []
            for j, idx in enumerate(sample.index[test]):
                fold_history.append({
                    "p_gain": float(fold_probabilities[j, 0]),
                    "p_flat": float(fold_probabilities[j, 1]),
                    "p_loss": float(fold_probabilities[j, 2]),
                    "actual_class": int(fold_actual_class[j]),
                    "season_order": int(sample.loc[idx, "season_order"]),
                    "gameweek": int(sample.loc[idx, "gameweek"]),
                })
            if probability_history:
                prior_probs = np.asarray([
                    [r["p_gain"], r["p_flat"], r["p_loss"]] for r in probability_history
                ], dtype=float)
                prior_classes = np.asarray([r["actual_class"] for r in probability_history], dtype=int)
                fold_calibrator = _fit_probability_calibrator(prior_probs, prior_classes)
                if fold_calibrator is not None:
                    calibrated_probabilities = _apply_probability_calibrator(
                        fold_probabilities, fold_calibrator
                    )
                    for j, idx in enumerate(sample.index[test]):
                        probability_eval_rows.append({
                            "actual_class": int(fold_actual_class[j]),
                            "p_gain_raw": float(fold_probabilities[j, 0]),
                            "p_flat_raw": float(fold_probabilities[j, 1]),
                            "p_loss_raw": float(fold_probabilities[j, 2]),
                            "p_gain_calibrated": float(calibrated_probabilities[j, 0]),
                            "p_flat_calibrated": float(calibrated_probabilities[j, 1]),
                            "p_loss_calibrated": float(calibrated_probabilities[j, 2]),
                            "season_order": int(sample.loc[idx, "season_order"]),
                            "gameweek": int(sample.loc[idx, "gameweek"]),
                        })
            probability_history.extend(fold_history)

        fold_residuals = actual - calibrated_pred
        errors.extend(np.abs(fold_residuals))
        calibrated_residuals.extend(fold_residuals)
        validation_cr.extend(test_cr)
        baseline_errors.extend(np.abs(actual - float(y.loc[train].mean())))

        raw_oof_residuals.extend(actual - raw_pred)
        raw_oof_cr.extend(test_cr)

    mae = float(np.mean(errors)) if errors else np.nan
    baseline_mae = float(np.mean(baseline_errors)) if baseline_errors else np.nan
    raw_oof_residuals_array = np.asarray(raw_oof_residuals, dtype=float)
    raw_oof_cr_array = np.asarray(raw_oof_cr, dtype=float)
    residuals_array = np.asarray(calibrated_residuals, dtype=float)
    residual_cr_array = np.asarray(validation_cr, dtype=float)

    calibration = _estimate_band_corrections(raw_oof_cr_array, raw_oof_residuals_array)
    residual_band_labels = _cr_band_labels(residual_cr_array)
    residuals_by_band = {
        label: residuals_array[residual_band_labels == label]
        for label in _CR_BAND_NAMES
    }

    probability_history_frame = pd.DataFrame(probability_history)
    probability_calibrator = None
    if not probability_history_frame.empty:
        history_probabilities = probability_history_frame[["p_gain", "p_flat", "p_loss"]].to_numpy(dtype=float)
        history_classes = probability_history_frame["actual_class"].to_numpy(dtype=int)
        probability_calibrator = _fit_probability_calibrator(history_probabilities, history_classes)

    probability_diagnostics: dict[str, object] = {}
    if probability_eval_rows:
        eval_frame = pd.DataFrame(probability_eval_rows)
        actual_classes = eval_frame["actual_class"].to_numpy(dtype=int)
        one_hot = np.eye(3)[actual_classes]
        raw_probabilities = eval_frame[["p_gain_raw", "p_flat_raw", "p_loss_raw"]].to_numpy(dtype=float)
        calibrated_probabilities = eval_frame[["p_gain_calibrated", "p_flat_calibrated", "p_loss_calibrated"]].to_numpy(dtype=float)
        probability_diagnostics = {
            "n": int(len(eval_frame)),
            "actual_gain_rate": float(np.mean(actual_classes == 0)),
            "raw_gain_probability_mean": float(np.mean(raw_probabilities[:, 0])),
            "raw_gain_bias_percentage_points": float((np.mean(raw_probabilities[:, 0]) - np.mean(actual_classes == 0)) * 100.0),
            "calibrated_gain_probability_mean": float(np.mean(calibrated_probabilities[:, 0])),
            "calibrated_gain_bias_percentage_points": float((np.mean(calibrated_probabilities[:, 0]) - np.mean(actual_classes == 0)) * 100.0),
            "raw_multiclass_brier": float(np.mean(np.sum((raw_probabilities - one_hot) ** 2, axis=1))),
            "calibrated_multiclass_brier": float(np.mean(np.sum((calibrated_probabilities - one_hot) ** 2, axis=1))),
            "raw_multiclass_log_loss": float(log_loss(actual_classes, raw_probabilities, labels=[0, 1, 2])),
            "calibrated_multiclass_log_loss": float(log_loss(actual_classes, calibrated_probabilities, labels=[0, 1, 2])),
            "method": "sequential_past_only_multinomial_logistic_conversion_only",
        }
        by_season: dict[str, dict[str, float | int]] = {}
        for season_order, group in eval_frame.groupby("season_order", sort=True):
            group_actual = group["actual_class"].to_numpy(dtype=int)
            group_one_hot = np.eye(3)[group_actual]
            group_raw = group[["p_gain_raw", "p_flat_raw", "p_loss_raw"]].to_numpy(dtype=float)
            group_calibrated = group[["p_gain_calibrated", "p_flat_calibrated", "p_loss_calibrated"]].to_numpy(dtype=float)
            by_season[str(int(season_order))] = {
                "n": int(len(group)),
                "actual_gain_rate": float(np.mean(group_actual == 0)),
                "raw_gain_bias_percentage_points": float((np.mean(group_raw[:, 0]) - np.mean(group_actual == 0)) * 100.0),
                "calibrated_gain_bias_percentage_points": float((np.mean(group_calibrated[:, 0]) - np.mean(group_actual == 0)) * 100.0),
                "raw_multiclass_brier": float(np.mean(np.sum((group_raw - group_one_hot) ** 2, axis=1))),
                "calibrated_multiclass_brier": float(np.mean(np.sum((group_calibrated - group_one_hot) ** 2, axis=1))),
                "raw_multiclass_log_loss": float(log_loss(group_actual, group_raw, labels=[0, 1, 2])),
                "calibrated_multiclass_log_loss": float(log_loss(group_actual, group_calibrated, labels=[0, 1, 2])),
            }
        probability_diagnostics["by_season_id"] = by_season

    model = None
    if np.isfinite(mae) and np.isfinite(baseline_mae) and mae < baseline_mae:
        model = _capital_gain_estimator().fit(x, y)
    return {
        "model": model,
        "source_rows": source_rows,
        "excluded_incomplete_seasons": excluded_incomplete_seasons,
        "season_team_coverage": season_team_coverage,
        "training_gameweeks_by_season": training_gameweeks_by_season,
        "mae": mae,
        "baseline_mae": baseline_mae,
        "rows": len(sample),
        "validation_rows": len(residuals_array),
        # These residuals are in CR units and are measured after the past-only
        # bias correction used in each walk-forward fold.
        "residuals": residuals_array,
        "residual_cr": residual_cr_array,
        "residuals_by_cr_band": residuals_by_band,
        "calibration_by_cr_band": calibration,
        "probability_calibrator": probability_calibrator,
        "probability_calibration_training_rows": int(len(probability_history_frame)),
        "probability_calibration_diagnostics": probability_diagnostics,
        "cr_min": float(sample.cr.min()),
        "cr_max": float(sample.cr.max()),
    }


def add_capital_gain_forecasts(forecasts: pd.DataFrame, history: pd.DataFrame | None) -> pd.DataFrame:
    """Estimate E[ΔCR] from score uncertainty plus correctly unit-matched OOF CR residuals."""
    out = forecasts.copy()
    for col in (
        "expected_plusvalenza", "plusvalenza_p10", "plusvalenza_p90",
        "plusvalenza_prob_gain", "plusvalenza_prob_loss", "plusvalenza_prob_flat",
        "plusvalenza_prob_gain_1cr", "plusvalenza_bias_correction_cr",
        "plusvalenza_prob_gain_raw", "plusvalenza_prob_loss_raw", "plusvalenza_prob_flat_raw",
    ):
        out[col] = np.nan
    out["plusvalenza_probability_calibration_method"] = "unavailable"
    out["plusvalenza_prob_gain_1cr_calibration_method"] = "raw_empirical_distribution_not_calibrated"
    out["plusvalenza_residual_pool_rows"] = 0
    out["plusvalenza_cv_mae"] = np.nan
    out["plusvalenza_baseline_mae"] = np.nan
    out["capital_gain_delta_cr_mae_walk_forward"] = np.nan
    out["capital_gain_delta_cr_mae_baseline"] = np.nan
    out["capital_gain_metric_target"] = "official_plus_delta_cr"
    out["capital_gain_metric_unit"] = "CR per player per Dunkest gameweek"
    out["capital_gain_metric_validation"] = (
        "expanding-origin season/gameweek walk-forward; historical starting CR reconstructed "
        "as official end CR minus observed plusvalenza; every fifth observed gameweek; "
        "past-only CR-band bias calibration and sequential multinomial calibration of "
        "gain/flat/loss probabilities from OOF conversion-only predictions"
    )
    out["capital_gain_price_basis"] = "pre_gameweek_cr = official_end_cr - official_plusvalenza"
    out["plusvalenza_probability_calibration_training_rows"] = 0
    for column in (
        "plusvalenza_probability_calibration_oof_n",
        "plusvalenza_probability_calibration_oof_gain_bias_raw_pp",
        "plusvalenza_probability_calibration_oof_gain_bias_calibrated_pp",
        "plusvalenza_probability_calibration_oof_brier_raw",
        "plusvalenza_probability_calibration_oof_brier_calibrated",
        "plusvalenza_probability_calibration_oof_logloss_raw",
        "plusvalenza_probability_calibration_oof_logloss_calibrated",
    ):
        out[column] = np.nan
    out["capital_gain_metric_baseline"] = "training-window mean ΔCR"
    out["plusvalenza_training_rows"] = 0
    out["plusvalenza_training_gameweeks"] = 0
    out["plusvalenza_training_seasons"] = 0
    out["plusvalenza_validation_rows"] = 0
    out["plusvalenza_source"] = "unavailable"
    out["plusvalenza_cost_supported"] = False
    fitted = fit_capital_gain_model(history)
    gameweeks_by_season = fitted.get("training_gameweeks_by_season", {})
    out["plusvalenza_training_gameweeks"] = int(
        sum(len(weeks) for weeks in gameweeks_by_season.values())
    )
    out["plusvalenza_training_seasons"] = int(len(gameweeks_by_season))
    out["plusvalenza_probability_calibration_training_rows"] = int(
        fitted.get("probability_calibration_training_rows", 0)
    )
    diagnostics = fitted.get("probability_calibration_diagnostics", {})
    diagnostic_columns = {
        "plusvalenza_probability_calibration_oof_n": "n",
        "plusvalenza_probability_calibration_oof_gain_bias_raw_pp": "raw_gain_bias_percentage_points",
        "plusvalenza_probability_calibration_oof_gain_bias_calibrated_pp": "calibrated_gain_bias_percentage_points",
        "plusvalenza_probability_calibration_oof_brier_raw": "raw_multiclass_brier",
        "plusvalenza_probability_calibration_oof_brier_calibrated": "calibrated_multiclass_brier",
        "plusvalenza_probability_calibration_oof_logloss_raw": "raw_multiclass_log_loss",
        "plusvalenza_probability_calibration_oof_logloss_calibrated": "calibrated_multiclass_log_loss",
    }
    for column, key in diagnostic_columns.items():
        out[column] = diagnostics.get(key, np.nan)
    model, residuals = fitted["model"], fitted["residuals"]
    if model is None or len(residuals) == 0:
        return out

    cr = pd.to_numeric(out.get("cr"), errors="coerce")
    supported = cr.between(fitted["cr_min"], fitted["cr_max"])
    safe_cr = cr.fillna(fitted["cr_min"]).to_numpy(dtype=float)
    expected_score = pd.to_numeric(out["expected_pdk"], errors="coerce").fillna(0.0)
    q10 = pd.to_numeric(out.get("p10", expected_score), errors="coerce").fillna(expected_score)
    q50 = pd.to_numeric(out.get("p50", expected_score), errors="coerce").fillna(expected_score)
    q90 = pd.to_numeric(out.get("p90", expected_score), errors="coerce").fillna(expected_score)
    ordered_quantiles = np.sort(np.column_stack([q10, q50, q90]), axis=1)
    q10, q50, q90 = (pd.Series(ordered_quantiles[:, i], index=out.index) for i in range(3))

    # Approximate the score distribution from P10/P50/P90. OOF residuals below
    # are in CR, not PDK: they must be added AFTER score-to-CR conversion.
    score_quantiles = np.linspace(0.0, 1.0, 41)
    base_scores = np.where(
        score_quantiles <= 0.5,
        q10.to_numpy()[:, None]
        + (q50 - q10).to_numpy()[:, None] * (score_quantiles[None, :] / 0.5),
        q50.to_numpy()[:, None]
        + (q90 - q50).to_numpy()[:, None] * ((score_quantiles[None, :] - 0.5) / 0.5),
    )
    base_scores = np.maximum(base_scores, 0.0)
    n_players, n_score_quantiles = base_scores.shape
    cr_repeated = np.repeat(safe_cr, n_score_quantiles)
    predicted_gain = model.predict(
        _features(pd.Series(base_scores.reshape(-1)), pd.Series(cr_repeated))
    ).reshape(n_players, n_score_quantiles)

    corrections = fitted["calibration_by_cr_band"]
    bias_correction = _corrections_for_cr(safe_cr, corrections)
    predicted_gain = predicted_gain + bias_correction[:, None]

    # Draw player-specific CR residuals from the corresponding credit band.
    # A global fallback is used for bands with fewer than 50 OOF residuals.
    n_resid = min(101, len(residuals))
    residual_quantiles = np.linspace(0.0, 1.0, n_resid)
    residual_samples = np.empty((n_players, n_resid), dtype=float)
    band_labels = _cr_band_labels(safe_cr)
    residuals_by_band = fitted["residuals_by_cr_band"]
    residual_pool_rows = np.zeros(n_players, dtype=int)
    for i, label in enumerate(band_labels):
        pool = np.asarray(residuals_by_band.get(str(label), []), dtype=float)
        if len(pool) < 50:
            pool = residuals
        residual_samples[i, :] = np.quantile(pool, residual_quantiles)
        residual_pool_rows[i] = len(pool)

    # Quantize the simulated ΔCR itself to the historical 0.1-credit grid.
    distribution = np.round(
        (predicted_gain[:, :, None] + residual_samples[:, None, :]) * 10.0
    ) / 10.0
    dist = pd.DataFrame(distribution.reshape(n_players, -1), index=out.index)
    out.loc[supported, "expected_plusvalenza"] = dist.loc[supported].mean(axis=1)
    out.loc[supported, "plusvalenza_p10"] = dist.loc[supported].quantile(.10, axis=1)
    out.loc[supported, "plusvalenza_p90"] = dist.loc[supported].quantile(.90, axis=1)
    raw_gain = (dist > 0).mean(axis=1)
    raw_flat = (dist == 0).mean(axis=1)
    raw_loss = (dist < 0).mean(axis=1)
    out.loc[supported, "plusvalenza_prob_gain_raw"] = raw_gain.loc[supported]
    out.loc[supported, "plusvalenza_prob_flat_raw"] = raw_flat.loc[supported]
    out.loc[supported, "plusvalenza_prob_loss_raw"] = raw_loss.loc[supported]
    raw_probabilities = np.column_stack([raw_gain.to_numpy(float), raw_flat.to_numpy(float), raw_loss.to_numpy(float)])
    out.loc[~supported, "plusvalenza_probability_calibration_method"] = "outside_cost_support"
    probability_calibrator = fitted.get("probability_calibrator")
    calibrated_probabilities = _apply_probability_calibrator(raw_probabilities, probability_calibrator)
    if probability_calibrator is not None:
        probability_method = "multinomial_logistic_past_only_oof_conversion_only"
    else:
        probability_method = "raw_empirical_distribution_insufficient_oof_calibration"
    out.loc[supported, "plusvalenza_prob_gain"] = calibrated_probabilities[supported.to_numpy(), 0]
    out.loc[supported, "plusvalenza_prob_flat"] = calibrated_probabilities[supported.to_numpy(), 1]
    out.loc[supported, "plusvalenza_prob_loss"] = calibrated_probabilities[supported.to_numpy(), 2]
    out.loc[supported, "plusvalenza_prob_gain_1cr"] = (dist.loc[supported] >= 1.0).mean(axis=1)
    out.loc[supported, "plusvalenza_probability_calibration_method"] = probability_method
    out["plusvalenza_cv_mae"] = fitted["mae"]
    out["plusvalenza_baseline_mae"] = fitted["baseline_mae"]
    out["capital_gain_delta_cr_mae_walk_forward"] = fitted["mae"]
    out["capital_gain_delta_cr_mae_baseline"] = fitted["baseline_mae"]
    out["plusvalenza_training_rows"] = fitted["rows"]
    out["plusvalenza_validation_rows"] = fitted["validation_rows"]
    out.loc[supported, "plusvalenza_bias_correction_cr"] = bias_correction[supported.to_numpy()]
    out.loc[supported, "plusvalenza_residual_pool_rows"] = residual_pool_rows[supported.to_numpy()]
    out["plusvalenza_cost_supported"] = supported
    out["plusvalenza_source"] = np.where(
        supported, "official_score_cost_walk_forward_calibrated", "outside_cost_support"
    )
    return out
