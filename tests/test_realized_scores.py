import numpy as np
import pandas as pd

from dunkest.backtest.walk_forward import _archived_coach_scores, _realized_player_scores


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


def test_archived_coach_scores_excludes_conflicting_normalized_identities():
    frame = pd.DataFrame({
        "coach": ["Coach A", "COACH A", "Coach B"],
        "nba_game_id": ["game-1", "game-2", "game-1"],
        "actual_coach_pdk": [10.0, 10.0, 8.0],
    })

    assert _archived_coach_scores(frame) == {"coach a": 10.0, "coach b": 8.0}

    frame.loc[1, "actual_coach_pdk"] = 12.0
    assert _archived_coach_scores(frame) == {"coach b": 8.0}
