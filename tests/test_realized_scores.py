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

    assert _realized_player_scores(frame) == {"playerone": 12.5}


def test_realized_player_scores_excludes_conflicting_duplicate_identities():
    frame = pd.DataFrame(
        {
            "player_name": ["Player One", "PLAYER ONE", "Player Two"],
            "actual_pdk": [12.0, 14.0, 9.0],
            "gameweek_stats_available": [True, True, True],
        }
    )

    assert _realized_player_scores(frame) == {"playertwo": 9.0}


def test_realized_player_scores_requires_available_gameweek_stats():
    frame = pd.DataFrame(
        {
            "player_name": ["Player One"],
            "actual_pdk": [12.0],
            "gameweek_stats_available": [False],
        }
    )

    assert _realized_player_scores(frame) == {}
