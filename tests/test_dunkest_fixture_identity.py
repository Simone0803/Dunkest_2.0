import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.data.dunkest.fixtures import (
    build_gameweek1_mapping_from_lineups,
    build_gameweek_mapping_from_official_calendar,
    fetch_official_dunkest_gameweek_calendar,
    ensure_gameweek1_fixture_mapping,
    get_fixture_mapping,
    save_fixture_mapping,
    validate_fixture_mapping,
)
from dunkest.data.temporal import (
    validate_player_fixture_associations,
    validate_prematch_features,
)


def _fixture(game_id, home, away, *, gw=1, turn=1, eligible=True, start="2026-10-20T23:00:00Z"):
    return {
        "season_id": "26",
        "nba_season": "2026-27",
        "nba_game_id": game_id,
        "game_datetime_utc": start,
        "game_date_local": "2026-10-21",
        "home_team": home,
        "away_team": away,
        "dunkest_gameweek": gw,
        "dunkest_turn": turn,
        "fantasy_eligible": eligible,
        "mapping_verified": True,
        "eligibility_reason": "official score-bearing game",
        "source": "official Dunkest calendar capture",
        "source_url_or_endpoint": "https://dunkest.example/calendar",
        "source_retrieved_at_utc": "2026-10-19T12:00:00Z",
        "mapping_version": "v1",
        "raw_payload_sha256": "a" * 64,
    }


def test_fixture_identity_is_game_id_and_duplicate_id_is_rejected():
    rows = [_fixture("001", "BOS", "NYK"), _fixture("002", "MIA", "ORL")]
    assert validate_fixture_mapping(pd.DataFrame(rows))["nba_game_id"].tolist() == ["001", "002"]
    with pytest.raises(ValueError, match="Duplicate fixture identity"):
        validate_fixture_mapping(pd.DataFrame([rows[0], rows[0]]))


def test_gw_can_be_subset_of_nba_games_and_team_can_play_multiple_games():
    rows = [
        _fixture("early", "BOS", "NYK", eligible=False),
        _fixture("valid", "BOS", "MIA", turn=2, eligible=True),
        _fixture("other", "LAL", "SAC", gw=2, eligible=True),
    ]
    clean = validate_fixture_mapping(pd.DataFrame(rows).sample(frac=1, random_state=1))
    assert len(clean.loc[clean["dunkest_gameweek"].eq(1)]) == 2
    assert clean.loc[clean["nba_game_id"].eq("valid"), "fantasy_eligible"].item()


def test_two_score_bearing_games_for_same_team_and_gw_are_rejected():
    with pytest.raises(ValueError, match="multiple fantasy-eligible games"):
        validate_fixture_mapping(pd.DataFrame([
            _fixture("001", "BOS", "NYK"), _fixture("002", "BOS", "MIA", turn=2),
        ]))


def test_player_game_join_checks_team_opponent_home_away_and_game_identity():
    fixture = pd.DataFrame([_fixture("001", "BOS", "NYK")])
    good = pd.DataFrame([{
        "nba_game_id": "001", "team": "BOS", "opponent": "NYK",
        "home_away": "HOME", "game_datetime_utc": "2026-10-20T23:00:00Z",
        "prediction_cutoff_utc": "2026-10-20T20:00:00Z",
    }])
    assert len(validate_player_fixture_associations(good, fixture)) == 1
    wrong = good.assign(opponent="MIA")
    with pytest.raises(ValueError, match="team/opponent/home-away"):
        validate_player_fixture_associations(wrong, fixture)
    wrong_side = good.assign(home_away="AWAY")
    with pytest.raises(ValueError, match="team/opponent/home-away"):
        validate_player_fixture_associations(wrong_side, fixture)


def test_player_fixture_association_rejects_explicitly_ineligible_side_and_parses_strings():
    fixture = pd.DataFrame([{
        **_fixture("001", "BOS", "NYK"),
        "home_team_eligible": "False",
        "away_team_eligible": "true",
    }])
    player = pd.DataFrame([{
        "nba_game_id": "001", "team": "BOS", "opponent": "NYK",
        "home_away": "HOME", "game_datetime_utc": "2026-10-20T23:00:00Z",
    }])
    with pytest.raises(ValueError, match="non-valid/unknown team fixture"):
        validate_player_fixture_associations(player, fixture)

    eligible_away = player.assign(team="NYK", opponent="BOS", home_away="AWAY")
    assert len(validate_player_fixture_associations(eligible_away, fixture)) == 1


