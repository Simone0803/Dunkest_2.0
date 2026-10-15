import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.data.cache import write_parquet
from dunkest.pipeline.season_opener import (
    _attach_verified_player_matchups,
    _filter_coaches_to_target_turn,
    get_opening_market,
    _require_finite_player_forecasts,
    _require_complete_score_bearing_teams,
    _select_turn_specific_lineup_annotations,
    _verified_gameweek_teams,
)
from dunkest.pipeline import season_opener


def test_season_opener_uses_shared_player_forecast_builder():
    # Regression guard: the live season-opener path calls this shared function.
    assert callable(season_opener.build_player_forecast)


def test_turn_specific_lineup_annotations_override_other_turn_labels_but_preserve_hard_out():
    market = pd.DataFrame([
        {
            "player_name": "Player A", "dunkest_turn": 1,
            "lineup_group": "PANCHINA", "starter": False, "status": "AVAILABLE",
            "lineup_group_turn1": "QUINTETTO", "starter_turn1": True, "status_turn1": "AVAILABLE",
            "lineup_group_turn2": "PANCHINA", "starter_turn2": False, "status_turn2": "AVAILABLE",
            "lineup_group_turn3": "", "starter_turn3": None, "status_turn3": "",
        },
        {
            "player_name": "Player B", "dunkest_turn": 2,
            "lineup_group": "QUINTETTO", "starter": True, "status": "OUT",
            "lineup_group_turn1": "PANCHINA", "starter_turn1": False, "status_turn1": "AVAILABLE",
            "lineup_group_turn2": "PANCHINA", "starter_turn2": False, "status_turn2": "OUT",
            "lineup_group_turn3": "QUINTETTO", "starter_turn3": True, "status_turn3": "AVAILABLE",
        },
        {
            "player_name": "Player C", "dunkest_turn": 3,
            "lineup_group": "QUINTETTO", "starter": True, "status": "AVAILABLE",
            "lineup_group_turn1": "QUINTETTO", "starter_turn1": True, "status_turn1": "AVAILABLE",
            "lineup_group_turn2": "PANCHINA", "starter_turn2": False, "status_turn2": "AVAILABLE",
            "lineup_group_turn3": "", "starter_turn3": None, "status_turn3": "",
        },
    ])

    result = _select_turn_specific_lineup_annotations(market).set_index("player_name")

    assert result.loc["Player A", "lineup_group"] == "QUINTETTO"
    assert bool(result.loc["Player A", "starter"]) is True
    assert result.loc["Player A", "status"] == "AVAILABLE"
    assert result.loc["Player B", "lineup_group"] == "INDISPONIBILI"
    assert result.loc["Player B", "status"] == "OUT"
    assert result.loc["Player C", "lineup_group"] == ""
    assert result.loc["Player C", "status"] == ""


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


def test_explicitly_ineligible_rest_team_is_accounted_for_not_treated_as_unknown():
    fixtures = pd.DataFrame([{
        "home_team": "BOS", "away_team": "DET",
        "home_team_eligible": True, "away_team_eligible": False,
    }])

    assert _require_complete_score_bearing_teams(fixtures, {"BOS", "DET"}) == {"BOS"}


def test_complete_matchup_coverage_is_accepted():
    fixtures = pd.DataFrame([{
        "home_team": "BOS", "away_team": "DET",
        "home_team_eligible": True, "away_team_eligible": True,
    }])

    assert _require_complete_score_bearing_teams(fixtures, {"BOS", "DET"}) == {"BOS", "DET"}


def _verified_fixture_rows():
    return pd.DataFrame([
        {
            "home_team": "DET", "away_team": "BOS", "home_team_eligible": True,
            "away_team_eligible": True, "dunkest_turn": 1, "nba_game_id": "g1",
            "mapping_verified": True, "fantasy_eligible": True,
        },
        {
            "home_team": "ORL", "away_team": "ATL", "home_team_eligible": True,
            "away_team_eligible": True, "dunkest_turn": 2, "nba_game_id": "g2",
            "mapping_verified": True, "fantasy_eligible": True,
        },
    ])


def test_player_matchups_fill_missing_opponent_and_validate_turn():
    predictions = pd.DataFrame([{
        "player_name": "Example Player", "team": "BOS", "opponent": "",
        "dunkest_turn": 1,
    }])

    result = _attach_verified_player_matchups(predictions, _verified_fixture_rows())

    assert result.loc[0, "opponent"] == "DET"
    assert result.loc[0, "dunkest_turn"] == 1
    assert result.loc[0, "nba_game_id"] == "g1"


