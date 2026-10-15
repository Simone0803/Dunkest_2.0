import numpy as np
import pandas as pd
from types import SimpleNamespace
from nba_api.stats import endpoints

from dunkest.config import Settings
from dunkest.data.nba import collector
from dunkest.features.builder import (
    _attach_next_game_schedule,
    _player_opponent_features,
    build_feature_matrix,
)


def test_future_schedule_normalizes_fixtures_and_only_keeps_final_scores(monkeypatch):
    games = pd.DataFrame(
        {
            "gameId": ["preseason", "1", "2"],
            "gameDate": ["2026-10-05", "2026-10-20", "2026-10-22"],
            "homeTeam_teamTricode": ["TOR", "BOS", "NYK"],
            "awayTeam_teamTricode": ["MIA", "NYK", "BOS"],
            "homeTeam_score": [0, 110, 0],
            "awayTeam_score": [0, 105, 0],
            "gameStatus": [1, 3, 1],
            "weekNumber": [0, 1, 1],
        }
    )

    class FakeScheduleLeagueV2:
        def __init__(self, **_kwargs):
            self.season_games = self

        def get_data_frame(self):
            return games

    monkeypatch.setattr(
        endpoints,
        "scheduleleaguev2",
        SimpleNamespace(ScheduleLeagueV2=FakeScheduleLeagueV2),
        raising=False,
    )

    result = collector.fetch_future_schedule(Settings())

    assert len(result) == 2
    assert result.loc[0, "HOME_TEAM"] == "BOS"
    assert result.loc[0, "AWAY_TEAM"] == "NYK"
    assert result.loc[0, "PTS"] == 110
    assert pd.isna(result.loc[1, "PTS"])
    assert pd.isna(result.loc[1, "PLUS_MINUS"])
    assert result["NBA_WEEK_NUMBER"].tolist() == [1, 1]


def test_inference_row_uses_upcoming_fixture_and_current_team():
    player_logs = pd.DataFrame(
        [
            {
                "PLAYER_NAME": "Player A",
                "GAME_DATE": pd.Timestamp(date),
                "TEAM_ABBREVIATION": "OLD",
                "OPPONENT": "MIA",
                "MATCHUP": "OLD @ MIA",
                "PDK": 10.0,
                "MIN": 20.0,
                "PTS": 10,
                "REB": 3,
                "AST": 2,
            }
            for date in ("2026-04-01", "2026-04-03")
        ]
    )
    team_logs = pd.DataFrame(
        [
            {
                "TEAM_ABBREVIATION": team,
                "GAME_DATE": pd.Timestamp("2026-04-01") + pd.Timedelta(days=day),
                "PTS": 100.0,
                "PLUS_MINUS": margin,
            }
            for team, margin in (("BOS", 5.0), ("NYK", -7.0))
            for day in range(5)
        ]
    )
    schedule = pd.DataFrame(
        [{"GAME_DATE": pd.Timestamp("2026-10-20"), "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK"}]
    )

    features = build_feature_matrix(
        Settings(rolling_windows=[3]),
        player_logs,
        team_logs,
        schedule=schedule,
        team_overrides={"Player A": "BOS"},
    )
    inference = features.loc[features["is_inference"]].iloc[0]

    assert inference["TEAM_ABBREVIATION"] == "BOS"
    assert inference["OPPONENT"] == "NYK"
    assert inference["is_home"] == 1.0
    assert inference["rest_days"] == 200.0
    assert inference["opp_pts_allowed_mean_5"] == 107.0
    assert features.loc[~features["is_inference"], "is_home"].eq(0.0).all()


def test_inference_row_without_prior_games_uses_first_upcoming_fixture():
    features = pd.DataFrame(
        [
            {
                "PLAYER_NAME": "Rookie",
                "GAME_DATE": pd.Timestamp("2026-10-01"),
                "TEAM_ABBREVIATION": "BOS",
                "OPPONENT": "",
                "is_inference": True,
                "is_home": np.nan,
                "rest_days": 3.0,
                "is_b2b": 0,
            }
        ]
    )
    schedule = pd.DataFrame(
        [{"GAME_DATE": pd.Timestamp("2026-10-20"), "HOME_TEAM": "NYK", "AWAY_TEAM": "BOS"}]
    )

    result = _attach_next_game_schedule(
        features,
        schedule,
        team_logs=None,
        team_overrides=None,
        player_logs=pd.DataFrame(),
    )
    inference = result.iloc[0]

    assert inference["OPPONENT"] == "NYK"
    assert inference["is_home"] == 0.0
    assert inference["rest_days"] == 3.0


