import pandas as pd
import pytest

from dunkest.rules.coach import (
    coach_coefficient,
    coach_points_from_game,
    coach_points_from_outcomes,
)
from dunkest.rules.pdk import pdk_from_boxscore_row


def test_pdk_basic_scoring():
    row = pd.Series(
        {
            "PTS": 20,
            "OREB": 1,
            "DREB": 4,
            "AST": 5,
            "STL": 1,
            "BLK": 0,
            "TOV": 2,
            "FGM": 8,
            "FGA": 15,
            "FTM": 2,
            "FTA": 3,
            "FG3M": 2,
        }
    )
    score = pdk_from_boxscore_row(row, team_won=False)
    assert score > 20


def test_pdk_matches_official_stat_weights_shot_misses_threes_and_team_win():
    row = pd.Series({
        "PTS": 15, "OREB": 2, "DREB": 5, "AST": 4, "STL": 1,
        "BLK": 2, "BLKA": 1, "TOV": 3, "FGM": 5, "FGA": 10,
        "FTM": 3, "FTA": 4, "FG3M": 4, "START_POSITION": "G",
    })

    # Base 22 + 4 made threes + 1 starter point, then the 5% team-win bonus.
    assert pdk_from_boxscore_row(row, team_won=True) == pytest.approx(27.0 * 1.05)


def test_pdk_accounts_for_blocks_against_starter_and_quadruple_double():
    row = pd.Series(
        {
            "PTS": 10, "OREB": 10, "DREB": 0, "AST": 10,
            "STL": 10, "BLK": 10, "BLKA": 2, "TOV": 0,
            "FGM": 0, "FGA": 0, "FTM": 0, "FTA": 0,
            "FG3M": 0, "START_POSITION": "G",
        }
    )
    # Base 10 + 12.5 + 15 + 15 + 15, quad-double +50,
    # starter +1 and blocks against -1.
    assert pdk_from_boxscore_row(row, team_won=False) == 117.5


def test_coach_coefficient_positive():
    assert coach_coefficient(5.0, True, True) == 0.87
    assert coach_coefficient(5.0, True, False) == pytest.approx(1 / 0.87)


def test_coach_points_win():
    pts = coach_points_from_game(110, 100, 10.0, 8.0)
    assert pts > 0


def test_vectorized_coach_score_matches_rule_thresholds_and_overtime():
    assert coach_points_from_game(122, 94, 10.0, 5.0) == pytest.approx(38.0 * 0.87)
    assert coach_points_from_game(94, 122, 10.0, 5.0) == pytest.approx(-26.0 / 0.87)
    assert coach_points_from_game(102, 100, 8.0, 8.0, overtime=True) == 18.0
    assert coach_points_from_game(100, 102, 8.0, 8.0, overtime=True) == -10.0
    values = coach_points_from_outcomes(
        [122, 94, 102, 100], [94, 122, 100, 102], 10.0, 5.0,
        [False, False, True, True],
    )
    assert values.tolist() == pytest.approx([
        38.0 * 0.87, -26.0 / 0.87, 18.0 * 0.87, -10.0 / 0.87
    ])
