import importlib.util
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd
import pytest

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


def _box_row(name, minutes, **extra):
    return {
        "Game_ID": "game-1", "PLAYER_NAME": name, "TEAM_ABBREVIATION": "ATL",
        "MIN": minutes, "PTS": 10, "OREB": 1, "DREB": 3, "AST": 2,
        "STL": 1, "BLK": 0, "BLKA": 0, "TOV": 1, "FG3M": 1,
        "FGA": 8, "FGM": 4, "FTA": 2, "FTM": 1, **extra,
    }


def test_outcome_panel_keeps_all_candidates_and_separates_official_and_proxy_pdk():
    forecasts = pd.DataFrame([
        {"player_name": "Test Player", "team": "ATL", "opponent": "BOS", "nba_game_id": "game-1", "expected_min": 30.0, "expected_pdk": 14.0},
        {"player_name": "Missing Player", "team": "ATL", "opponent": "BOS", "nba_game_id": "game-1", "expected_min": 12.0, "expected_pdk": 5.0},
    ])
    market = pd.DataFrame([
        {"player_name": "Test Player", "team_code": "ATL"},
        {"player_name": "Missing Player", "team_code": "ATL"},
    ])
    official = pd.DataFrame([{
        "_requested_player_name": "Test Player", "opponentTeamCode": "BOS",
        "gameDate": "2026-10-01", "pdk": 12.5, "gameValidForDunkest": True,
    }])
    panel, audit = collector.build_player_outcome_panel(
        forecasts, market, _fixtures(), official, pd.DataFrame([_box_row("Test Player", "31:30")])
    )
    played = panel.set_index("player_name").loc["Test Player"]
    missing = panel.set_index("player_name").loc["Missing Player"]

    assert len(panel) == 2
    assert played["outcome_status"] == "appeared"
    assert played["actual_minutes"] == 31.5
    assert played["actual_pdk_official"] == 12.5
    assert pd.notna(played["actual_pdk_nba_proxy"])
    assert played["actual_pdk_source"] == "official_dunkest"
    assert played["actual_pdk_nba_proxy_source"] == "nba_boxscore_rule_proxy"
    assert missing["outcome_status"] == "outcome_missing"
    assert pd.isna(missing["actual_minutes"])
    assert audit["candidate_rows"] == 2


@pytest.mark.parametrize(
    ("minutes", "comment", "expected_status"),
    [(0.0, "", "zero_minutes_verified"), (0.0, "DNP - Coach's Decision", "dnp_documented")],
)
def test_explicit_zero_log_distinguishes_verified_zero_and_documented_dnp(minutes, comment, expected_status):
    forecasts = pd.DataFrame([{
        "player_name": "Test Player", "team": "ATL", "opponent": "BOS",
        "nba_game_id": "game-1", "expected_min": 8.0, "expected_pdk": 2.0,
    }])
    market = pd.DataFrame([{"player_name": "Test Player", "team_code": "ATL"}])
    panel, _ = collector.build_player_outcome_panel(
        forecasts, market, _fixtures(), pd.DataFrame(),
        pd.DataFrame([_box_row("Test Player", minutes, COMMENT=comment)]),
    )
    assert panel.iloc[0]["outcome_status"] == expected_status
    assert panel.iloc[0]["actual_minutes"] == 0.0


def test_conflicting_log_rows_are_ambiguous_and_not_used_as_minutes_labels():
    forecasts = pd.DataFrame([{
        "player_name": "Test Player", "team": "ATL", "opponent": "BOS",
        "nba_game_id": "game-1", "expected_min": 8.0, "expected_pdk": 2.0,
    }])
    market = pd.DataFrame([{"player_name": "Test Player", "team_code": "ATL"}])
    panel, _ = collector.build_player_outcome_panel(
        forecasts, market, _fixtures(), pd.DataFrame(),
        pd.DataFrame([_box_row("Test Player", 0.0), _box_row("Test Player", 12.0)]),
    )
    assert panel.iloc[0]["outcome_status"] == "outcome_ambiguous"
    assert pd.isna(panel.iloc[0]["actual_minutes"])


