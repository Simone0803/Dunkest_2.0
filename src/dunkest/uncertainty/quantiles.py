from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd


_NORMAL = NormalDist()
_Z_QUANTILES = np.array([_NORMAL.inv_cdf(0.1), 0.0, _NORMAL.inv_cdf(0.9)])


def _piecewise_quantile(probability: float, residuals: np.ndarray) -> float:
    """Interpolate calibrated residual quantiles on a normal-probability axis."""
    eps = 1e-6
    z = _NORMAL.inv_cdf(float(np.clip(probability, eps, 1.0 - eps)))
    if z < _Z_QUANTILES[0]:
        slope = (residuals[1] - residuals[0]) / (_Z_QUANTILES[1] - _Z_QUANTILES[0])
        return float(residuals[0] + slope * (z - _Z_QUANTILES[0]))
    if z > _Z_QUANTILES[-1]:
        slope = (residuals[-1] - residuals[-2]) / (_Z_QUANTILES[-1] - _Z_QUANTILES[-2])
        return float(residuals[-1] + slope * (z - _Z_QUANTILES[-1]))
    return float(np.interp(z, _Z_QUANTILES, residuals))


def _conditional_cdf_at_zero(mean: float, residuals: np.ndarray) -> float:
    """Approximate the conditional score distribution's mass below zero."""
    target = -mean
    if target < residuals[0]:
        slope = (_Z_QUANTILES[1] - _Z_QUANTILES[0]) / (residuals[1] - residuals[0])
        z = _Z_QUANTILES[0] + slope * (target - residuals[0])
    elif target > residuals[-1]:
        slope = (_Z_QUANTILES[-1] - _Z_QUANTILES[-2]) / (residuals[-1] - residuals[-2])
        z = _Z_QUANTILES[-1] + slope * (target - residuals[-1])
    else:
        z = float(np.interp(target, residuals, _Z_QUANTILES))
    return float(np.clip(_NORMAL.cdf(z), 0.0, 1.0))


def _mixture_quantile(
    probability: float,
    play_probability: float,
    playing_mean: float,
    residuals: np.ndarray,
) -> float:
    """Quantile for a zero-if-absent and continuous-if-playing score mixture."""
    p = float(np.clip(play_probability, 0.0, 1.0))
    if p <= 0.0:
        return 0.0
    conditional_zero_cdf = _conditional_cdf_at_zero(playing_mean, residuals)
    lower_zero_mass = p * conditional_zero_cdf
    upper_zero_mass = (1.0 - p) + lower_zero_mass
    q = float(np.clip(probability, 1e-6, 1.0 - 1e-6))
    if lower_zero_mass <= q <= upper_zero_mass:
        return 0.0
    conditional_probability = q / p if q < lower_zero_mass else (q - (1.0 - p)) / p
    return float(playing_mean + _piecewise_quantile(conditional_probability, residuals))


