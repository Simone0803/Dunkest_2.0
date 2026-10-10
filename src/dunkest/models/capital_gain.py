"""Empirical one-week Dunkest CR change forecasts.

The conversion model uses only the official starting CR and realized Dunkest
score. Player context belongs in the upstream score forecast, not in the CR
rule model. Historical residuals are strictly walk-forward errors and provide
an empirical uncertainty distribution for gain/loss probabilities.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _features(score: pd.Series, cr: pd.Series) -> pd.DataFrame:
    score = pd.to_numeric(score, errors="coerce")
    cr = pd.to_numeric(cr, errors="coerce")
    return pd.DataFrame({"score": score, "cr": cr, "score_per_cr": score / cr.where(cr > 0)})


def _temporal_splits(sample: pd.DataFrame, min_train_rows: int = 40):
    ordered = sample.sort_values(["season_order", "gameweek"])
    dates = ordered[["season_order", "gameweek"]].drop_duplicates().to_records(index=False)
    for season_order, week in dates[1:]:
        train = (sample["season_order"] < season_order) | (
            sample["season_order"].eq(season_order) & sample["gameweek"].lt(week)
        )
        test = sample["season_order"].eq(season_order) & sample["gameweek"].eq(week)
        if int(train.sum()) >= min_train_rows and test.any():
            yield train, test


def fit_capital_gain_model(history: pd.DataFrame | None) -> dict:
    """Fit only when walk-forward MAE beats the prior-week mean baseline."""
    required = {"cr", "pdk", "plus", "gameweek"}
    if history is None or history.empty or not required.issubset(history.columns):
        return {"model": None, "mae": np.nan, "baseline_mae": np.nan, "rows": 0,
                "residuals": np.array([]), "cr_min": np.nan, "cr_max": np.nan}
    optional = ["season_id"] if "season_id" in history else []
    sample = history[[*sorted(required), *optional]].copy()
    for col in [*required, *optional]:
        sample[col] = pd.to_numeric(sample[col], errors="coerce")
    sample = sample.dropna().query("cr > 0 and pdk >= 0").sort_values("gameweek")
    if "season_id" in sample:
        sample["season_order"] = pd.to_numeric(sample["season_id"], errors="coerce")
    else:
        sample["season_order"] = 0
    sample = sample.dropna(subset=["season_order"]).sort_values(["season_order", "gameweek"])
    if len(sample) < 60 or sample.gameweek.nunique() < 4:
        return {"model": None, "mae": np.nan, "baseline_mae": np.nan, "rows": len(sample),
                "residuals": np.array([]), "cr_min": np.nan, "cr_max": np.nan}
    x = _features(sample.pdk, sample.cr)
    y = sample.plus.astype(float)
    errors, baseline_errors, residuals = [], [], []
    for train, test in _temporal_splits(sample):
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        model.fit(x.loc[train], y.loc[train])
        pred = model.predict(x.loc[test])
        errors.extend(np.abs(y.loc[test].to_numpy() - pred))
        residuals.extend(y.loc[test].to_numpy() - pred)
        baseline_errors.extend(np.abs(y.loc[test].to_numpy() - y.loc[train].mean()))
    mae = float(np.mean(errors)) if errors else np.nan
    baseline_mae = float(np.mean(baseline_errors)) if baseline_errors else np.nan
    model = None
    if np.isfinite(mae) and np.isfinite(baseline_mae) and mae < baseline_mae:
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(x, y)
    return {"model": model, "mae": mae, "baseline_mae": baseline_mae,
            "rows": len(sample), "residuals": np.asarray(residuals, dtype=float),
            "cr_min": float(sample.cr.min()), "cr_max": float(sample.cr.max())}


def add_capital_gain_forecasts(forecasts: pd.DataFrame, history: pd.DataFrame | None) -> pd.DataFrame:
    """Estimate E[ΔCR] by integrating score uncertainty and OOF residuals."""
    out = forecasts.copy()
    for col in ("expected_plusvalenza", "plusvalenza_p10", "plusvalenza_p90",
                "plusvalenza_prob_gain", "plusvalenza_prob_loss", "plusvalenza_prob_flat",
                "plusvalenza_prob_gain_1cr"):
        out[col] = np.nan
    out["plusvalenza_cv_mae"] = np.nan
    out["plusvalenza_baseline_mae"] = np.nan
    out["capital_gain_delta_cr_mae_walk_forward"] = np.nan
    out["capital_gain_delta_cr_mae_baseline"] = np.nan
    out["capital_gain_metric_target"] = "official_plus_delta_cr"
    out["capital_gain_metric_unit"] = "CR per player per Dunkest gameweek"
    out["capital_gain_metric_validation"] = "season/gameweek walk-forward"
    out["capital_gain_metric_baseline"] = "training-window mean ΔCR"
    out["plusvalenza_training_rows"] = 0
    out["plusvalenza_source"] = "unavailable"
    out["plusvalenza_cost_supported"] = False
    fitted = fit_capital_gain_model(history)
    model, residuals = fitted["model"], fitted["residuals"]
    if model is None or len(residuals) == 0:
        return out
    cr = pd.to_numeric(out.get("cr"), errors="coerce")
    supported = cr.between(fitted["cr_min"], fitted["cr_max"])
    expected_score = pd.to_numeric(out["expected_pdk"], errors="coerce")
    q10 = pd.to_numeric(out.get("p10", expected_score), errors="coerce").fillna(expected_score)
    q50 = pd.to_numeric(out.get("p50", expected_score), errors="coerce").fillna(expected_score)
    q90 = pd.to_numeric(out.get("p90", expected_score), errors="coerce").fillna(expected_score)
    ordered_quantiles = np.sort(np.column_stack([q10, q50, q90]), axis=1)
    q10, q50, q90 = (pd.Series(ordered_quantiles[:, i], index=out.index) for i in range(3))
    # Piecewise-linear quantile integration across P10/P50/P90; same empirical
    # OOF residual pool is then added to preserve the observed score-to-price noise.
    quantiles = np.linspace(0.0, 1.0, 41)
    base_scores = np.where(quantiles <= .5,
                           q10.to_numpy()[:, None] + (q50-q10).to_numpy()[:, None] * (quantiles[None, :] / .5),
                           q50.to_numpy()[:, None] + (q90-q50).to_numpy()[:, None] * ((quantiles[None, :]-.5) / .5))
    n_resid = min(101, len(residuals))
    sampled_residuals = np.quantile(residuals, np.linspace(0, 1, n_resid))
    gains = []
    for residual in sampled_residuals:
        scores = np.maximum(base_scores + residual, 0.0).reshape(-1)
        cr_repeated = np.repeat(cr.to_numpy(), len(quantiles))
        score_repeated = scores
        predicted = model.predict(_features(pd.Series(score_repeated), pd.Series(cr_repeated)))
        gains.append(predicted.reshape(len(out), len(quantiles)))
    # Observed Dunkest market changes are quantized to 0.1 CR. Keep each
    # simulated outcome on that grid before deriving event probabilities.
    distribution = np.round(np.concatenate(gains, axis=1) * 10.0) / 10.0
    dist = pd.DataFrame(distribution, index=out.index)
    out.loc[supported, "expected_plusvalenza"] = dist.loc[supported].mean(axis=1)
    out.loc[supported, "plusvalenza_p10"] = dist.loc[supported].quantile(.10, axis=1)
    out.loc[supported, "plusvalenza_p90"] = dist.loc[supported].quantile(.90, axis=1)
    out.loc[supported, "plusvalenza_prob_gain"] = (dist.loc[supported] > 0).mean(axis=1)
    out.loc[supported, "plusvalenza_prob_loss"] = (dist.loc[supported] < 0).mean(axis=1)
    out.loc[supported, "plusvalenza_prob_flat"] = (dist.loc[supported] == 0).mean(axis=1)
    out.loc[supported, "plusvalenza_prob_gain_1cr"] = (dist.loc[supported] >= 1.0).mean(axis=1)
    out["plusvalenza_cv_mae"] = fitted["mae"]
    out["plusvalenza_baseline_mae"] = fitted["baseline_mae"]
    out["capital_gain_delta_cr_mae_walk_forward"] = fitted["mae"]
    out["capital_gain_delta_cr_mae_baseline"] = fitted["baseline_mae"]
    out["plusvalenza_training_rows"] = fitted["rows"]
    out["plusvalenza_cost_supported"] = supported
    out["plusvalenza_source"] = np.where(supported, "official_score_cost_walk_forward", "outside_cost_support")
    return out