def test_player_matchup_mismatch_fails_closed():
    predictions = pd.DataFrame([{
        "player_name": "Example Player", "team": "BOS", "opponent": "NYK",
        "dunkest_turn": 1,
    }])

    with pytest.raises(RuntimeError, match="Avversario giocatori incoerente"):
        _attach_verified_player_matchups(predictions, _verified_fixture_rows())


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), ""])
def test_nonfinite_player_forecasts_stop_season_opener(bad_value):
    predictions = pd.DataFrame([{
        "player_name": "Incomplete Forecast", "expected_pdk": bad_value,
    }])

    with pytest.raises(RuntimeError, match="Forecast PDK giocatore mancanti o non finiti"):
        _require_finite_player_forecasts(predictions)


def test_finite_player_forecasts_are_normalized_for_optimization():
    predictions = pd.DataFrame([{
        "player_name": "Finite Forecast", "expected_pdk": "7.25",
    }])

    result = _require_finite_player_forecasts(predictions)

    assert result.loc[0, "expected_pdk"] == 7.25
    assert result["expected_pdk"].dtype == float


def test_coach_pool_is_restricted_to_requested_turn_and_verified_opponent():
    coaches = pd.DataFrame([
        {"coach": "Coach One", "team": "BOS", "opponent": "DET", "dunkest_turn": 1, "coach_cr": 8.0},
        {"coach": "Coach Two", "team": "ATL", "opponent": "ORL", "dunkest_turn": 2, "coach_cr": 9.0},
    ])

    result = _filter_coaches_to_target_turn(coaches, _verified_fixture_rows(), 1)

    assert result["coach"].tolist() == ["Coach One"]
    assert result["opponent"].tolist() == ["DET"]
    assert result["dunkest_turn"].tolist() == [1]


def test_opening_market_uses_recent_timestamped_cache(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26", opening_prior_season_id="25")
    path = tmp_path / "processed" / "opening_market_26_25_gw1.parquet"
    cached = pd.DataFrame([{"player_name": "Cached Player", "cr": 8.0}])
    write_parquet(cached, path, source="test_opening_market")

    def unexpected_fetch(*args, **kwargs):
        pytest.fail("fresh opening market cache should be reused")

    monkeypatch.setattr(season_opener, "fetch_opening_market_pool", unexpected_fetch)

    assert get_opening_market(settings)["player_name"].tolist() == ["Cached Player"]


@pytest.mark.parametrize("cache_age_hours", [7, None])
def test_opening_market_refreshes_stale_or_untimestamped_cache(
    tmp_path, monkeypatch, cache_age_hours
):
    settings = Settings(data_dir=str(tmp_path), season_id="26", opening_prior_season_id="25")
    path = tmp_path / "processed" / "opening_market_26_25_gw1.parquet"
    write_parquet(pd.DataFrame([{"player_name": "Stale Player", "cr": 8.0}]), path, source="test")
    metadata_path = path.with_suffix(path.suffix + ".meta.json")
    if cache_age_hours is None:
        metadata_path.unlink()
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["fetched_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=cache_age_hours)
        ).isoformat()
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    fresh = pd.DataFrame([{"player_name": "Fresh Player", "cr": 9.0}])
    calls = []

    def fetch(*args, **kwargs):
        calls.append(True)
        return fresh

    monkeypatch.setattr(season_opener, "fetch_opening_market_pool", fetch)

    result = get_opening_market(settings)

    assert calls == [True]
    assert result["player_name"].tolist() == ["Fresh Player"]


def test_unknown_team_eligibility_still_blocks_roster_generation():
    fixtures = pd.DataFrame([
        {"home_team": "BOS", "away_team": "DET",
         "home_team_eligible": True, "away_team_eligible": None},
    ])
    with pytest.raises(RuntimeError, match="stato eleggibilità esplicito"):
        _require_complete_score_bearing_teams(fixtures, {"BOS", "DET"})


def test_string_boolean_fixture_statuses_are_parsed_semantically():
    fixtures = pd.DataFrame([{
        "home_team": "BOS", "away_team": "DET",
        "home_team_eligible": "true", "away_team_eligible": "False",
        "mapping_verified": "true", "fantasy_eligible": "true",
        "dunkest_turn": 1, "nba_game_id": "g1",
    }])

    assert _verified_gameweek_teams(fixtures) == {"BOS"}
    assert _require_complete_score_bearing_teams(fixtures, {"BOS", "DET"}) == {"BOS"}
    assert season_opener._verified_matchups_by_team(fixtures) == {
        "BOS": {"opponent": "DET", "dunkest_turn": 1, "nba_game_id": "g1"}
    }


def test_unrecognized_fixture_boolean_does_not_create_verified_matchup():
    fixtures = pd.DataFrame([{
        "home_team": "BOS", "away_team": "DET",
        "home_team_eligible": "unknown", "away_team_eligible": "False",
        "mapping_verified": "yes-ish", "fantasy_eligible": "true",
        "dunkest_turn": 1, "nba_game_id": "g1",
    }])

    assert _verified_gameweek_teams(fixtures) == set()
    assert season_opener._verified_matchups_by_team(fixtures) == {}