def test_dunkest_gameweek_never_filters_or_assigns_by_nba_week_number():
    features = pd.DataFrame([{
        "PLAYER_NAME": "Player A", "GAME_DATE": pd.Timestamp("2026-10-01"),
        "TEAM_ABBREVIATION": "BOS", "OPPONENT": "", "is_inference": True,
        "is_home": np.nan, "rest_days": 3.0, "is_b2b": 0,
    }])
    raw_nba_schedule = pd.DataFrame([{
        "GAME_ID": "early", "GAME_DATE": "2026-10-20", "HOME_TEAM": "BOS",
        "AWAY_TEAM": "NYK", "NBA_WEEK_NUMBER": 1,
    }])
    result = _attach_next_game_schedule(
        features, raw_nba_schedule, None, None, pd.DataFrame(), target_gameweek=1
    )
    assert result.iloc[0]["OPPONENT"] == ""
    assert pd.isna(result.iloc[0]["is_home"])


def test_fixture_bridge_selects_official_valid_game_not_earliest_nba_game():
    features = pd.DataFrame([{
        "PLAYER_NAME": "Player A", "GAME_DATE": pd.Timestamp("2026-10-01"),
        "TEAM_ABBREVIATION": "BOS", "OPPONENT": "", "is_inference": True,
        "is_home": np.nan, "rest_days": 3.0, "is_b2b": 0,
    }])
    bridge = pd.DataFrame([
        {"nba_game_id": "later_valid", "game_datetime_utc": "2026-10-22T00:00:00Z",
         "home_team": "NYK", "away_team": "BOS", "dunkest_gameweek": 1,
         "dunkest_turn": 2, "fantasy_eligible": True, "mapping_verified": True},
        {"nba_game_id": "earlier_invalid", "game_datetime_utc": "2026-10-20T00:00:00Z",
         "home_team": "BOS", "away_team": "NYK", "dunkest_gameweek": 1,
         "dunkest_turn": 1, "fantasy_eligible": False, "mapping_verified": True},
    ])
    result = _attach_next_game_schedule(
        features, bridge, None, None, pd.DataFrame(), target_gameweek=1
    )
    inference = result.iloc[0]
    assert inference["NBA_GAME_ID"] == "later_valid"
    assert inference["DUNKEST_GAMEWEEK"] == 1
    assert inference["DUNKEST_TURN"] == 2
    assert inference["OPPONENT"] == "NYK"
    assert inference["is_home"] == 0.0


def test_player_opponent_rate_is_shrunk_toward_season_rate():
    history = pd.DataFrame(
        {
            "MIN": [20.0, 20.0, 20.0],
            "PDK": [10.0, 20.0, 10.0],
            "OPPONENT": ["MIA", "NYK", "BOS"],
        }
    )

    rate, games = _player_opponent_features(history, "NYK")

    assert rate == 100.0 / 140.0
    assert games == 1.0


def test_fixture_bridge_string_booleans_fail_closed_in_feature_engineering():
    features = pd.DataFrame([{
        "PLAYER_NAME": "Player A", "GAME_DATE": pd.Timestamp("2026-10-01"),
        "TEAM_ABBREVIATION": "BOS", "OPPONENT": "", "is_inference": True,
        "is_home": np.nan, "rest_days": 3.0, "is_b2b": 0,
    }])
    bridge = pd.DataFrame([{
        "nba_game_id": "unverified", "game_datetime_utc": "2026-10-22T00:00:00Z",
        "home_team": "BOS", "away_team": "NYK", "dunkest_gameweek": 1,
        "dunkest_turn": 1, "fantasy_eligible": "true", "mapping_verified": "False",
        "home_team_eligible": "true", "away_team_eligible": "true",
    }, {
        "nba_game_id": "eligible", "game_datetime_utc": "2026-10-23T00:00:00Z",
        "home_team": "MIA", "away_team": "BOS", "dunkest_gameweek": 1,
        "dunkest_turn": 2, "fantasy_eligible": "true", "mapping_verified": "true",
        "home_team_eligible": "False", "away_team_eligible": "true",
    }])
    result = _attach_next_game_schedule(
        features, bridge, None, None, pd.DataFrame(), target_gameweek=1
    )
    inference = result.iloc[0]
    assert inference["NBA_GAME_ID"] == "eligible"
    assert inference["OPPONENT"] == "MIA"
    assert inference["is_home"] == 0.0
