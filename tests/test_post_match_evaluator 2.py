import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "evaluate_archived_run_post_match_v1",
    ROOT / "scripts" / "evaluate_archived_run_post_match_v1.py",
)
evaluator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evaluator)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_fixture_run(tmp_path: Path, with_results: bool = True):
    data = tmp_path / "data"
    run_id = "20261001T080000Z_test0001"
    run_dir = data / "predictions" / run_id
    snapshot = run_dir / "pre_match_snapshot"
    snapshot.mkdir(parents=True)

    mapping_path = snapshot / "dunkest_fixture_mapping_26_gw1.parquet"
    pd.DataFrame([{
        "nba_game_id": "game-1",
        "game_datetime_utc": "2026-10-01T12:00:00Z",
        "dunkest_gameweek": 1,
        "mapping_verified": True,
        "source_retrieved_at_utc": "2026-10-01T07:00:00Z",
        "raw_payload_sha256": "a" * 64,
    }]).to_parquet(mapping_path, index=False)
    (run_dir / "predictions.parquet").parent.mkdir(parents=True, exist_ok=True)
    player_names = [f"Test Player {i}" for i in range(1, 11)]
    pd.DataFrame([{
        "player_name": name,
        "nba_game_id": "game-1",
        "expected_pdk": 8.0,
        "p10": 2.0,
        "p90": 14.0,
    } for name in player_names]).to_parquet(run_dir / "predictions.parquet", index=False)
    lineup_rows = []
    for i, name in enumerate(player_names, start=1):
        slot = "Starter" if i <= 5 else "Sixth Man" if i == 6 else "Bench"
        lineup_rows.append({
            "rank": 1,
            "player_name": name,
            "nba_game_id": "game-1",
            "dunkest_turn": 1,
            "slot": slot,
            "slot_turn_1": slot,
            "captain": "Test Player 1",
            "coach": "Test Coach",
            "coach_nba_game_id": "game-1",
            "num_transfers": 0,
            "transfer_malus": 3.5,
        })
    pd.DataFrame(lineup_rows).to_parquet(run_dir / "lineups.parquet", index=False)

    coach_market_path = snapshot / "coach_market_26_gw1.parquet"
    pd.DataFrame([{
        "coach": "Test Coach", "team": "BOS", "coach_cr": 10.0,
        "opponent": "NYK", "opponent_coach_cr": 10.0,
        "nba_game_id": "game-1", "fixture_source": "test", "date": "2026-10-01",
    }]).to_parquet(coach_market_path, index=False)
    snapshot_files = [{
        "path": mapping_path.name,
        "sha256": _sha(mapping_path),
        "source": "test fixture mapping",
    }, {
        "path": coach_market_path.name,
        "sha256": _sha(coach_market_path),
        "source": "test coach market",
    }]
    # Model-input snapshots need acquisition metadata, not just a pre-tipoff run timestamp.
    input_frames = {
        "player_credits_26_gw1.parquet": pd.DataFrame([{
            "player_name": name, "team_code": "BOS", "role": "G", "gameweek": 1, "cr": 10.0,
        } for name in player_names]),
        "injuries_26_gw1.parquet": pd.DataFrame([{
            "player_name": name, "team": "BOS", "status": "available", "gameweek": 1,
        } for name in player_names]),
        "current_lineups_market.csv": pd.DataFrame([{"player_name": name, "team": "BOS", "role": "G"} for name in player_names]),
        "lineups_availability.csv": pd.DataFrame([{
            "player_name": name, "status": "available", "dunkest_turn": 1,
            "observed_at_utc": "2026-10-01T07:00:00Z",
        } for name in player_names]),
    }
    input_frames["coach_market_26_gw1.parquet"] = pd.read_parquet(coach_market_path)
    for name, frame in input_frames.items():
        path = snapshot / name
        if path.name != coach_market_path.name:
            if path.suffix == ".parquet":
                frame.to_parquet(path, index=False)
            else:
                frame.to_csv(path, index=False)
        if not any(entry["path"] == path.name for entry in snapshot_files):
            snapshot_files.append({"path": path.name, "sha256": _sha(path), "source": "test market input"})
        metadata_path = Path(str(path) + ".meta.json")
        metadata_path.write_text(json.dumps({
            "fetched_at": "2026-10-01T07:00:00Z",
            "source": "official test fixture",
            "dunkest_turn": 1,
        }), encoding="utf-8")
        snapshot_files.append({"path": metadata_path.name, "sha256": _sha(metadata_path), "source": "test acquisition metadata"})
    manifest = {
        "run_id": run_id,
        "timestamp": "2026-10-01T08:00:00Z",
        "configuration": {"season_id": "26", "target_gameweek": 1, "transfer_penalty": 0.0},
        "pre_match_snapshot": {"path": str(snapshot), "files": snapshot_files},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result_dir = None
    if with_results:
        result_dir = data / "archive" / "26" / "gw1" / "post_match_test0001"
        result_dir.mkdir(parents=True)
        pd.DataFrame([{
            "player_name": name,
            "nba_game_id": "game-1",
            "actual_pdk": 10.0,
        } for name in player_names]).to_parquet(result_dir / "player_results.parquet", index=False)
        pd.DataFrame([{
            "coach": "Test Coach",
            "nba_game_id": "game-1",
            "actual_coach_pdk": 7.0,
        }]).to_parquet(result_dir / "coach_results.parquet", index=False)
        result_manifest = {
            "schema_version": 2,
            "season_id": "26",
            "dunkest_gameweek": 1,
            "retrieved_at_utc": "2026-10-01T17:00:00Z",
            "source": "official test fixture",
            "sha256": {
                "player_results.parquet": _sha(result_dir / "player_results.parquet"),
                "coach_results.parquet": _sha(result_dir / "coach_results.parquet"),
            },
        }
        result_manifest_path = result_dir / "manifest.json"
        result_manifest_path.write_text(json.dumps(result_manifest), encoding="utf-8")
        registry_dir = result_dir.parent / "registry"
        registry_dir.mkdir(parents=True)
        (registry_dir / f"{result_dir.name}.json").write_text(json.dumps({
            "schema_version": 1,
            "archive_id": result_dir.name,
            "season_id": "26",
            "dunkest_gameweek": 1,
            "manifest_sha256": _sha(result_manifest_path),
            "sha256": result_manifest["sha256"],
        }), encoding="utf-8")
    return run_dir, result_dir


def test_forecast_metrics_and_lineup_score_from_fixture_linked_actuals(tmp_path):
    run_dir, results_dir = _make_fixture_run(tmp_path)
    report, matched, lineups = evaluator.evaluate_run(run_dir, results_dir)

    assert report["status"] == "ready"
    assert len(matched) == 10
    assert report["metrics"]["player_mae"] == pytest.approx(2.0)
    assert report["metrics"]["player_rmse"] == pytest.approx(2.0)
    assert bool(lineups.iloc[0]["roster_size_valid"])
    # Five starters (captain at 1.5x), sixth man, four bench players at 0.5x,
    # plus 7 coach points, minus the frozen 3.5 transfer malus.
    assert lineups.iloc[0]["actual_team_score"] == pytest.approx(88.5)
    assert report["metrics"]["rank1_realized_team_score"] == pytest.approx(88.5)


def test_evaluation_rejects_lineup_with_fewer_than_ten_unique_players(tmp_path):
    run_dir, results_dir = _make_fixture_run(tmp_path)
    lineup_path = run_dir / "lineups.parquet"
    lineups = pd.read_parquet(lineup_path).iloc[:-1]
    lineups.to_parquet(lineup_path, index=False)

    report, _, scored = evaluator.evaluate_run(run_dir, results_dir)

    assert report["status"] == "partial"
    assert len(scored) == 1
    assert scored.iloc[0]["selected_player_rows"] == 9
    assert scored.iloc[0]["unique_players"] == 9
    assert not bool(scored.iloc[0]["roster_size_valid"])
    assert not bool(scored.iloc[0]["complete"])
    assert pd.isna(scored.iloc[0]["actual_team_score"])


def test_evaluation_stays_not_ready_when_no_post_match_archive_exists(tmp_path):
    run_dir, _ = _make_fixture_run(tmp_path, with_results=False)
    report, matched, lineups = evaluator.evaluate_run(run_dir, None)

    assert report["status"] == "not_ready"
    result_check = next(item for item in report["checks"] if item["check"] == "post_match_results")
    assert not result_check["passed"]
    assert matched.empty
    assert lineups.empty


def test_pre_match_snapshot_hash_mismatch_is_rejected(tmp_path):
    run_dir, results_dir = _make_fixture_run(tmp_path)
    mapping_path = run_dir / "pre_match_snapshot" / "dunkest_fixture_mapping_26_gw1.parquet"
    mapping_path.write_bytes(mapping_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="hash mismatch"):
        evaluator.evaluate_run(run_dir, results_dir)



def test_legacy_undated_availability_csv_does_not_override_official_injury_snapshot(tmp_path):
    run_dir, results_dir = _make_fixture_run(tmp_path)
    snapshot = run_dir / "pre_match_snapshot"
    availability_path = snapshot / "lineups_availability.csv"
    availability = pd.read_csv(availability_path).drop(columns=["observed_at_utc"])
    availability.to_csv(availability_path, index=False)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["pre_match_snapshot"]["files"]:
        if entry["path"] == availability_path.name:
            entry["sha256"] = _sha(availability_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report, _, _ = evaluator.evaluate_run(run_dir, results_dir)

    assert report["status"] == "ready"
    assert report["run"]["pre_match_inputs_complete"]
    assert "lineups_availability" not in report["run"]["snapshot_capture_checks"]

def test_evaluation_rejects_input_captured_at_or_after_tipoff(tmp_path):
    run_dir, results_dir = _make_fixture_run(tmp_path)
    snapshot = run_dir / "pre_match_snapshot"
    metadata_path = snapshot / "current_lineups_market.csv.meta.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["fetched_at"] = "2026-10-01T12:00:00Z"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["pre_match_snapshot"]["files"]:
        if entry["path"] == metadata_path.name:
            entry["sha256"] = _sha(metadata_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report, _, _ = evaluator.evaluate_run(run_dir, results_dir)

    assert report["status"] == "partial"
    check = next(item for item in report["checks"] if item["check"] == "pre_match_snapshot_capture_times")
    assert not check["passed"]
    market_check = report["run"]["snapshot_capture_checks"]["current_lineups_market"]
    assert not market_check["timestamp_valid"]
    assert market_check["files"][0]["reason"] != "ok"


def test_legacy_availability_csv_is_not_a_required_snapshot(tmp_path):
    run_dir, results_dir = _make_fixture_run(tmp_path)
    snapshot = run_dir / "pre_match_snapshot"
    availability_path = snapshot / "lineups_availability.csv"
    availability_path.unlink()
    (snapshot / "lineups_availability.csv.meta.json").unlink()
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pre_match_snapshot"]["files"] = [
        entry for entry in manifest["pre_match_snapshot"]["files"]
        if entry["path"] not in {"lineups_availability.csv", "lineups_availability.csv.meta.json"}
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report, _, _ = evaluator.evaluate_run(run_dir, results_dir)

    assert report["status"] == "ready"
    assert report["run"]["pre_match_inputs_complete"]
    assert "lineups_availability" not in report["run"]["snapshot_capture_checks"]


def test_conflicting_duplicate_actuals_are_rejected():
    frame = pd.DataFrame([
        {"player_name": "Test Player", "nba_game_id": "game-1", "actual_pdk": 5.0},
        {"player_name": "Test Player", "nba_game_id": "game-1", "actual_pdk": 9.0},
    ])
    with pytest.raises(ValueError, match="Conflicting player scores"):
        evaluator.canonical_actuals(frame, "player", ("actual_pdk",))



def test_evaluation_requires_each_frozen_coach_fixture_pair(tmp_path):
    run_dir, results_dir = _make_fixture_run(tmp_path)
    snapshot = run_dir / "pre_match_snapshot"
    coach_market_path = snapshot / "coach_market_26_gw1.parquet"
    coach_market = pd.read_parquet(coach_market_path)
    coach_market.loc[len(coach_market)] = {"coach": "Other Coach", "nba_game_id": "game-1"}
    coach_market.to_parquet(coach_market_path, index=False)

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["pre_match_snapshot"]["files"]:
        if entry["path"] == coach_market_path.name:
            entry["sha256"] = _sha(coach_market_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report, _, lineups = evaluator.evaluate_run(run_dir, results_dir)

    assert report["status"] == "partial"
    coach_check = next(x for x in report["checks"] if x["check"] == "coach_actual_coverage")
    assert not coach_check["passed"]
    assert "1/2 frozen coach-fixture pairs" in coach_check["detail"]
    assert bool(lineups.iloc[0]["complete"])


def test_explicit_workspace_run_directory_is_resolved_without_copying(tmp_path):
    run_dir, _ = _make_fixture_run(tmp_path, with_results=False)
    workspace_run = tmp_path / "workspaces" / "isolated" / run_dir.name
    workspace_run.parent.mkdir(parents=True)
    # Move the fixture run outside data/predictions to mimic the frozen preflight workspace.
    import shutil
    shutil.move(str(run_dir), str(workspace_run))

    resolved = evaluator.resolve_run_dir(tmp_path / "data", "26", 1, run_dir=workspace_run)

    assert resolved == workspace_run.resolve()
    assert (resolved / "manifest.json").is_file()


def test_explicit_workspace_run_directory_rejects_run_id_mismatch(tmp_path):
    run_dir, _ = _make_fixture_run(tmp_path, with_results=False)

    with pytest.raises(ValueError, match="does not match manifest run_id"):
        evaluator.resolve_run_dir(tmp_path / "data", "26", 1, run_id="wrong-id", run_dir=run_dir)
