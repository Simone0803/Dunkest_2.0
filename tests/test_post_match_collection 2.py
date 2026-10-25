import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_dunkest_post_match_results_v1",
    ROOT / "scripts" / "build_dunkest_post_match_results_v1.py",
)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


def _fixtures():
    mapping = pd.DataFrame([{
        "nba_game_id": "game-1",
        "game_datetime_utc": "2026-10-01T12:00:00Z",
        "game_date_local": "2026-10-01",
        "dunkest_gameweek": 1,
        "mapping_verified": True,
        "source_retrieved_at_utc": "2026-10-01T07:00:00Z",
        "raw_payload_sha256": "a" * 64,
        "home_team": "ATL",
        "away_team": "BOS",
    }])
    return collector.prepare_fixture_index(mapping, 1)[0]


def test_player_actuals_join_by_player_opponent_date_and_verified_fixture():
    predictions = pd.DataFrame([{
        "player_name": "Test Player", "nba_game_id": "game-1", "expected_pdk": 8.0,
    }])
    market = pd.DataFrame([{"player_name": "Test Player", "team_code": "ATL"}])
    official = pd.DataFrame([{
        "_requested_player_name": "Test Player",
        "opponentTeamCode": "BOS",
        "gameDate": "2026-10-01",
        "pdk": 12.5,
        "gameValidForDunkest": True,
    }])
    actuals, missing, audit = collector.build_player_actuals(predictions, market, _fixtures(), official)

    assert actuals.to_dict("records") == [{
        "player_name": "Test Player", "nba_game_id": "game-1", "actual_pdk": 12.5,
    }]
    assert missing.empty
    assert audit["prediction_coverage"] == 1.0


def test_invalid_dunkest_result_rows_are_not_counted_as_actuals():
    predictions = pd.DataFrame([{
        "player_name": "Test Player", "nba_game_id": "game-1", "expected_pdk": 8.0,
    }])
    market = pd.DataFrame([{"player_name": "Test Player", "team_code": "ATL"}])
    official = pd.DataFrame([{
        "_requested_player_name": "Test Player",
        "opponentTeamCode": "BOS",
        "gameDate": "2026-10-01",
        "pdk": 12.5,
        "gameValidForDunkest": False,
    }])
    actuals, missing, audit = collector.build_player_actuals(predictions, market, _fixtures(), official)

    assert actuals.empty
    assert len(missing) == 1
    assert audit["prediction_coverage"] == 0.0


def test_coach_scores_are_linked_to_final_nba_fixture_ids():
    coach_market = pd.DataFrame([
        {"coach": "Coach A", "team": "ATL", "coach_cr": 8.0, "opponent": "BOS", "opponent_coach_cr": 7.0, "nba_game_id": "game-1"},
        {"coach": "Coach B", "team": "BOS", "coach_cr": 7.0, "opponent": "ATL", "opponent_coach_cr": 8.0, "nba_game_id": "game-1"},
    ])
    team_logs = pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PTS": 110, "MIN": 240},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PTS": 98, "MIN": 240},
    ])
    player_logs = pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PLAYER_NAME": "Player A", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PLAYER_NAME": "Player B", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PLAYER_NAME": "Player C", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PLAYER_NAME": "Player D", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PLAYER_NAME": "Player E", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PLAYER_NAME": "Player F", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PLAYER_NAME": "Player G", "MIN": 24.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PLAYER_NAME": "Player H", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PLAYER_NAME": "Player I", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PLAYER_NAME": "Player J", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PLAYER_NAME": "Player K", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PLAYER_NAME": "Player L", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PLAYER_NAME": "Player M", "MIN": 36.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PLAYER_NAME": "Player N", "MIN": 24.0},
    ])
    actuals, audit = collector.build_coach_actuals(coach_market, _fixtures(), team_logs, player_logs)

    assert len(actuals) == 2
    assert set(actuals["nba_game_id"]) == {"game-1"}
    assert audit["coverage"] == 1.0
    assert audit["expected_coach_fixture_pairs"] == 2
    assert audit["overtime_inference_games"] == 1
    assert actuals["actual_coach_pdk"].notna().all()
    assert not actuals["overtime"].any()


def test_coach_score_is_not_fabricated_when_overtime_cannot_be_inferred():
    coach_market = pd.DataFrame([
        {"coach": "Coach A", "team": "ATL", "coach_cr": 8.0, "opponent": "BOS", "opponent_coach_cr": 7.0, "nba_game_id": "game-1"},
    ])
    team_logs = pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PTS": 110, "MIN": 240},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PTS": 98, "MIN": 240},
    ])
    actuals, audit = collector.build_coach_actuals(coach_market, _fixtures(), team_logs, pd.DataFrame())

    assert actuals.empty
    assert audit["coverage"] == 0.0
    assert audit["missing_coach_fixture_pairs"] == [["Coach A", "game-1"]]


