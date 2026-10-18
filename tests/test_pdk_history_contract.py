import numpy as np
import pandas as pd
import pytest

from dunkest.features.builder import _rolling_features
from dunkest.features.pdk_history import PDK_HISTORY_FEATURES, summarize_pdk_history
from dunkest.models.multiseason_training import adapt_certified_training_rows
from dunkest.models.predictor import FEATURE_COLS


def _matched_history():
    dates = pd.date_range("2024-10-20", periods=4, freq="2D")
    official = [10.0, 20.0, 30.0, 40.0]
    minutes = [30.0, 0.0, 20.0, 40.0]
    opponents = ["BOS", "BOS", "MIA", "BOS"]
    source = pd.DataFrame({
        "season_label": ["2024-25"] * 4,
        "game_date": dates,
        "gameId": [f"d-{i}" for i in range(4)],
        "dunkest_player_id": ["p1"] * 4,
        "dunkest_player_name": ["Player"] * 4,
        "target_pdk": official,
        "history_games_before_target": [0, 1, 2, 3],
        "opponentTeamCode": opponents,
        "nba_GAME_ID": [f"nba-{i}" for i in range(4)],
        "nba_PLAYER_ID": [99] * 4,
        "nba_match_status": ["matched_player_date_opponent"] * 4,
        "prev3_pdk_mean": [np.nan, 10.0, 15.0, 20.0],
        "prev5_pdk_mean": [np.nan, 10.0, 15.0, 20.0],
        "prev10_pdk_mean": [np.nan, 10.0, 15.0, 20.0],
        "prev5_pdk_std": [np.nan, 0.0, 5.0, 8.16],
        "prev5_nba_min_mean": [np.nan, 30.0, 15.0, 16.67],
        "rest_days_from_nba_logs": [3.0] * 4,
    })
    minutes_labels = pd.DataFrame({
        "nba_GAME_ID": [f"nba-{i}" for i in range(4)],
        "nba_PLAYER_ID": [99] * 4,
        "nba_MIN": minutes,
        "nba_match_status": ["matched_player_date_opponent"] * 4,
    })
    logs = pd.DataFrame({
        "PLAYER_NAME": ["Player"] * 4,
        "GAME_DATE": dates,
        "GAME_ID": [f"nba-{i}" for i in range(4)],
        "SEASON_YEAR": ["2024-25"] * 4,
        "OPPONENT": opponents,
        "PDK": [110.0, 120.0, 130.0, 140.0],
        "PDK_OFFICIAL_VALID": official,
        "MIN": minutes,
    })
    return source, minutes_labels, logs


def test_training_and_inference_use_same_four_official_only_feature_definitions():
    source, minutes_labels, logs = _matched_history()
    training = adapt_certified_training_rows(
        source, minimum_rows=1, minutes_labels=minutes_labels
    ).iloc[-1]
    inference = _rolling_features(logs, [3, 5, 10]).iloc[3]

    assert tuple(PDK_HISTORY_FEATURES) == (
        "pdk_season_mean", "pdk_per_min_season",
        "player_opp_pdk_per_min", "player_opp_games",
    )
    assert all(feature in FEATURE_COLS for feature in PDK_HISTORY_FEATURES)
    for feature in PDK_HISTORY_FEATURES:
        assert inference[feature] == pytest.approx(training[feature], nan_ok=True), feature
        assert pd.api.types.is_number(training[feature])
    # Three prior official scores average to 20; the zero-minute game counts
    # toward the score mean but not either rate denominator.
    assert training["pdk_season_mean"] == pytest.approx(20.0)
    assert training["pdk_per_min_season"] == pytest.approx(40.0 / 50.0)
    # One prior eligible BOS game, shrunk toward the 0.8 official PDK/min base.
    assert training["player_opp_pdk_per_min"] == pytest.approx((10.0 + 120 * 0.8) / 150)
    assert training["player_opp_games"] == pytest.approx(1.0)


def test_four_features_exclude_current_and_future_targets_and_minutes():
    _, _, logs = _matched_history()
    original = _rolling_features(logs, [3, 5, 10]).iloc[3]
    as_of = summarize_pdk_history(
        logs,
        as_of=logs.loc[3, "GAME_DATE"],
        target_season=2024,
        opponent="BOS",
    )
    for feature in PDK_HISTORY_FEATURES:
        assert as_of[feature] == pytest.approx(original[feature], nan_ok=True)
    changed = logs.copy()
    changed.loc[3, ["PDK_OFFICIAL_VALID", "MIN"]] = [999.0, 1.0]
    after_change = _rolling_features(changed, [3, 5, 10]).iloc[3]
    for feature in PDK_HISTORY_FEATURES:
        assert after_change[feature] == pytest.approx(original[feature], nan_ok=True)


def test_official_only_features_do_not_fall_back_to_proxy_and_handle_missing_minutes():
    logs = pd.DataFrame([
        {"PLAYER_NAME": "Player", "GAME_DATE": "2024-10-20", "GAME_ID": "1",
         "SEASON_YEAR": "2024-25", "OPPONENT": "BOS", "PDK": 50.0,
         "PDK_OFFICIAL_VALID": np.nan, "MIN": 30.0},
        {"PLAYER_NAME": "Player", "GAME_DATE": "2024-10-22", "GAME_ID": "2",
         "SEASON_YEAR": "2024-25", "OPPONENT": "MIA", "PDK": 60.0,
         "PDK_OFFICIAL_VALID": 12.0, "MIN": np.nan},
        {"PLAYER_NAME": "Player", "GAME_DATE": "2024-10-24", "GAME_ID": "3",
         "SEASON_YEAR": "2024-25", "OPPONENT": "NYK", "PDK": 70.0,
         "PDK_OFFICIAL_VALID": 15.0, "MIN": 0.0},
    ])
    actual = _rolling_features(logs, [3]).iloc[2]
    assert actual["pdk_season_mean"] == pytest.approx(12.0)
    assert pd.isna(actual["pdk_per_min_season"])
    assert pd.isna(actual["player_opp_pdk_per_min"])
    assert actual["player_opp_games"] == 0.0

    no_official = logs.iloc[[0]].drop(columns="PDK_OFFICIAL_VALID")
    no_history = _rolling_features(no_official, [3]).iloc[-1]
    assert pd.isna(no_history["pdk_season_mean"])
    assert pd.isna(no_history["pdk_per_min_season"])
    assert pd.isna(no_history["player_opp_pdk_per_min"])
    assert no_history["player_opp_games"] == 0.0


def test_opponent_without_prior_games_uses_base_rate_and_reports_zero_games():
    _, _, logs = _matched_history()
    inference = _rolling_features(logs.iloc[:3].assign(OPPONENT="NYK"), [3]).iloc[-1]
    assert inference["player_opp_pdk_per_min"] == pytest.approx(0.8)
    assert inference["player_opp_games"] == 0.0
