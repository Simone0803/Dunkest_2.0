import numpy as np
import pandas as pd

from dunkest.models.rookie_prior import load_college_rookie_priors


def _historical_and_current_classes() -> pd.DataFrame:
    rows = []
    for year in range(2014, 2022):
        for index in range(12):
            minutes = 18.0 + index * 1.2 + (index % 3)
            ppg = 0.30 * minutes + index * 0.2
            games = 40 + index
            rows.append({
                "player_name": f"Player {year}-{index}",
                "draft_year": year,
                "position": ("G", "F", "C")[index % 3],
                "age": 19.0 + index * 0.1,
                "draft_pick": index + 1,
                "pace": 68.0 + (index % 5),
                "games": 30 + index,
                "starts": 10 + index,
                "minutes_per_game": minutes,
                "points_per_game": ppg,
                "rebounds_per_game": 4.0 + index * 0.2,
                "assists_per_game": 2.0 + index * 0.1,
                "steals_per_game": 0.8,
                "blocks_per_game": 0.4,
                "turnovers_per_game": 1.5,
                "field_goals_made_per_game": ppg * 0.4,
                "field_goals_attempted_per_game": ppg * 0.85,
                "free_throws_made_per_game": 2.0,
                "free_throws_attempted_per_game": 2.5,
                "three_pointers_made_per_game": 1.0,
                "nba_rookie_games": games,
                "nba_rookie_minutes": games * (8.0 + minutes * 0.55),
                "nba_pdk_per_min": 0.25 + 0.30 * ppg / minutes,
            })
    for index in range(3):
        rows.append({
            "player_name": f"Current Rookie {index}",
            "draft_year": 2022,
            "position": ("G", "F", "C")[index],
            "age": 19.0,
            "draft_pick": index + 1,
            "pace": 68.0,
            "games": 32,
            "starts": 20,
            "minutes_per_game": 27.0 + index,
            "points_per_game": 10.0 + index,
            "rebounds_per_game": 5.0,
            "assists_per_game": 3.0,
            "steals_per_game": 0.8,
            "blocks_per_game": 0.4,
            "turnovers_per_game": 1.5,
            "field_goals_made_per_game": 4.0,
            "field_goals_attempted_per_game": 9.0,
            "free_throws_made_per_game": 2.0,
            "free_throws_attempted_per_game": 2.5,
            "three_pointers_made_per_game": 1.0,
            "nba_rookie_games": np.nan,
            "nba_rookie_minutes": np.nan,
            "nba_pdk_per_min": np.nan,
        })
    return pd.DataFrame(rows)


def test_rookie_minutes_prior_uses_past_classes_and_passes_temporal_baseline(tmp_path):
    source = tmp_path / "rookie_college.csv"
    _historical_and_current_classes().to_csv(source, index=False)

    priors = load_college_rookie_priors(source)

    assert len(priors) == 3
    assert priors["college_projected_minutes_per_game"].between(0.0, 40.0).all()
    assert priors["college_minutes_cv_mae"].nunique() == 1
    assert priors["college_minutes_baseline_cv_mae"].nunique() == 1
    assert priors["college_minutes_cv_mae"].iloc[0] < priors["college_minutes_baseline_cv_mae"].iloc[0]
    assert priors["college_minutes_prior_weight"].between(0.0, 0.35).all()