def test_invalid_final_score_is_not_counted_as_coach_actual_coverage():
    coach_market = pd.DataFrame([{
        "coach": "Coach A", "team": "ATL", "coach_cr": 8.0,
        "opponent": "BOS", "opponent_coach_cr": 7.0, "nba_game_id": "game-1",
    }])
    team_logs = pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PTS": 100, "MIN": 240},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PTS": 100, "MIN": 240},
    ])
    player_logs = pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": team, "MIN": 48.0}
        for team in ("ATL", "BOS") for _ in range(5)
    ])

    actuals, audit = collector.build_coach_actuals(
        coach_market, _fixtures(), team_logs, player_logs
    )

    assert actuals.empty
    assert audit["coverage"] == 0.0
    assert audit["missing_coach_fixture_pairs"] == [["Coach A", "game-1"]]


def test_coach_overtime_is_inferred_from_summed_player_minutes():
    coach_market = pd.DataFrame([
        {"coach": "Coach A", "team": "ATL", "coach_cr": 8.0, "opponent": "BOS", "opponent_coach_cr": 7.0, "nba_game_id": "game-1"},
    ])
    team_logs = pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PTS": 120, "MIN": 240},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PTS": 117, "MIN": 240},
    ])
    player_logs = pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "MIN": 50.0},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "MIN": 50.0},
    ])
    actuals, audit = collector.build_coach_actuals(coach_market, _fixtures(), team_logs, player_logs)

    assert len(actuals) == 1
    assert bool(actuals.iloc[0]["overtime"])
    assert audit["coverage"] == 1.0


def test_date_only_schedule_uses_conservative_postgame_cutoff():
    cutoff, mode = collector.safe_postgame_retrieval_cutoff(pd.Series([
        "2026-10-21T00:00:00Z", "2026-10-22T00:00:00Z",
    ]))

    assert cutoff == pd.Timestamp("2026-10-23T12:00:00Z")
    assert mode == "date_only_schedule_plus_36h"


def test_exact_kickoff_schedule_uses_four_hour_cutoff():
    cutoff, mode = collector.safe_postgame_retrieval_cutoff(pd.Series([
        "2026-10-21T23:30:00Z", "2026-10-22T02:00:00Z",
    ]))

    assert cutoff == pd.Timestamp("2026-10-22T06:00:00Z")
    assert mode == "exact_kickoff_plus_4h"


def test_builder_resolves_frozen_run_from_isolated_workspace(tmp_path):
    data_dir = tmp_path / "data"
    workspace_run = tmp_path / "workspaces" / "preflight" / "predictions" / "run-1"
    workspace_run.mkdir(parents=True)
    (workspace_run / "manifest.json").write_text('{"run_id":"run-1"}', encoding="utf-8")

    resolved = collector.resolve_run_dir(data_dir, run_id="run-1", run_dir=workspace_run)

    assert resolved == workspace_run.resolve()


def test_builder_rejects_mismatched_run_id_for_explicit_workspace(tmp_path):
    workspace_run = tmp_path / "workspaces" / "run-1"
    workspace_run.mkdir(parents=True)
    (workspace_run / "manifest.json").write_text('{"run_id":"run-1"}', encoding="utf-8")

    import pytest
    with pytest.raises(ValueError, match="does not match manifest run_id"):
        collector.resolve_run_dir(tmp_path / "data", run_id="wrong-run", run_dir=workspace_run)