def test_fixture_mapping_not_available_at_prediction_cutoff_is_rejected():
    fixture = pd.DataFrame([_fixture("001", "BOS", "NYK")])
    fixture.loc[0, "source_retrieved_at_utc"] = "2026-10-20T21:00:00Z"
    player = pd.DataFrame([{
        "nba_game_id": "001", "team": "BOS", "opponent": "NYK", "home_away": "HOME",
        "game_datetime_utc": "2026-10-20T23:00:00Z", "prediction_cutoff_utc": "2026-10-20T20:00:00Z",
    }])
    with pytest.raises(ValueError, match="after the prediction cutoff"):
        validate_player_fixture_associations(player, fixture)


def test_unverified_fixture_proxy_is_never_used_for_predictions(tmp_path):
    settings = Settings(data_dir=str(tmp_path))
    official = _fixture("official", "BOS", "NYK")
    provisional = _fixture("proxy", "MIA", "ORL")
    provisional["mapping_verified"] = False
    provisional["source"] = "nba_schedule_first_appearance"
    provisional["mapping_version"] = "mixed"
    official["mapping_version"] = "mixed"
    save_fixture_mapping(
        settings,
        pd.DataFrame([official, provisional]),
        source="test",
    )

    mapping = get_fixture_mapping(settings, 1)

    assert mapping["nba_game_id"].tolist() == ["official"]


def test_lineups_matchup_maps_to_the_unique_nba_game_on_display_date():
    settings = Settings()
    schedule = pd.DataFrame([
        {"GAME_ID": "first", "GAME_DATE": "2026-10-20", "HOME_TEAM": "DET", "AWAY_TEAM": "BOS"},
        {"GAME_ID": "later", "GAME_DATE": "2027-01-10", "HOME_TEAM": "BOS", "AWAY_TEAM": "DET"},
    ])
    observations = pd.DataFrame([{
        "fixture_label": "TURNO 1 20/10 BOS VS DET",
        "team_a": "BOS", "team_b": "DET", "display_day": "20", "display_month": "10",
        "dunkest_turn": 1, "observed_at_utc": "2026-10-10T08:00:00Z",
    }])

    mapping = build_gameweek1_mapping_from_lineups(settings, schedule, observations)

    assert mapping["nba_game_id"].tolist() == ["first"]
    assert mapping.loc[0, "home_team"] == "DET"
    # The date-to-NBA-game identity is resolved, but eligibility remains
    # unverified until both teams have explicit Lineups status observations.
    assert not bool(mapping.loc[0, "mapping_verified"])
    assert pd.isna(mapping.loc[0, "fantasy_eligible"])


