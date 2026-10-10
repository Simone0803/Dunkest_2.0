import numpy as np
import pandas as pd

from dunkest.backtest.walk_forward import _realized_player_scores


def test_realized_player_scores_excludes_missing_and_nonfinite_outcomes():
    frame = pd.DataFrame(
        {
            "player_name": ["Player One", "Player Two", "Player Three", ""],
            "actual_pdk": [12.5, np.nan, np.inf, 8.0],
            "gameweek_stats_available": [True, True, True, True],
        }
    )

    assert _realized_player_scores(frame) == {"player one": 12.5}


def test_realized_player_scores_excludes_conflicting_duplicate_identities():
    frame = pd.DataFrame(
        {
            "player_name": ["Player One", "PLAYER ONE", "Player Two"],
            "actual_pdk": [12.0, 14.0, 9.0],
            "gameweek_stats_available": [True, True, True],
        }
    )

    assert _realized_player_scores(frame) == {"player two": 9.0}


def test_realized_player_scores_requires_available_gameweek_stats():
    frame = pd.DataFrame(
        {
            "player_name": ["Player One"],
            "actual_pdk": [12.0],
            "gameweek_stats_available": [False],
        }
    )

    assert _realized_player_scores(frame) == {}


from dunkest.backtest.walk_forward import (
    _mask_post_match_market_outcomes,
    _realized_coach_scores,
)
from dunkest.rules.coach import coach_points_from_game


def test_mask_post_match_market_outcomes_preserves_pregame_market_fields():
    frame = pd.DataFrame({
        "player_name": ["Player One"],
        "cr": [12.5],
        "pdk": [15.0],
        "prior_pdk": [14.0],
        "actual_pdk": [18.0],
        "official_plusvalenza": [1.0],
        "plus": [2.0],
        "gameweek_stats_available": [True],
    })

    masked = _mask_post_match_market_outcomes(frame)

    assert masked.loc[0, "cr"] == 12.5
    for column in ("pdk", "prior_pdk", "actual_pdk", "official_plusvalenza", "plus", "gameweek_stats_available"):
        assert pd.isna(masked.loc[0, column])
    assert frame.loc[0, "actual_pdk"] == 18.0


def test_realized_coach_scores_uses_archived_credits_and_final_box_score():
    coach_market = pd.DataFrame([{
        "coach": "Coach Home", "team": "BOS", "coach_cr": 10.0,
        "opponent": "NYK", "opponent_coach_cr": 8.0, "nba_game_id": "001",
    }])
    team_logs = pd.DataFrame([
        {"Game_ID": "001", "TEAM_ABBREVIATION": "BOS", "PTS": 110, "MIN": 240},
        {"Game_ID": "001", "TEAM_ABBREVIATION": "NYK", "PTS": 100, "MIN": 240},
    ])
    games = pd.DataFrame([{
        "nba_game_id": "001", "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK",
    }])

    scores = _realized_coach_scores(coach_market, team_logs, games)

    assert scores == {
        "coach home": coach_points_from_game(110, 100, 10.0, 8.0, False)
    }


def test_realized_coach_scores_does_not_guess_when_opponent_credit_is_missing():
    coach_market = pd.DataFrame([{
        "coach": "Coach Home", "team": "BOS", "coach_cr": 10.0,
        "opponent": "NYK", "opponent_coach_cr": np.nan, "nba_game_id": "001",
    }])
    team_logs = pd.DataFrame([
        {"Game_ID": "001", "TEAM_ABBREVIATION": "BOS", "PTS": 110, "MIN": 240},
        {"Game_ID": "001", "TEAM_ABBREVIATION": "NYK", "PTS": 100, "MIN": 240},
    ])
    games = pd.DataFrame([{
        "nba_game_id": "001", "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK",
    }])

    assert _realized_coach_scores(coach_market, team_logs, games) == {}
