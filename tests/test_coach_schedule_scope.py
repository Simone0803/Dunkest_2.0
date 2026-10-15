import pandas as pd

from dunkest.models.coach import _normalize_schedule_frame


def test_gameweek_coach_context_rejects_unlinked_raw_nba_schedule():
    raw = pd.DataFrame([
        {"GAME_DATE": "2026-10-22", "HOME_TEAM": "BOS", "AWAY_TEAM": "NYK"},
        {"GAME_DATE": "2027-03-01", "HOME_TEAM": "LAL", "AWAY_TEAM": "GSW"},
    ])

    normalized = _normalize_schedule_frame(raw, gameweek=2)

    assert normalized.empty


def test_gameweek_coach_context_uses_only_verified_fixture_rows_for_that_gameweek():
    schedule = pd.DataFrame([
        {"dunkest_gameweek": 1, "fantasy_eligible": True, "mapping_verified": True, "nba_game_id": "g1",
         "game_datetime_utc": "2026-10-22T00:00:00Z", "home_team": "BOS",
         "away_team": "NYK", "home_team_eligible": True, "away_team_eligible": True},
        {"dunkest_gameweek": 2, "fantasy_eligible": True, "mapping_verified": True, "nba_game_id": "g2",
         "game_datetime_utc": "2026-10-24T00:00:00Z", "home_team": "LAL",
         "away_team": "GSW", "home_team_eligible": True, "away_team_eligible": True},
    ])

    normalized = _normalize_schedule_frame(schedule, gameweek=2)

    assert normalized["NBA_GAME_ID"].tolist() == ["g2"]
    assert normalized["HOME_TEAM"].tolist() == ["LAL"]


def test_gameweek_coach_context_rejects_unverified_or_string_false_bridge_rows():
    schedule = pd.DataFrame([
        {"dunkest_gameweek": 2, "fantasy_eligible": "true", "mapping_verified": "False",
         "nba_game_id": "bad", "game_datetime_utc": "2026-10-24T00:00:00Z",
         "home_team": "BOS", "away_team": "NYK", "home_team_eligible": "true",
         "away_team_eligible": "true"},
        {"dunkest_gameweek": 2, "fantasy_eligible": "true", "mapping_verified": "true",
         "nba_game_id": "good", "game_datetime_utc": "2026-10-25T00:00:00Z",
         "home_team": "LAL", "away_team": "GSW", "home_team_eligible": "False",
         "away_team_eligible": "true"},
    ])

    normalized = _normalize_schedule_frame(schedule, gameweek=2)

    assert normalized["NBA_GAME_ID"].tolist() == ["good"]
    assert normalized["HOME_TEAM_ELIGIBLE"].tolist() == [False]
    assert normalized["AWAY_TEAM_ELIGIBLE"].tolist() == [True]


def test_gameweek_coach_context_fails_closed_when_bridge_verification_is_missing():
    schedule = pd.DataFrame([{"dunkest_gameweek": 2, "fantasy_eligible": True,
                              "nba_game_id": "g2", "game_datetime_utc": "2026-10-24",
                              "home_team": "LAL", "away_team": "GSW"}])
    assert _normalize_schedule_frame(schedule, gameweek=2).empty
