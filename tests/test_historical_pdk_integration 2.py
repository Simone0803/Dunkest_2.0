import numpy as np
import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.models.historical_pdk import _nba_features, _pdk_features


def test_historical_pdk_lags_use_only_targets_strictly_before_prediction_date():
    history = pd.DataFrame({
        "game_date": pd.to_datetime(["2025-10-20", "2025-10-25", "2025-11-01"]),
        "target_pdk": [10.0, 20.0, 99.0],
    })
    features = _pdk_features(history, pd.Timestamp("2025-11-01"))
    assert features["history_games_before_target"] == 2.0
    assert features["lag1_pdk"] == 20.0
    assert features["lag2_pdk"] == 10.0
    assert features["prev3_pdk_mean"] == 15.0


def test_historical_nba_lags_exclude_same_day_and_future_games():
    history = pd.DataFrame({
        "_date": pd.to_datetime(["2025-10-20", "2025-10-25", "2025-11-01"]),
        "_game_id": ["a", "b", "c"],
        "MIN": [10.0, 20.0, 99.0],
        "PTS": [5.0, 15.0, 99.0],
    })
    features = _nba_features(history, pd.Timestamp("2025-11-01"))
    assert features["nba_history_games_before_target"] == 2.0
    assert features["lag1_nba_min"] == 20.0
    assert features["lag2_nba_min"] == 10.0
    assert features["prev3_nba_pts_mean"] == 10.0
    assert features["rest_days_from_nba_logs"] == 7.0


def test_historical_pdk_blend_weight_is_bounded():
    assert Settings(historical_pdk_blend_weight=0.0).historical_pdk_blend_weight == 0.0
    assert Settings(historical_pdk_blend_weight=0.2).historical_pdk_blend_weight == 0.2
    with pytest.raises(ValueError, match="historical_pdk_blend_weight"):
        Settings(historical_pdk_blend_weight=1.1)
    with pytest.raises(ValueError, match="historical_pdk_blend_weight"):
        Settings(historical_pdk_blend_weight=-0.1)


def test_historical_feature_helpers_return_missing_values_for_empty_history():
    pdk = _pdk_features(pd.DataFrame(columns=["game_date", "target_pdk"]), pd.Timestamp("2026-10-20"))
    nba = _nba_features(pd.DataFrame(), pd.Timestamp("2026-10-20"))
    assert pdk["history_games_before_target"] == 0.0
    assert np.isnan(pdk["lag1_pdk"])
    assert nba["nba_history_games_before_target"] == 0.0
    assert np.isnan(nba["lag1_nba_min"])