def test_post_match_builder_archives_linked_results_through_shared_writer(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    processed = data_dir / "processed"
    processed.mkdir(parents=True)
    run_dir = tmp_path / "workspace" / "run-1"
    snapshot_dir = run_dir / "pre_match_snapshot"
    snapshot_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": "run-1",
        "configuration": {
            "season": "2026-27", "season_id": "26", "target_gameweek": 1,
        },
    }), encoding="utf-8")
    pd.DataFrame([{
        "nba_game_id": "game-1", "game_datetime_utc": "2026-10-01T12:00:00Z",
        "game_date_local": "2026-10-01", "dunkest_gameweek": 1,
        "mapping_verified": True, "source_retrieved_at_utc": "2026-10-01T07:00:00Z",
        "raw_payload_sha256": "a" * 64, "home_team": "ATL", "away_team": "BOS",
    }]).to_parquet(snapshot_dir / "dunkest_fixture_mapping_26_test.parquet", index=False)
    pd.DataFrame([{"player_name": "Test Player", "team_code": "ATL"}]).to_parquet(
        snapshot_dir / "player_credits_26_gw1.parquet", index=False
    )
    pd.DataFrame([{
        "coach": "Coach A", "team": "ATL", "coach_cr": 8.0,
        "opponent": "BOS", "opponent_coach_cr": 7.0, "nba_game_id": "game-1",
    }]).to_parquet(snapshot_dir / "coach_market_26_gw1.parquet", index=False)
    pd.DataFrame([{
        "player_name": "Test Player", "nba_game_id": "game-1", "expected_pdk": 8.0,
    }]).to_parquet(run_dir / "predictions.parquet", index=False)
    (run_dir / "lineups.parquet").write_bytes(b"lineups")
    candidate_path = run_dir / "player_forecast_snapshot.parquet"
    pd.DataFrame([{
        "player_name": "Test Player", "team": "ATL", "opponent": "BOS",
        "nba_game_id": "game-1", "expected_min": 30.0, "expected_pdk": 8.0,
        "fixture_verified": True,
    }]).to_parquet(candidate_path, index=False)
    candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    run_manifest = {
        "run_id": "run-1", "timestamp": "2026-10-01T10:00:00Z",
        "configuration": {
            "season": "2026-27", "season_id": "26", "target_gameweek": 1,
        },
        "player_forecast_snapshot": {
            "path": str(candidate_path), "sha256": candidate_sha, "candidate_rows": 1,
            "forecast_timestamp_utc": "2026-10-01T09:30:00Z",
            "prediction_cutoff_utc": "2026-10-01T12:00:00Z",
            "cutoff_verified": True, "cutoff_basis": "official lock feed",
            "cutoff_source_sha256": "b" * 64,
            "certification": {
                "pre_lock_eligible": True, "exact_dunkest_cutoff_verified": True,
                "reason": "verified fixture",
            },
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")
    pd.DataFrame([{
        "_requested_player_name": "Test Player", "opponentTeamCode": "BOS",
        "gameDate": "2026-10-01", "pdk": 12.5, "gameValidForDunkest": True,
    }]).to_parquet(processed / "official_dunkest_player_games_2026-27.parquet", index=False)
    pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PTS": 110},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PTS": 98},
    ]).to_parquet(processed / "team_game_logs_2026-27.parquet", index=False)
    player_logs = [
        {
            "Game_ID": "game-1", "TEAM_ABBREVIATION": team,
            "PLAYER_NAME": "Test Player" if team == "ATL" and index == 0 else f"Player {team} {index}",
            "MIN": 48.0,
        }
        for team in ("ATL", "BOS") for index in range(5)
    ]
    pd.DataFrame(player_logs).to_parquet(processed / "player_game_logs_2026-27.parquet", index=False)

    archived_files = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "archive_manifest.json":
            archived_files.append({
                "path": path.relative_to(run_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    archive_manifest_path = run_dir / "archive_manifest.json"
    archive_manifest_path.write_text(json.dumps({
        "run_id": "run-1", "pre_lock_eligible": True, "files": archived_files,
    }), encoding="utf-8")
    registry_dir = run_dir.parents[2] / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "run-1.json").write_text(json.dumps({
        "run_id": "run-1", "pre_lock_eligible": True,
        "archive_manifest_sha256": hashlib.sha256(archive_manifest_path.read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256((run_dir / "predictions.parquet").read_bytes()).hexdigest(),
        "lineups_sha256": hashlib.sha256((run_dir / "lineups.parquet").read_bytes()).hexdigest(),
        "player_forecast_snapshot_sha256": candidate_sha,
    }), encoding="utf-8")

    output_dir = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", [
        "build_dunkest_post_match_results_v1.py",
        "--data-dir", str(data_dir), "--run-dir", str(run_dir),
        "--output-dir", str(output_dir),
    ])

    assert collector.main() == 0
    archived = list((data_dir / "archive" / "26" / "gw1").glob("post_match_*/manifest.json"))
    assert len(archived) == 1
    manifest = json.loads(archived[0].read_text(encoding="utf-8"))
    assert manifest["run_id"] == "run-1"
    assert manifest["coverage_audit"]["timing_check_passed"] is True
    assert manifest["coverage_audit"]["player"]["prediction_coverage"] == 1.0
    assert manifest["coverage_audit"]["coach"]["coverage"] == 1.0