def add_uncertainty_columns(
    df: pd.DataFrame,
    residual_std: float = 5.0,
    residual_q10: float | pd.Series | np.ndarray | None = None,
    residual_q50: float | pd.Series | np.ndarray | None = None,
    residual_q90: float | pd.Series | np.ndarray | None = None,
) -> pd.DataFrame:
    out = df.copy()
    residual_std = float(residual_std)
    if not np.isfinite(residual_std) or residual_std <= 0.0:
        residual_std = 5.0
    historical_std = pd.to_numeric(
        out.get("pdk_std_5", pd.Series(np.nan, index=out.index)), errors="coerce"
    )
    base_std = historical_std.fillna(residual_std).clip(lower=residual_std * 0.5)
    probability = pd.to_numeric(out.get("p_play", pd.Series(1.0, index=out.index)), errors="coerce").fillna(1.0).clip(0, 1)
    playing_mean = pd.to_numeric(
        out.get("expected_pdk_before_play_probability", out["expected_pdk"]), errors="coerce"
    ).fillna(0.0)
    std = np.sqrt(probability * base_std.pow(2) + probability * (1 - probability) * playing_mean.pow(2))
    mu = out["expected_pdk"]
    out["pred_std"] = std
    quantiles = [residual_q10, residual_q50, residual_q90]
    has_calibrated_quantiles = all(value is not None for value in quantiles)
    quantile_matrix = None
    if has_calibrated_quantiles:
        columns = []
        for value in quantiles:
            if np.isscalar(value):
                column = np.full(len(out), float(value), dtype=float)
            elif isinstance(value, pd.Series):
                column = pd.to_numeric(value.reindex(out.index), errors="coerce").to_numpy(dtype=float)
            else:
                column = pd.to_numeric(pd.Series(value), errors="coerce").to_numpy(dtype=float)
            if len(column) != len(out) or not np.isfinite(column).all():
                has_calibrated_quantiles = False
                break
            columns.append(column)
        if has_calibrated_quantiles:
            # Each row may use the residual quantiles calibrated for its forecast
            # score band. They are already in PDK units and must not be rescaled
            # by player volatility, which would distort empirical coverage.
            quantile_matrix = np.maximum.accumulate(np.column_stack(columns), axis=1)
    if not has_calibrated_quantiles:
        fallback = np.array([-1.28 * residual_std, 0.0, 1.28 * residual_std], dtype=float)
        quantile_matrix = np.tile(fallback, (len(out), 1))
    # Conditional score quantiles use on-court variability. The Bernoulli
    # availability variance is added once by the mixture quantile below.
    conditional_scale = base_std / max(float(residual_std), 1e-9)
    quantile_levels = (0.10, 0.50, 0.90)
    values = np.empty((len(out), len(quantile_levels)), dtype=float)
    for row_index in range(len(out)):
        row_residuals = quantile_matrix[row_index].copy()
        for quantile_index in range(1, len(row_residuals)):
            if row_residuals[quantile_index] <= row_residuals[quantile_index - 1]:
                row_residuals[quantile_index] = row_residuals[quantile_index - 1] + 1e-9
        # Only fallback Gaussian intervals need a player-specific scale.
        scaled_residuals = (
            row_residuals
            if has_calibrated_quantiles
            else row_residuals * float(conditional_scale.iloc[row_index])
        )
        for quantile_index, level in enumerate(quantile_levels):
            values[row_index, quantile_index] = _mixture_quantile(
                level,
                float(probability.iloc[row_index]),
                float(playing_mean.iloc[row_index]),
                scaled_residuals,
            )
    out[["p10", "p50", "p90"]] = values
    return out


def interval_coverage_by_cohort(
    actual: pd.Series,
    intervals: pd.DataFrame,
    history_games: pd.Series | None = None,
    observed_minutes: pd.Series | None = None,
    minimum_group_size: int = 30,
) -> list[dict]:
    """Summarize cross-fitted interval coverage without changing forecasts."""
    if not {"p10", "p90"}.issubset(intervals.columns):
        raise ValueError("Interval diagnostics require p10 and p90 columns.")

    sample = pd.DataFrame(
        {
            "actual": pd.to_numeric(actual, errors="coerce"),
            "p10": pd.to_numeric(intervals["p10"], errors="coerce"),
            "p90": pd.to_numeric(intervals["p90"], errors="coerce"),
        }
    ).dropna()
    if history_games is not None:
        sample["history_games"] = pd.to_numeric(history_games, errors="coerce")
    if observed_minutes is not None:
        sample["observed_minutes"] = pd.to_numeric(observed_minutes, errors="coerce")
    if sample.empty:
        return []

    cohorts = [("all", "all", sample)]
    if "history_games" in sample:
        bands = pd.cut(
            sample["history_games"],
            bins=[-np.inf, 5, 20, np.inf],
            labels=["0-4", "5-19", "20+"],
            right=False,
        )
        cohorts.extend(
            ("history_games", str(label), group)
            for label, group in sample.groupby(bands, observed=True)
        )
    if "observed_minutes" in sample:
        bands = pd.cut(
            sample["observed_minutes"],
            bins=[-np.inf, 12, 24, 32, np.inf],
            labels=["<12", "12-23", "24-31", "32+"],
            right=False,
        )
        cohorts.extend(
            ("observed_minutes", str(label), group)
            for label, group in sample.groupby(bands, observed=True)
        )

    return [
        {
            "dimension": dimension,
            "cohort": cohort,
            "n": len(group),
            "p10_coverage": float(group["actual"].ge(group["p10"]).mean()),
            "p90_coverage": float(group["actual"].le(group["p90"]).mean()),
            "mean_interval_width": float((group["p90"] - group["p10"]).mean()),
            "meets_minimum_group_size": len(group) >= minimum_group_size,
        }
        for dimension, cohort, group in cohorts
    ]
