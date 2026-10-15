from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_coach_win_probability_walk_forward_2018-26_v1.py"
SPEC = importlib.util.spec_from_file_location("coach_probability_walk_forward", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _games(same_day_regular_home_score: int = 110) -> pd.DataFrame:
    rows = [
        # A completed earlier game supplies the only historical evidence.
        {"SEASON": "2024-25", "GAME_ID": "old1", "GAME_DATE": "2024-10-20", "MATCHUP": "AAA vs. BBB", "TEAM_ABBREVIATION": "AAA", "PTS": 110},
        {"SEASON": "2024-25", "GAME_ID": "old1", "GAME_DATE": "2024-10-20", "MATCHUP": "BBB @ AAA", "TEAM_ABBREVIATION": "BBB", "PTS": 100},
        # Normal home game and a neutral-site game on the same date.
        {"SEASON": "2024-25", "GAME_ID": "new1", "GAME_DATE": "2024-10-21", "MATCHUP": "AAA vs. CCC", "TEAM_ABBREVIATION": "AAA", "PTS": same_day_regular_home_score},
        {"SEASON": "2024-25", "GAME_ID": "new1", "GAME_DATE": "2024-10-21", "MATCHUP": "CCC @ AAA", "TEAM_ABBREVIATION": "CCC", "PTS": 99},
        {"SEASON": "2024-25", "GAME_ID": "new2", "GAME_DATE": "2024-10-21", "MATCHUP": "DDD @ EEE", "TEAM_ABBREVIATION": "DDD", "PTS": 104},
        {"SEASON": "2024-25", "GAME_ID": "new2", "GAME_DATE": "2024-10-21", "MATCHUP": "EEE @ DDD", "TEAM_ABBREVIATION": "EEE", "PTS": 102},
    ]
    return pd.DataFrame(rows)


def test_neutral_site_game_is_forecast_without_home_advantage() -> None:
    forecasts = MODULE._walk_forward_predictions(_games())
    neutral = forecasts.loc[forecasts["game_id"].eq("new2")].iloc[0]
    assert bool(neutral["neutral_site"])
    assert neutral["home_advantage_estimate"] == 0.0
    assert neutral["home_team"] == "DDD"
    assert neutral["away_team"] == "EEE"


def test_same_day_results_do_not_leak_into_other_same_day_forecasts() -> None:
    first = MODULE._walk_forward_predictions(_games(110))
    changed = MODULE._walk_forward_predictions(_games(145))
    first_neutral = first.loc[first["game_id"].eq("new2")].iloc[0]
    changed_neutral = changed.loc[changed["game_id"].eq("new2")].iloc[0]
    assert first_neutral["predicted_home_win_probability"] == changed_neutral["predicted_home_win_probability"]
    assert first_neutral["predicted_home_points"] == changed_neutral["predicted_home_points"]