def test_unverified_fixture_is_not_assigned_and_does_not_produce_zero_minutes():
    forecasts = pd.DataFrame([{
        "player_name": "Test Player", "team": "ATL", "opponent": "BOS",
        "nba_game_id": None, "expected_min": 8.0, "expected_pdk": 2.0,
    }])
    market = pd.DataFrame([{"player_name": "Test Player", "team_code": "ATL"}])
    panel, _ = collector.build_player_outcome_panel(
        forecasts, market, _fixtures(), pd.DataFrame(), pd.DataFrame()
    )
    assert panel.iloc[0]["outcome_status"] == "fixture_unverified"
    assert pd.isna(panel.iloc[0]["nba_game_id"])
    assert pd.isna(panel.iloc[0]["actual_minutes"])


def test_official_pdk_with_two_matching_fixtures_is_marked_ambiguous():
    mapping = pd.DataFrame([
        {
            "nba_game_id": "game-1", "game_datetime_utc": "2026-10-01T12:00:00Z",
            "game_date_local": "2026-10-01", "dunkest_gameweek": 1,
            "mapping_verified": True, "source_retrieved_at_utc": "2026-10-01T07:00:00Z",
            "raw_payload_sha256": "a" * 64, "home_team": "ATL", "away_team": "BOS",
        },
        {
            "nba_game_id": "game-2", "game_datetime_utc": "2026-10-01T14:00:00Z",
            "game_date_local": "2026-10-01", "dunkest_gameweek": 1,
            "mapping_verified": True, "source_retrieved_at_utc": "2026-10-01T07:00:00Z",
            "raw_payload_sha256": "b" * 64, "home_team": "ATL", "away_team": "BOS",
        },
    ])
    fixtures, _ = collector.prepare_fixture_index(mapping, 1)
    forecasts = pd.DataFrame([{
        "player_name": "Test Player", "team": "ATL", "opponent": "BOS",
        "nba_game_id": "game-1", "expected_min": 8.0, "expected_pdk": 2.0,
    }])
    market = pd.DataFrame([{"player_name": "Test Player", "team_code": "ATL"}])
    official = pd.DataFrame([{
        "_requested_player_name": "Test Player", "opponentTeamCode": "BOS",
        "gameDate": "2026-10-01", "pdk": 11.0, "gameValidForDunkest": True,
    }])
    panel, _ = collector.build_player_outcome_panel(
        forecasts, market, fixtures, official, pd.DataFrame()
    )
    assert panel.iloc[0]["actual_pdk_status"] == "ambiguous"
    assert pd.isna(panel.iloc[0]["actual_pdk_official"])


def test_player_forecast_metrics_report_coverage_and_use_only_valid_labels():
    panel = pd.DataFrame([
        {"expected_min": 10.0, "actual_minutes": 8.0, "expected_pdk": 7.0, "actual_pdk_official": 5.0, "outcome_status": "appeared"},
        {"expected_min": 4.0, "actual_minutes": 0.0, "expected_pdk": 2.0, "actual_pdk_official": 1.0, "outcome_status": "dnp_documented"},
        {"expected_min": 20.0, "actual_minutes": float("nan"), "expected_pdk": 9.0, "actual_pdk_official": float("nan"), "outcome_status": "outcome_missing"},
    ])
    summary = collector.evaluate_player_forecast_panel(panel)
    assert summary["candidate_count"] == 3
    assert summary["outcome_coverage"] == pytest.approx(2 / 3)
    assert summary["verified_zero_minutes"] == 1
    assert summary["documented_dnp"] == 1
    assert summary["minutes"]["n"] == 2
    assert summary["minutes"]["mae"] == 3.0
    assert summary["minutes"]["rmse"] == pytest.approx(10 ** 0.5)
    assert summary["minutes"]["bias"] == 3.0
    assert summary["pdk_official"]["n"] == 2
    assert summary["pdk_official"]["mae"] == 1.5


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


