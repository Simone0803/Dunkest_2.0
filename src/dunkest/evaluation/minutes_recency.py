"""Small, deterministic helpers for past-only minutes recency experiments."""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGET_ONLY_COLUMNS = {
    "target_minutes", "target_min", "nba_MIN", "MIN", "target_pdk",
    "target_pdk_official", "pdk_official", "minutes_actual",
}


def validate_feature_names(feature_names: list[str] | tuple[str, ...]) -> None:
    """Reject current-game labels accidentally included in the input matrix."""
    leaked = sorted(set(feature_names) & TARGET_ONLY_COLUMNS)
    if leaked:
        raise ValueError(f"target labels cannot be model features: {leaked}")


def recency_sample_weights(
    game_dates: pd.Series,
    *,
    as_of: object,
    half_life_years: float = 2.0,
) -> pd.Series:
    """Return exponential time-decay weights; reject rows after the fold origin."""
    if not np.isfinite(half_life_years) or half_life_years <= 0:
        raise ValueError("half_life_years must be finite and positive")
    dates = pd.to_datetime(game_dates, utc=True, errors="coerce")
    origin = pd.to_datetime(as_of, utc=True, errors="coerce")
    if pd.isna(origin) or dates.isna().any():
        raise ValueError("training dates and fold origin must be valid timestamps")
    age_years = (origin - dates).dt.total_seconds() / (365.2425 * 24 * 3600)
    if (age_years < 0).any():
        raise ValueError("training data contains a game on/after the fold origin")
    weights = np.exp2(-age_years / float(half_life_years))
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("recency weights must be finite and positive")
    return pd.Series(weights, index=game_dates.index, name="sample_weight")


def validate_temporal_fold(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    date_col: str = "game_date",
    prior_feature_date_col: str = "prior_nba_history_game_date",
) -> dict[str, str | int]:
    """Fail closed on unsorted/overlapping folds or target-date feature history."""
    if train.empty or test.empty:
        raise ValueError("walk-forward training and test folds must be non-empty")
    train_dates = pd.to_datetime(train[date_col], utc=True, errors="coerce")
    test_dates = pd.to_datetime(test[date_col], utc=True, errors="coerce")
    if train_dates.isna().any() or test_dates.isna().any():
        raise ValueError("walk-forward rows need valid game dates")
    if train_dates.max() >= test_dates.min():
        raise ValueError("training dates must precede every test date")
    if prior_feature_date_col in train:
        prior = pd.to_datetime(train[prior_feature_date_col], utc=True, errors="coerce")
        has_prior = prior.notna()
        if (prior.loc[has_prior] >= train_dates.loc[has_prior]).any():
            raise ValueError("training feature history reaches its target game")
    if prior_feature_date_col in test:
        prior = pd.to_datetime(test[prior_feature_date_col], utc=True, errors="coerce")
        has_prior = prior.notna()
        if (prior.loc[has_prior] >= test_dates.loc[has_prior]).any():
            raise ValueError("test feature history reaches its target game")
    return {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_max_date_utc": train_dates.max().isoformat(),
        "test_min_date_utc": test_dates.min().isoformat(),
    }
