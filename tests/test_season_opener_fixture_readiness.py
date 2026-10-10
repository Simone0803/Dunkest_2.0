import pandas as pd
import pytest

from dunkest.pipeline.season_opener import (
    _require_complete_score_bearing_teams,
    _verified_gameweek_teams,
)


def test_only_explicitly_score_bearing_fixture_sides_are_verified():
    fixtures = pd.DataFrame([
        {
            "home_team": "BOS", "away_team": "DET",
            "home_team_eligible": True, "away_team_eligible": False,
        },
        {
            "home_team": "PHI", "away_team": "NYK",
            "home_team_eligible": None, "away_team_eligible": True,
        },
    ])

    assert _verified_gameweek_teams(fixtures) == {"BOS", "NYK"}


def test_empty_fixture_mapping_verifies_no_teams():
    assert _verified_gameweek_teams(pd.DataFrame()) == set()


def test_incomplete_matchup_coverage_stops_roster_generation():
    fixtures = pd.DataFrame([{
        "home_team": "BOS", "away_team": "DET",
        "home_team_eligible": True, "away_team_eligible": False,
    }])

    with pytest.raises(RuntimeError, match="1/2 squadre"):
        _require_complete_score_bearing_teams(fixtures, {"BOS", "DET"})


def test_complete_matchup_coverage_is_accepted():
    fixtures = pd.DataFrame([{
        "home_team": "BOS", "away_team": "DET",
        "home_team_eligible": True, "away_team_eligible": True,
    }])

    assert _require_complete_score_bearing_teams(fixtures, {"BOS", "DET"}) == {"BOS", "DET"}
