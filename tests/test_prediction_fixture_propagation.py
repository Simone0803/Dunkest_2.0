import json

import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.optimize.milp import LineupSolution
from dunkest.pipeline.predict import (
    _attach_prediction_fixture_context,
    _verified_team_context,
)
from dunkest.report.artifacts import save_run_artifacts


def _fixture(game_id, home, away, turn, *, verified=True):
    return {
        "home_team": home,
        "away_team": away,
        "home_team_eligible": True,
        "away_team_eligible": True,
        "fantasy_eligible": True,
        "mapping_verified": verified,
        "dunkest_turn": turn,
        "dunkest_match_id": f"dunkest-{turn}",
        "nba_game_id": game_id,
        "game_datetime_utc": f"2026-10-{20 + turn}T00:00:00Z",
    }


def test_verified_fixture_identity_reaches_lineups_artifact_for_multiturn_roster_and_coach(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26", target_gameweek=2)
    fixtures = pd.DataFrame([
        _fixture("nba-game-1", "BOS", "NYK", 1),
        _fixture("nba-game-2", "ATL", "MIA", 2),
    ])
    forecasts = pd.DataFrame([
        {"player_name": "Player One", "team": "BOS", "expected_pdk": 10.0},
        {"player_name": "Player Two", "team": "MIA", "expected_pdk": 8.0},
    ])

    players = _attach_prediction_fixture_context(forecasts, fixtures)
    by_player = players.set_index("player_name")
    assert (by_player.loc["Player One", ["team", "opponent", "dunkest_turn", "nba_game_id"]].tolist()
            == ["BOS", "NYK", 1, "nba-game-1"])
    assert (by_player.loc["Player Two", ["team", "opponent", "dunkest_turn", "nba_game_id"]].tolist()
            == ["MIA", "ATL", 2, "nba-game-2"])

    solution = LineupSolution(
        rank=1,
        expected_team_pdk=18.0,
        expected_player_pdk=18.0,
        expected_coach_pdk=4.0,
        budget_used=20.0,
        captain="Player One",
        coach="Coach One",
        module="dinamico-per-turno",
        num_transfers=0,
        players=players,
        meta={
            "turn_lineups": {
                "1": {"slots": {"Player One": "Captain", "Player Two": "Bench"}, "module": "1-0-0"},
                "2": {"slots": {"Player One": "Bench", "Player Two": "Captain"}, "module": "0-1-0"},
            },
            "coach_matchup": {
                "coach_team": "BOS", "coach_opponent": "NYK",
                "coach_dunkest_turn": 1, "coach_nba_game_id": "nba-game-1",
            },
        },
    )

    candidates = players.copy()
    candidates["dunkest_player_id"] = ["dk-101", "dk-202"]
    candidates["expected_min"] = [26.0, 18.0]
    candidates["expected_min_model_shadow"] = [24.0, float("nan")]
    candidates["p_play"] = [1.0, 0.75]
    candidates["lineup_group"] = ["QUINTETTO", "PANCHINA"]
    candidates["status"] = ["Available", "Questionable"]
    players.attrs["candidate_forecasts"] = candidates
    players.attrs["runtime_feature_snapshot"] = pd.DataFrame([{
        "PLAYER_NAME": "Player One", "PLAYER_ID": "nba-player-101",
        "GAME_DATE": "2026-10-23T00:00:00Z", "player_key": "player one",
        "lag1_nba_min": 24.0, "hgb_input__lag1_nba_min": 24.0,
        "minutes_shadow_feature_status": "transformed",
    }])
    players.attrs["minutes_shadow_feature_columns"] = ["lag1_nba_min"]
    players.attrs["forecast_timestamp_utc"] = "2026-10-19T12:00:00Z"

    output = save_run_artifacts(settings, players, [solution])
    lineups = pd.read_parquet(output / "lineups.parquet").set_index("player_name")
    frozen_candidates = pd.read_parquet(output / "player_forecast_snapshot.parquet").set_index("player_name")
    frozen_features = pd.read_parquet(output / "runtime_feature_snapshot.parquet").set_index("dunkest_player_id")
    manifest = json.loads((output / "manifest.json").read_text())

    assert lineups.loc["Player One", "nba_game_id"] == "nba-game-1"
    assert lineups.loc["Player Two", "nba_game_id"] == "nba-game-2"
    assert lineups.loc["Player One", "coach_nba_game_id"] == "nba-game-1"
    assert lineups.loc["Player One", "slot_turn_1"] == "Captain"
    assert lineups.loc["Player One", "slot_turn_2"] == "Bench"
    assert lineups.loc["Player Two", "slot_turn_1"] == "Bench"
    assert lineups.loc["Player Two", "slot_turn_2"] == "Captain"
    assert frozen_candidates.loc["Player One", "canonical_player_id_source"] == "dunkest_player_id"
    assert frozen_candidates.loc["Player One", "canonical_player_id"] == "dk-101"
    assert frozen_candidates.loc["Player One", "expected_min"] == 26.0
    assert frozen_candidates.loc["Player One", "minutes_hybrid_status"] == "available"
    assert frozen_candidates.loc["Player One", "minutes_shadow_status"] == "available"
    assert frozen_candidates.loc["Player Two", "minutes_shadow_status"] == "unavailable"
    assert pd.isna(frozen_candidates.loc["Player Two", "expected_min_model_shadow"])
    assert frozen_candidates["forecast_record_id"].is_unique
    assert frozen_candidates["forecast_run_id"].nunique() == 1
    assert manifest["player_forecast_snapshot"]["certification"][
        "candidate_stable_identity_verified"
    ] is True
    assert frozen_candidates.loc["Player Two", "p_play"] == 0.75
    assert frozen_candidates.loc["Player Two", "canonical_player_id"] == "dk-202"
    assert frozen_candidates.loc["Player Two", "canonical_player_id_source"] == "dunkest_player_id"
    assert frozen_candidates.loc["Player Two", "nba_game_id"] == "nba-game-2"
    assert frozen_candidates.loc["Player Two", "dunkest_match_id"] == "dunkest-2"
    assert frozen_features.loc["dk-101", "feature_match_status"] == "matched"
    assert frozen_features.loc["dk-101", "runtime_feature__hgb_input__lag1_nba_min"] == 24.0
    assert frozen_features.loc["dk-202", "feature_match_status"] == "missing"
    assert manifest["runtime_feature_snapshot"]["candidate_rows"] == 2
    assert len(manifest["runtime_feature_snapshot"]["sha256"]) == 64


def test_unverified_fixture_never_assigns_its_nba_game_id():
    fixtures = pd.DataFrame([_fixture("unverified-game", "BOS", "NYK", 1, verified=False)])

    assert _verified_team_context(fixtures) == {}
    out = _attach_prediction_fixture_context(
        pd.DataFrame([{"player_name": "Player One", "team": "BOS"}]), fixtures
    )
    assert out.empty


@pytest.mark.parametrize("missing_id", [None, "", "nan"])
def test_verified_eligible_fixture_with_missing_id_fails_explicitly(missing_id):
    fixture = _fixture(missing_id, "BOS", "NYK", 1)
    with pytest.raises(RuntimeError, match="non contiene nba_game_id"):
        _verified_team_context(pd.DataFrame([fixture]))


def test_ambiguous_team_fixture_mapping_fails_instead_of_choosing_an_id():
    fixtures = pd.DataFrame([
        _fixture("game-1", "BOS", "NYK", 1),
        _fixture("game-2", "BOS", "MIA", 2),
    ])

    with pytest.raises(RuntimeError, match="più partite valide alla squadra BOS"):
        _verified_team_context(fixtures)


def test_duplicate_nba_game_id_fails_instead_of_reusing_fixture_identity():
    fixtures = pd.DataFrame([
        _fixture("same-game", "BOS", "NYK", 1),
        _fixture("same-game", "ATL", "MIA", 2),
    ])

    with pytest.raises(RuntimeError, match="same-game è associato a più fixture"):
        _verified_team_context(fixtures)