def test_complete_capture_with_all_sides_ineligible_rejects_stale_mapping(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    processed = tmp_path / "processed"
    processed.mkdir()
    schedule = pd.DataFrame([
        {"GAME_ID": "opening", "GAME_DATE": "2026-10-20", "HOME_TEAM": "DET", "AWAY_TEAM": "BOS"},
        {"GAME_ID": "next", "GAME_DATE": "2026-10-21", "HOME_TEAM": "NYK", "AWAY_TEAM": "PHI"},
    ])
    schedule.to_parquet(processed / "future_regular_schedule_2026-27.parquet", index=False)
    old = _fixture("stale", "DET", "BOS")
    save_fixture_mapping(settings, pd.DataFrame([old]), source="test")
    pd.DataFrame([
        {
            "team_a": "BOS", "team_b": "DET", "display_day": 20, "display_month": 10,
            "dunkest_turn": 1, "team_a_eligible": False, "team_b_eligible": False,
            "observed_at_utc": "2026-10-10T15:00:00Z",
        },
        {
            "team_a": "PHI", "team_b": "NYK", "display_day": 21, "display_month": 10,
            "dunkest_turn": 1, "team_a_eligible": False, "team_b_eligible": False,
            "observed_at_utc": "2026-10-10T15:00:00Z",
        },
    ]).to_csv(tmp_path / "lineups_fixtures.csv", index=False)

    with pytest.raises(RuntimeError, match="tutti i 4 lati"):
        ensure_gameweek1_fixture_mapping(settings)


def test_partial_verified_mapping_is_used_without_requiring_30_active_teams(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    processed = tmp_path / "processed"
    processed.mkdir()
    schedule = pd.DataFrame([{
        "GAME_ID": "opening", "GAME_DATE": "2026-10-20",
        "HOME_TEAM": "DET", "AWAY_TEAM": "BOS",
    }])
    schedule.to_parquet(processed / "future_regular_schedule_2026-27.parquet", index=False)
    pd.DataFrame([{
        "team_a": "BOS", "team_b": "DET", "display_day": 20,
        "display_month": 10, "dunkest_turn": 1,
        "team_a_eligible": False, "team_b_eligible": True,
        "observed_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }]).to_csv(tmp_path / "lineups_fixtures.csv", index=False)

    mapping = ensure_gameweek1_fixture_mapping(settings)

    assert mapping["nba_game_id"].tolist() == ["opening"]
    assert bool(mapping.loc[0, "home_team_eligible"])
    assert not bool(mapping.loc[0, "away_team_eligible"])


def test_lineups_mapping_keeps_validity_per_team_not_per_game():
    settings = Settings()
    schedule = pd.DataFrame([
        {"GAME_ID": "first", "GAME_DATE": "2026-10-20", "HOME_TEAM": "DET", "AWAY_TEAM": "BOS"},
    ])
    observations = pd.DataFrame([{
        "fixture_label": "TURNO 1 20/10 BOS @ DET",
        "team_a": "BOS", "team_b": "DET", "display_day": "20", "display_month": "10",
        "team_a_eligible": False, "team_b_eligible": True,
        "dunkest_turn": 1, "observed_at_utc": "2026-10-10T08:00:00Z",
    }])

    mapping = build_gameweek1_mapping_from_lineups(settings, schedule, observations)

    assert bool(mapping.loc[0, "fantasy_eligible"])
    assert bool(mapping.loc[0, "home_team_eligible"])
    assert not bool(mapping.loc[0, "away_team_eligible"])


def test_lineups_mapping_resolves_one_day_display_date_shift_without_season_wide_pair_match():
    settings = Settings()
    schedule = pd.DataFrame([
        {"GAME_ID": "opening", "GAME_DATE": "2026-10-20", "HOME_TEAM": "DET", "AWAY_TEAM": "BOS"},
        {"GAME_ID": "later", "GAME_DATE": "2026-11-15", "HOME_TEAM": "BOS", "AWAY_TEAM": "DET"},
        {"GAME_ID": "next_season", "GAME_DATE": "2027-01-10", "HOME_TEAM": "DET", "AWAY_TEAM": "BOS"},
    ])
    observations = pd.DataFrame([{
        "fixture_label": "TURNO 1 21/10 BOS @ DET",
        "team_a": "BOS", "team_b": "DET", "display_day": "21", "display_month": "10",
        "team_a_eligible": True, "team_b_eligible": False,
        "dunkest_turn": 1, "observed_at_utc": "2026-10-10T08:00:00Z",
    }])

    mapping = build_gameweek1_mapping_from_lineups(settings, schedule, observations)

    assert mapping["nba_game_id"].tolist() == ["opening"]
    assert mapping.loc[0, "home_team"] == "DET"
    assert bool(mapping.loc[0, "away_team_eligible"])
    assert not bool(mapping.loc[0, "home_team_eligible"])


def test_prematch_feature_guard_rejects_postmatch_target_and_late_data():
    with pytest.raises(ValueError, match="POST_MATCH"):
        validate_prematch_features(pd.DataFrame(), ["target_pdk"])
    late = pd.DataFrame({
        "prediction_cutoff_utc": ["2026-10-20T20:00:00Z"],
        "available_at_utc": ["2026-10-20T21:00:00Z"],
    })
    with pytest.raises(ValueError, match="post-cutoff"):
        validate_prematch_features(late, ["pdk_mean_5"])


def test_fetch_official_dunkest_calendar_uses_current_schedule_and_validates_matchday_number(monkeypatch):
    import dunkest.data.dunkest.fixtures as fixtures

    calls = []
    def fake_get_json(url, timeout):
        calls.append(url)
        if url.endswith("/leagues/1/config"):
            return {"data": {"current_schedule_id": 57, "current_matchday": {"id": 1858, "number": 1}}}
        return {"data": {"id": 1858, "number": 1, "rounds": [{
            "id": 2890, "number": 1, "matches": [{
                "id": 14067, "status": "scheduled", "started_at": "2026-10-20T19:00:00Z",
                "home_team": {"abbreviation": "DET", "is_valid": True},
                "away_team": {"abbreviation": "BOS", "is_valid": False},
            }]
        }]}}
    monkeypatch.setattr(fixtures, "get_json", fake_get_json)

    calendar, metadata = fetch_official_dunkest_gameweek_calendar(1)

    assert calls == [
        "https://fantaking-api.dunkest.com/api/v1/leagues/1/config",
        "https://fantaking-api.dunkest.com/api/v1/schedules/57/matchdays/1858",
    ]
    assert metadata["schedule_id"] == 57 and metadata["matchday_id"] == 1858
    assert calendar.loc[0, "dunkest_turn"] == 1
    assert bool(calendar.loc[0, "home_team_eligible"]) is True
    assert bool(calendar.loc[0, "away_team_eligible"]) is False


def test_fetch_official_dunkest_calendar_rejects_wrong_matchday_id(monkeypatch):
    import dunkest.data.dunkest.fixtures as fixtures
    def fake_get_json(url, timeout):
        if url.endswith("/leagues/1/config"):
            return {"data": {"current_schedule_id": 57, "current_matchday": {"id": 1858, "number": 1}}}
        return {"data": {"id": 1859, "number": 2, "rounds": []}}
    monkeypatch.setattr(fixtures, "get_json", fake_get_json)
    with pytest.raises(ValueError, match="expected Giornata 1"):
        fetch_official_dunkest_gameweek_calendar(1)


def test_official_calendar_bridge_uses_official_turn_and_team_validity():
    settings = Settings()
    schedule = pd.DataFrame([
        {"GAME_ID": "0022600001", "GAME_DATE": "2026-10-20", "HOME_TEAM": "DET", "AWAY_TEAM": "BOS"},
        {"GAME_ID": "0022600002", "GAME_DATE": "2026-10-21", "HOME_TEAM": "NYK", "AWAY_TEAM": "PHI"},
    ])
    calendar = pd.DataFrame([
        {"dunkest_schedule_id": 57, "dunkest_matchday_id": 1858, "dunkest_gameweek": 1,
         "dunkest_turn": 1, "dunkest_match_id": 14067, "game_datetime_utc": "2026-10-20T19:00:00Z",
         "home_team": "DET", "away_team": "BOS", "home_team_eligible": True, "away_team_eligible": False},
        {"dunkest_schedule_id": 57, "dunkest_matchday_id": 1858, "dunkest_gameweek": 1,
         "dunkest_turn": 1, "dunkest_match_id": 14068, "game_datetime_utc": "2026-10-20T23:00:00Z",
         "home_team": "NYK", "away_team": "PHI", "home_team_eligible": True, "away_team_eligible": True},
    ])

    mapping = build_gameweek_mapping_from_official_calendar(
        settings, schedule, calendar, gameweek=1
    ).sort_values("nba_game_id")

    assert mapping["nba_game_id"].tolist() == ["0022600001", "0022600002"]
    assert mapping["dunkest_turn"].tolist() == [1, 1]
    assert mapping["home_team_eligible"].tolist() == [True, True]
    assert mapping["away_team_eligible"].tolist() == [False, True]
    assert mapping["source"].eq("official_fantaking_dunkest_api").all()
    assert mapping["mapping_verified"].all()