def test_collection_before_safe_cutoff_does_not_access_outcome_files(tmp_path, monkeypatch, capsys):
    data_dir = tmp_path / "data"
    processed = data_dir / "processed"
    processed.mkdir(parents=True)
    run_dir = tmp_path / "workspace" / "run-early"
    snapshot_dir = run_dir / "pre_match_snapshot"
    snapshot_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": "run-early",
        "configuration": {
            "season": "2026-27", "season_id": "26", "target_gameweek": 1,
        },
    }), encoding="utf-8")
    pd.DataFrame([{
        "nba_game_id": "game-1", "game_datetime_utc": "2026-10-22T00:00:00Z",
        "game_date_local": "2026-10-21", "dunkest_gameweek": 1,
        "mapping_verified": True, "source_retrieved_at_utc": "2026-10-18T07:00:00Z",
        "raw_payload_sha256": "a" * 64, "home_team": "ATL", "away_team": "BOS",
    }]).to_parquet(snapshot_dir / "dunkest_fixture_mapping_26_test.parquet", index=False)
    pd.DataFrame([{"player_name": "Test Player", "team_code": "ATL"}]).to_parquet(
        snapshot_dir / "player_credits_26_gw1.parquet", index=False
    )
    pd.DataFrame([{
        "coach": "Coach A", "team": "ATL", "coach_cr": 8.0,
        "opponent": "BOS", "opponent_coach_cr": 7.0, "nba_game_id": "game-1",
    }]).to_parquet(snapshot_dir / "coach_market_26_gw1.parquet", index=False)

    def unexpected_outcome_access(path):
        raise AssertionError(f"outcome file accessed before safe cutoff: {path}")

    class FrozenBeforeCutoff(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 10, 23, 11, 0, tzinfo=timezone.utc)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(collector, "datetime", FrozenBeforeCutoff)

    monkeypatch.setattr(collector, "fingerprint_file", unexpected_outcome_access)
    monkeypatch.setattr(collector, "read_frame", unexpected_outcome_access)
    output_dir = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", [
        "build_dunkest_post_match_results_v1.py",
        "--data-dir", str(data_dir), "--run-dir", str(run_dir),
        "--output-dir", str(output_dir),
    ])

    assert collector.main() == 2
    output = json.loads(capsys.readouterr().out)
    audit = json.loads(Path(output["audit"]).read_text(encoding="utf-8"))
    assert output["status"] == "not_ready"
    assert output["timing_check"] is False
    assert output["outcome_files_read"] is False
    assert audit["outcome_access_skipped_reason"] == "before_safe_postgame_retrieval_cutoff"
    assert audit["source_file_fingerprints"] == {}
    assert not (data_dir / "archive" / "26" / "gw1").exists()


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


