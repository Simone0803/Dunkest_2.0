import numpy as np
import pandas as pd
import pytest

from dunkest.evaluation.minutes_recency import (
    recency_sample_weights,
    validate_feature_names,
    validate_temporal_fold,
)


def test_recency_weights_are_positive_and_half_life_is_fixed():
    origin = pd.Timestamp("2025-07-01T00:00:00Z")
    dates = pd.Series([
        origin - pd.Timedelta(days=2 * 365.2425),
        origin - pd.Timedelta(days=365.2425),
    ])

    weights = recency_sample_weights(dates, as_of=origin, half_life_years=2.0)

    assert np.all(weights > 0)
    assert weights.iloc[0] == pytest.approx(0.5)
    assert weights.iloc[1] == pytest.approx(2 ** -0.5)


def test_recency_weights_reject_training_rows_after_fold_origin():
    with pytest.raises(ValueError, match="on/after the fold origin"):
        recency_sample_weights(
            pd.Series(pd.to_datetime(["2025-07-02T00:00:00Z"])),
            as_of="2025-07-01T00:00:00Z",
        )


def test_temporal_fold_requires_train_dates_before_test_and_past_feature_dates():
    train = pd.DataFrame({
        "game_date": pd.to_datetime(["2024-10-01T00:00:00Z"]),
        "prior_nba_history_game_date": pd.to_datetime(["2024-09-29T00:00:00Z"]),
    })
    test = pd.DataFrame({
        "game_date": pd.to_datetime(["2024-10-02T00:00:00Z"]),
        "prior_nba_history_game_date": pd.to_datetime(["2024-10-01T00:00:00Z"]),
    })

    result = validate_temporal_fold(train, test)

    assert result["train_rows"] == 1
    assert result["test_rows"] == 1
    bad_train = train.assign(game_date=pd.to_datetime(["2024-10-02T00:00:00Z"]))
    with pytest.raises(ValueError, match="training dates must precede"):
        validate_temporal_fold(bad_train, test)
    bad_test = test.assign(prior_nba_history_game_date=pd.to_datetime(["2024-10-02T00:00:00Z"]))
    with pytest.raises(ValueError, match="history reaches its target"):
        validate_temporal_fold(train, bad_test)


def test_feature_guard_rejects_target_game_minutes_or_pdk():
    validate_feature_names(["lag1_nba_min", "prev5_pdk_mean"])
    with pytest.raises(ValueError, match="target labels cannot be model features"):
        validate_feature_names(["lag1_nba_min", "target_minutes"])
