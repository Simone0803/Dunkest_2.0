import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.data.dunkest.fixtures import (
    get_fixture_mapping,
    save_current_capture_fixture_mapping,
    save_fixture_mapping,
)
from dunkest.pipeline.predict import _attach_verified_gameweek_context


def _fixture(game_id, home, away, *, gw, turn, date, retrieved):
    return {
        "season_id": "26",
        "nba_season": "2026-27",
        "nba_game_id": game_id,
        "game_datetime_utc": date,
        "game_date_local": pd.Timestamp(date).date(),
        "home_team": home,
        "away_team": away,
        "home_team_eligible": True,
        "away_team_eligible": True,
        "dunkest_gameweek": gw,
        "dunkest_turn": turn,
        "fantasy_eligible": True,
        "mapping_verified": True,
        "eligibility_reason": "official_lineups_black_gray_status_observed",
        "source": "dunkest_lineups_browser",
        "source_url_or_endpoint": "https://fantasy.dunkest.com/1/lineups",
        "source_retrieved_at_utc": retrieved,
        "mapping_version": "test_v1",
        "raw_payload_sha256": "a" * 64,
    }


def test_next_gameweek_mapping_preserves_prior_gameweeks(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26", season="2026-27")
    processed = tmp_path / "processed"
    processed.mkdir()
    schedule = pd.DataFrame([
        {"GAME_ID": "g1", "GAME_DATE": "2026-10-20T00:00:00Z", "HOME_TEAM": "BOS", "AWAY_TEAM": "DET"},
        {"GAME_ID": "g2", "GAME_DATE": "2026-10-24T00:00:00Z", "HOME_TEAM": "BOS", "AWAY_TEAM": "MIA"},
    ])
    schedule.to_parquet(processed / "future_regular_schedule_2026-27_v2.parquet", index=False)
    old = pd.DataFrame([_fixture(
        "g1", "BOS", "DET", gw=1, turn=1,
        date="2026-10-20T00:00:00Z", retrieved="2026-10-14T10:00:00Z",
    )])
    save_fixture_mapping(settings, old, source="test")
    now = datetime.now(timezone.utc).isoformat()
    pd.DataFrame([{
        "fixture_label": "TURNO 1 24/10 BOS @ MIA",
        "team_a": "BOS", "team_b": "MIA", "display_day": 24, "display_month": 10,
        "dunkest_turn": 1, "team_a_eligible": True, "team_b_eligible": True,
        "observed_at_utc": now,
    }]).to_csv(tmp_path / "lineups_fixtures.csv", index=False)

    mapped = save_current_capture_fixture_mapping(settings, 2)

    assert mapped["dunkest_gameweek"].eq(2).all()
    assert mapped["nba_game_id"].tolist() == ["g2"]
    assert get_fixture_mapping(settings, 1)["nba_game_id"].tolist() == ["g1"]
    all_mapping = pd.read_parquet(next(processed.glob("dunkest_fixture_mapping_26_*.parquet")))
    assert set(all_mapping["dunkest_gameweek"].astype(int)) == {1, 2}


def test_next_gameweek_mapping_rejects_a_capture_that_repeats_prior_week_fixtures(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26", season="2026-27")
    processed = tmp_path / "processed"
    processed.mkdir()
    schedule = pd.DataFrame([
        {"GAME_ID": "g1", "GAME_DATE": "2026-10-20T00:00:00Z", "HOME_TEAM": "BOS", "AWAY_TEAM": "DET"},
    ])
    schedule.to_parquet(processed / "future_regular_schedule_2026-27_v2.parquet", index=False)
    save_fixture_mapping(settings, pd.DataFrame([_fixture(
        "g1", "BOS", "DET", gw=1, turn=1,
        date="2026-10-20T00:00:00Z", retrieved="2026-10-14T10:00:00Z",
    )]), source="test")
    now = datetime.now(timezone.utc).isoformat()
    pd.DataFrame([
        {"fixture_label": "TURNO 1 20/10 BOS @ DET", "team_a": "BOS", "team_b": "DET",
         "display_day": 20, "display_month": 10, "dunkest_turn": 1,
         "team_a_eligible": True, "team_b_eligible": True, "observed_at_utc": now},
    ]).to_csv(tmp_path / "lineups_fixtures.csv", index=False)

    with pytest.raises(RuntimeError, match="riutilizza partite già assegnate"):
        save_current_capture_fixture_mapping(settings, 2)


def test_prediction_context_uses_verified_opponent_turn_and_turn_specific_lineup(tmp_path):
    settings = Settings(data_dir=str(tmp_path), target_gameweek=2)
    pd.DataFrame([
        {"player_name": "Player One", "team": "BOS", "role": "G", "lineup_group_turn1": "PANCHINA", "lineup_group_turn2": "QUINTETTO", "status_turn2": "AVAILABLE", "starter_turn2": "true"},
        {"player_name": "Player Two", "team": "NYK", "role": "F", "lineup_group_turn1": "QUINTETTO", "lineup_group_turn2": "PANCHINA", "status_turn2": "AVAILABLE", "starter_turn2": "false"},
        {"player_name": "Resting Player", "team": "ORL", "role": "C", "lineup_group_turn2": "QUINTETTO"},
    ]).to_csv(tmp_path / "current_lineups_market.csv", index=False)
    market = pd.DataFrame([
        {"player_name": "Player One", "team_code": "BOS", "position": "G", "cr": 8.0, "lineup_group": "PANCHINA", "status": ""},
        {"player_name": "Player Two", "team_code": "NYK", "position": "F", "cr": 7.0, "lineup_group": "QUINTETTO", "status": ""},
        {"player_name": "Resting Player", "team_code": "ORL", "position": "C", "cr": 5.0, "lineup_group": "QUINTETTO", "status": ""},
    ])
    fixtures = pd.DataFrame([{
        "home_team": "BOS", "away_team": "NYK", "home_team_eligible": True,
        "away_team_eligible": True, "fantasy_eligible": True, "dunkest_turn": 2,
        "nba_game_id": "g2", "game_datetime_utc": "2026-10-24T00:00:00Z",
    }])

    out = _attach_verified_gameweek_context(settings, market, fixtures).set_index("player_name")

    assert set(out.index) == {"Player One", "Player Two"}
    assert out.loc["Player One", "opponent"] == "NYK"
    assert out.loc["Player One", "dunkest_turn"] == 2
    assert out.loc["Player One", "nba_game_id"] == "g2"
    assert out.loc["Player One", "lineup_group"] == "QUINTETTO"
    assert out.loc["Player Two", "opponent"] == "BOS"
    assert out.loc["Player Two", "lineup_group"] == "PANCHINA"


def test_prediction_context_fails_closed_without_verified_fixture():
    settings = Settings(target_gameweek=2)
    market = pd.DataFrame([{"player_name": "Player One", "team_code": "BOS"}])
    with pytest.raises(RuntimeError, match="Nessun matchup Dunkest verificato"):
        _attach_verified_gameweek_context(settings, market, pd.DataFrame())