def test_post_match_builder_archives_linked_results_through_shared_writer(tmp_path, monkeypatch, capsys):
    data_dir = tmp_path / "data"
    processed = data_dir / "processed"
    processed.mkdir(parents=True)
    archive_root = tmp_path / "archives"
    run_dir = archive_root / "season_id=26" / "gw=1" / "run-1"
    snapshot_dir = run_dir / "pre_match_snapshot"
    snapshot_dir.mkdir(parents=True)
    forecast_path = run_dir / "player_forecast_snapshot.parquet"
    candidate_forecasts = pd.DataFrame([{
        "player_name": "Test Player", "team": "ATL", "opponent": "BOS",
        "nba_game_id": "game-1", "expected_min": 30.0, "expected_pdk": 8.0,
        "fixture_verified": True,
    }])
    candidate_forecasts.to_parquet(forecast_path, index=False)
    forecast_sha = hashlib.sha256(forecast_path.read_bytes()).hexdigest()
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": "run-1",
        "timestamp": "2026-10-01T10:00:00Z",
        "configuration": {
            "season": "2026-27", "season_id": "26", "target_gameweek": 1,
        },
        "player_forecast_snapshot": {
            "path": str(forecast_path), "sha256": forecast_sha, "candidate_rows": 1,
            "forecast_timestamp_utc": "2026-10-01T09:30:00Z",
            "prediction_cutoff_utc": "2026-10-01T12:00:00Z",
            "cutoff_verified": True, "cutoff_basis": "official lock feed",
            "cutoff_source_sha256": "b" * 64,
            "certification": {
                "pre_lock_eligible": True, "exact_dunkest_cutoff_verified": True,
                "reason": "verified fixture",
            },
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
    pd.DataFrame([{"player_name": "Test Player", "nba_game_id": "game-1"}]).to_parquet(
        run_dir / "lineups.parquet", index=False
    )
    pd.DataFrame([{
        "_requested_player_name": "Test Player", "opponentTeamCode": "BOS",
        "gameDate": "2026-10-01", "pdk": 12.5, "gameValidForDunkest": True,
    }]).to_parquet(processed / "official_dunkest_player_games_2026-27.parquet", index=False)
    pd.DataFrame([
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "ATL", "PTS": 110},
        {"Game_ID": "game-1", "TEAM_ABBREVIATION": "BOS", "PTS": 98},
    ]).to_parquet(processed / "team_game_logs_2026-27.parquet", index=False)
    player_logs = [_box_row("Test Player", 30.0)] + [
        {**_box_row(f"Other {team} {index}", 42.0), "TEAM_ABBREVIATION": team}
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
    registry_path = archive_root / "registry" / "run-1.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps({
        "run_id": "run-1", "pre_lock_eligible": True,
        "archive_manifest_sha256": hashlib.sha256(archive_manifest_path.read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256((run_dir / "predictions.parquet").read_bytes()).hexdigest(),
        "lineups_sha256": hashlib.sha256((run_dir / "lineups.parquet").read_bytes()).hexdigest(),
        "player_forecast_snapshot_sha256": forecast_sha,
    }), encoding="utf-8")

    frozen_bytes = forecast_path.read_bytes()
    frozen_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    checked, _ = collector.validate_frozen_forecast(run_dir, frozen_manifest)
    assert len(checked) == 1
    postcutoff_manifest = dict(frozen_manifest)
    postcutoff_manifest["player_forecast_snapshot"] = dict(frozen_manifest["player_forecast_snapshot"])
    postcutoff_manifest["player_forecast_snapshot"]["forecast_timestamp_utc"] = "2026-10-01T12:01:00Z"
    with pytest.raises(ValueError, match="not certified pre-lock"):
        collector.validate_frozen_forecast(run_dir, postcutoff_manifest)

    output_dir = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", [
        "build_dunkest_post_match_results_v1.py",
        "--data-dir", str(data_dir), "--run-dir", str(run_dir),
        "--output-dir", str(output_dir),
    ])

    assert collector.main() == 0
    assert forecast_path.read_bytes() == frozen_bytes
    archived = list((data_dir / "archive" / "26" / "gw1").glob("post_match_*/manifest.json"))
    assert len(archived) == 1
    manifest = json.loads(archived[0].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 3
    assert manifest["run_id"] == "run-1"
    assert manifest["coverage_audit"]["timing_check_passed"] is True
    assert manifest["coverage_audit"]["player"]["prediction_coverage"] == 1.0
    assert manifest["coverage_audit"]["coach"]["coverage"] == 1.0
    fingerprints = manifest["source_file_fingerprints"]
    assert set(fingerprints) == {
        "official_player_games", "team_logs", "nba_player_logs_for_overtime",
        "frozen_run_manifest", "frozen_predictions", "fixture_mapping",
        "player_market", "coach_market", "pre_lock_archive_manifest", "pre_lock_registry",
    }
    official_source = processed / "official_dunkest_player_games_2026-27.parquet"
    assert fingerprints["official_player_games"]["sha256"] == hashlib.sha256(
        official_source.read_bytes()
    ).hexdigest()
    assert all(len(source["sha256"]) == 64 for source in fingerprints.values())
    registry_path = archived[0].parent.parent / "registry" / f"{archived[0].parent.name}.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["manifest_sha256"] == hashlib.sha256(archived[0].read_bytes()).hexdigest()
    first_output = json.loads(capsys.readouterr().out)
    first_audit = Path(first_output["audit"])
    first_audit_bytes = first_audit.read_bytes()
    assert manifest["collection_id"] in first_audit.name

    # Re-running collection is idempotent for the immutable outcome set.
    assert collector.main() == 0
    assert forecast_path.read_bytes() == frozen_bytes
    second_output = json.loads(capsys.readouterr().out)
    assert Path(second_output["audit"]) != first_audit
    assert first_audit.read_bytes() == first_audit_bytes
    assert len(list((data_dir / "archive" / "26" / "gw1").glob("post_match_*/manifest.json"))) == 1

    original_build_player_actuals = collector.build_player_actuals

    def change_official_results_after_read(*args, **kwargs):
        result = original_build_player_actuals(*args, **kwargs)
        official_source.write_bytes(official_source.read_bytes() + b"changed-after-read")
        return result

    monkeypatch.setattr(collector, "build_player_actuals", change_official_results_after_read)
    with pytest.raises(RuntimeError, match="inputs changed while actuals were being built"):
        collector.main()
    assert len(list((data_dir / "archive" / "26" / "gw1").glob("post_match_*/manifest.json"))) == 1
