"""Strict helpers for paired, temporally valid expected-minutes evaluations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def pair_minutes_forecasts(
    forecasts: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    keys: tuple[str, ...],
    game_date_col: str = "game_date",
    forecast_at_col: str = "forecast_at_utc",
    feature_max_at_col: str = "feature_max_at_utc",
    train_max_date_col: str | None = "train_max_date",
) -> pd.DataFrame:
    """Return identical player-game rows with both forecasts and valid labels.

    The input frames are long-lived-independent row sets: ``forecasts`` has one
    row per player/game and both prediction columns; ``outcomes`` has one row
    per same player/game. Duplicate identities or temporal leakage fail closed.
    """
    required_forecasts = set(keys) | {
        game_date_col, forecast_at_col, feature_max_at_col,
        "minutes_hybrid", "minutes_hgb",
    }
    required_outcomes = set(keys) | {"minutes_actual"}
    missing = required_forecasts - set(forecasts.columns)
    if missing:
        raise ValueError(f"forecast columns missing: {sorted(missing)}")
    missing = required_outcomes - set(outcomes.columns)
    if missing:
        raise ValueError(f"outcome columns missing: {sorted(missing)}")
    if forecasts.duplicated(list(keys)).any():
        raise ValueError("duplicate forecast player-game keys")
    if outcomes.duplicated(list(keys)).any():
        raise ValueError("duplicate outcome player-game keys")

    f = forecasts.copy()
    f[forecast_at_col] = pd.to_datetime(f[forecast_at_col], utc=True, errors="coerce")
    f[feature_max_at_col] = pd.to_datetime(f[feature_max_at_col], utc=True, errors="coerce")
    f[game_date_col] = pd.to_datetime(f[game_date_col], utc=True, errors="coerce")
    if f[[forecast_at_col, feature_max_at_col, game_date_col]].isna().any().any():
        raise ValueError("forecast, feature, and game timestamps must be present")
    if (f[feature_max_at_col] > f[forecast_at_col]).any():
        raise ValueError("post-forecast feature timestamp detected")
    if (f[forecast_at_col] >= f[game_date_col]).any():
        raise ValueError("forecast is not earlier than target game")
    if train_max_date_col and train_max_date_col in f:
        train_date = pd.to_datetime(f[train_max_date_col], utc=True, errors="coerce")
        if train_date.isna().any() or (train_date >= f[forecast_at_col]).any():
            raise ValueError("training data reaches forecast time")

    joined = f.merge(outcomes, on=list(keys), how="inner", validate="one_to_one")
    numeric = ["minutes_hybrid", "minutes_hgb", "minutes_actual"]
    joined = joined.dropna(subset=numeric).copy()
    return joined.sort_values([game_date_col, *keys]).reset_index(drop=True)


def minutes_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | int]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape or actual.size == 0:
        raise ValueError("actual and predicted must be non-empty arrays of equal shape")
    error = predicted - actual
    return {
        "n": int(actual.size),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": float(np.mean(error)),
    }


def paired_game_bootstrap_delta(
    frame: pd.DataFrame,
    *,
    game_col: str = "nba_game_id",
    actual_col: str = "minutes_actual",
    hybrid_col: str = "minutes_hybrid",
    hgb_col: str = "minutes_hgb",
    n_bootstrap: int = 10_000,
    seed: int = 20_261_024,
) -> dict[str, list[float]]:
    """95% percentile CIs for HGB-minus-hybrid metrics by game-cluster bootstrap."""
    if frame.empty or frame[game_col].isna().any():
        raise ValueError("paired rows and game identifiers are required")
    games = frame[game_col].drop_duplicates().to_numpy()
    if len(games) < 2:
        raise ValueError("at least two game clusters are required")
    rng = np.random.default_rng(seed)
    game_stats = []
    for game in games:
        group = frame.loc[frame[game_col] == game]
        actual = group[actual_col].to_numpy(float)
        hybrid_error = group[hybrid_col].to_numpy(float) - actual
        hgb_error = group[hgb_col].to_numpy(float) - actual
        game_stats.append(
            [
                len(group),
                np.abs(hybrid_error).sum(),
                np.square(hybrid_error).sum(),
                hybrid_error.sum(),
                np.abs(hgb_error).sum(),
                np.square(hgb_error).sum(),
                hgb_error.sum(),
            ]
        )
    stats = np.asarray(game_stats, dtype=float)
    counts = rng.multinomial(len(games), np.full(len(games), 1.0 / len(games)), size=n_bootstrap)
    weighted = counts @ stats
    n = weighted[:, 0]
    hybrid_mae = weighted[:, 1] / n
    hybrid_rmse = np.sqrt(weighted[:, 2] / n)
    hybrid_bias = weighted[:, 3] / n
    hgb_mae = weighted[:, 4] / n
    hgb_rmse = np.sqrt(weighted[:, 5] / n)
    hgb_bias = weighted[:, 6] / n
    delta = np.column_stack(
        [hgb_mae - hybrid_mae, hgb_rmse - hybrid_rmse, hgb_bias - hybrid_bias]
    )
    bounds = np.quantile(delta, [0.025, 0.975], axis=0)
    return {metric: [float(bounds[0, j]), float(bounds[1, j])] for j, metric in enumerate(("mae", "rmse", "bias"))}
