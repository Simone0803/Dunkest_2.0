import pandas as pd
import pytest

from dunkest.features.builder import _attach_current_season_form
from dunkest.models.predictor import _blend_current_season_rate


def test_current_season_rate_uses_target_fixture_season_and_excludes_future_games():
    logs = pd.DataFrame([
        {"PLAYER_NAME": "Player", "GAME_DATE": "2025-11-01", "PDK": 20.0, "MIN": 30.0},
        {"PLAYER_NAME": "Player", "GAME_DATE": "2026-01-01", "PDK": 25.0, "MIN": 30.0},
        {"PLAYER_NAME": "Player", "GAME_DATE": "2026-10-22", "PDK": 40.0, "MIN": 30.0},
        # This row is deliberately after the target fixture and must not leak.
        {"PLAYER_NAME": "Player", "GAME_DATE": "2026-10-28", "PDK": 1000.0, "MIN": 30.0},
    ])
    features = pd.DataFrame([{
        "PLAYER_NAME": "Player",
        "is_inference": True,
        "NBA_GAME_DATETIME_UTC": pd.Timestamp("2026-10-25"),
    }])

    actual = _attach_current_season_form(features, logs, "2026-10-20").iloc[0]

    assert actual["current_season_games"] == 1
    assert actual["pdk_per_min_current_season"] == pytest.approx(40 / 30)
    assert actual["prior_seasons_games"] == 2
    assert actual["pdk_per_min_prior_seasons"] == pytest.approx(45 / 60)


def test_current_season_weight_grows_gradually_with_evidence():
    one_game, one_weight = _blend_current_season_rate(0.75, 1.50, 1)
    ten_games, ten_weight = _blend_current_season_rate(0.75, 1.50, 10)
    thirty_games, thirty_weight = _blend_current_season_rate(0.75, 1.50, 30)

    assert one_weight == pytest.approx(1 / 9)
    assert ten_weight == pytest.approx(10 / 18)
    assert thirty_weight == pytest.approx(30 / 38)
    assert 0.75 < one_game < ten_games < thirty_games < 1.50


def test_current_season_rate_falls_back_to_prior_when_current_sample_is_empty():
    rate, weight = _blend_current_season_rate(0.82, 1.40, 0)
    assert rate == pytest.approx(0.82)
    assert weight == 0.0


def test_current_season_without_prior_keeps_rate_but_reports_weight():
    rate, weight = _blend_current_season_rate(float("nan"), 1.20, 1)
    assert rate == pytest.approx(1.20)
    assert weight == pytest.approx(1 / 9)
