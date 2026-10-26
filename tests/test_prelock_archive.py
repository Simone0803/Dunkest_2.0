from __future__ import annotations
import importlib.util
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prelock_archive", ROOT / "scripts/archive_dunkest_pre_lock_run_v1.py")
archive = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(archive)


def make_run(tmp_path: Path, *, unknown_fixture_time: bool = False) -> Path:
    run_id = "run_test_001"
    run = tmp_path / "predictions" / run_id
    snap = run / "pre_match_snapshot"
    snap.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "configuration": {"season_id": "26", "target_gameweek": 1},
        "inputs": [],
    }
    (run / "manifest.json").write_text(json.dumps(manifest))
    (run / "predictions.parquet").write_bytes(b"prediction-bytes")
    (run / "lineups.parquet").write_bytes(b"lineup-bytes")
    forecast_bytes = b"candidate-forecast-bytes"
    (run / "player_forecast_snapshot.parquet").write_bytes(forecast_bytes)
    import pandas as pd
    feature_path = run / "runtime_feature_snapshot.parquet"
    pd.DataFrame([{
        "forecast_record_id": "record-1", "dunkest_player_id": "dk-1",
        "canonical_player_id": "dk-1", "nba_game_id": "nba-1",
        "player_key": "player-one", "feature_match_status": "missing",
        "candidate_key_count": 1, "source_feature_row_count": 0,
    }]).to_parquet(feature_path, index=False)
    manifest["player_forecast_snapshot"] = {
        "path": "player_forecast_snapshot.parquet",
        "sha256": hashlib.sha256(forecast_bytes).hexdigest(),
        "candidate_rows": 1,
        "certification": {"pre_lock_eligible": False},
    }
    manifest["runtime_feature_snapshot"] = {
        "path": feature_path.name,
        "sha256": hashlib.sha256(feature_path.read_bytes()).hexdigest(),
        "candidate_rows": 1,
        "source_input_dataset_identifier": "test-inputs",
        "source_input_provenance": [],
        "certification_status": "valid",
    }
    manifest["dataset_identifier"] = "test-inputs"
    (run / "manifest.json").write_text(json.dumps(manifest))
    fetched = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    for name in archive.SNAPSHOTS:
        if name.startswith("dunkest_players_"):
            import pandas as pd
            pd.DataFrame([{
                "player_name": f"Player {i}", "cr": 5.0, "team_code": "BOS", "position": "G"
            } for i in range(410)]).to_parquet(snap / name, index=False)
        else:
            (snap / name).write_bytes(("snapshot:" + name).encode())
        if name in archive.FRESHNESS_REQUIRED:
            (snap / (name + ".meta.json")).write_text(json.dumps({"fetched_at": fetched}))
    return run


def make_versioned_snapshot_run(tmp_path: Path) -> tuple[Path, dict]:
    import pandas as pd

    run = make_run(tmp_path)
    manifest = archive.load_json(run / "manifest.json")
    run_at = datetime.fromisoformat(manifest["timestamp"])
    forecast_at = run_at - timedelta(seconds=30)
    cutoff = run_at + timedelta(hours=2)
    forecast_id = "player-record-1"
    config_hash, input_hash, source_hash = "b" * 64, "c" * 64, "d" * 64
    player = pd.DataFrame([{
        "forecast_run_id": manifest["run_id"], "forecast_record_id": forecast_id,
        "forecast_schema_version": 1, "player_key": "player-one",
        "dunkest_player_id": "dk-1", "canonical_player_id": "dk-1",
        "canonical_player_id_source": "dunkest_player_id", "nba_game_id": "nba-1",
        "dunkest_turn": 1, "forecast_timestamp_utc": forecast_at.isoformat(),
        "prediction_cutoff_utc": cutoff.isoformat(), "forecast_model_version": "model-v1",
        "forecast_code_version": "model-v1", "forecast_configuration_sha256": config_hash,
        "forecast_input_dataset_identifier": input_hash,
        "forecast_source_fingerprint_sha256": source_hash,
        "expected_min": 24.0, "expected_min_model_shadow": float("nan"),
        "pdk_rate_for_projection": 0.5, "p_play": 1.0, "ensemble_pdk": 12.0,
        "prior_pdk": 11.0, "implied_min": 24.0, "has_history": True, "n_games": 20,
        "historical_rf_pdk": 12.0, "historical_rf_blend_weight": 0.0,
        "component_minutes_pdk": 12.0, "component_ensemble_pdk": 12.0,
        "component_prior_pdk": 11.0, "projection_weight_minutes": 1.0,
        "projection_weight_ensemble": 0.0, "projection_weight_prior": 0.0,
        "expected_pdk_conditional": 12.0, "expected_pdk": 12.0,
    }])
    runtime = pd.DataFrame([{
        "forecast_run_id": manifest["run_id"],
        "forecast_record_id": forecast_id, "dunkest_player_id": "dk-1",
        "canonical_player_id": "dk-1", "nba_game_id": "nba-1",
        "player_key": "player-one", "feature_match_status": "matched",
        "candidate_key_count": 1, "source_feature_row_count": 1,
        "minutes_shadow_status": "unavailable", "forecast_timestamp_utc": forecast_at,
        "runtime_feature_schema_version": 1,
    }])
    shadow = pd.DataFrame([{
        "forecast_run_id": manifest["run_id"], "forecast_record_id": forecast_id,
        "canonical_player_id": "dk-1", "dunkest_player_id": "dk-1",
        "player_key": "player-one", "nba_game_id": "nba-1", "dunkest_turn": 1,
        "forecast_timestamp_utc": forecast_at, "prediction_cutoff_utc": cutoff,
        "forecast_model_version": "model-v1", "forecast_code_version": "code-v1",
        "forecast_configuration_sha256": config_hash,
        "forecast_input_dataset_identifier": input_hash,
        "forecast_source_fingerprint_sha256": source_hash,
        "expected_min_model_shadow": float("nan"), "minutes_shadow_status": "unavailable",
        "shadow_forecast_schema_version": 1,
    }])
    coaches = pd.DataFrame([{
        "forecast_run_id": manifest["run_id"], "forecast_record_id": "coach-record-1",
        "coach_key": "coach-bos", "coach": "Coach BOS", "team": "BOS",
        "nba_game_id": "nba-1", "dunkest_turn": 1,
        "forecast_timestamp_utc": forecast_at, "prediction_cutoff_utc": cutoff,
        "expected_coach_pdk": 10.0, "coach_cr": 8.0,
        "coach_forecast_schema_version": 1, "forecast_model_version": "model-v1",
        "forecast_code_version": "model-v1",
        "forecast_configuration_sha256": config_hash,
        "forecast_input_dataset_identifier": input_hash,
        "forecast_source_fingerprint_sha256": source_hash,
    }])
    frames = {
        "player_forecast_snapshot": ("player_forecast_snapshot.parquet", player),
        "runtime_feature_snapshot": ("runtime_feature_snapshot.parquet", runtime),
        "shadow_forecast_snapshot": ("shadow_forecast_snapshot.parquet", shadow),
        "coach_forecast_snapshot": ("coach_forecast_snapshot.parquet", coaches),
    }
    descriptors = {}
    for name, (filename, frame) in frames.items():
        path = run / filename
        frame.to_parquet(path, index=False)
        descriptors[name] = {"path": filename, "sha256": archive.digest(path)}
    manifest.update({
        "schema_version": 2,
        "snapshot_schemas": {
            "player_forecast": 1, "runtime_features": 1,
            "shadow_forecast": 1, "coach_forecast": 1,
        },
        "archive_status": "complete", "persistence_errors": [],
        "config_sha256": config_hash, "dataset_identifier": input_hash,
        "source_fingerprint": {"sha256": source_hash},
        "player_forecast_snapshot": {
            **descriptors["player_forecast_snapshot"], "schema_version": 1, "status": "valid",
            "candidate_rows": 1, "columns": list(player.columns),
            "forecast_timestamp_utc": forecast_at.isoformat(),
            "prediction_cutoff_utc": cutoff.isoformat(), "model_version": "model-v1",
            "certification": {"pre_lock_eligible": False},
        },
        "runtime_feature_snapshot": {
            **descriptors["runtime_feature_snapshot"], "schema_version": 1, "status": "valid",
            "candidate_rows": 1, "source_input_dataset_identifier": input_hash,
            "source_input_provenance": [], "certification_status": "valid",
        },
        "shadow_forecast_snapshot": {
            **descriptors["shadow_forecast_snapshot"], "schema_version": 1,
            "status": "unavailable", "rows": 1, "available_rows": 0,
            "optimizer_input": False,
        },
        "coach_forecast_snapshot": {
            **descriptors["coach_forecast_snapshot"], "schema_version": 1, "status": "valid",
            "rows": 1, "columns": list(coaches.columns),
        },
    })
    (run / "manifest.json").write_text(json.dumps(manifest))
    return run, manifest


def test_archive_creates_integrity_manifest_and_registry(tmp_path):
    run = make_run(tmp_path)
    out = archive.archive_run(run, tmp_path / "archive", 36)
    assert out["status"] == "archived"
    assert out["registry_status"] == "registered"
    assert out["pre_lock_eligible"] is False  # fixture freshness is deliberately unknown
    archived = Path(out["archive_path"])
    assert (archived / "archive_manifest.json").is_file()
    assert (Path(out["registry_path"])).is_file()
    assert archive.inventory(archived) == archive.load_json(archived / "archive_manifest.json")["files"]


def test_archive_registry_failure_removes_new_unregistered_bundle(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    archive_root = tmp_path / "archive"
    original_open = Path.open

    def fail_registry_creation(path, mode="r", *args, **kwargs):
        if path.parent.name == "registry" and mode == "x":
            raise OSError("simulated registry write failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_registry_creation)
    try:
        archive.archive_run(run, archive_root, 36)
    except OSError as exc:
        assert "simulated registry write failure" in str(exc)
    else:
        raise AssertionError("registry failure must not leave a published unregistered bundle")

    assert list(archive_root.glob("season_id=*/gw=*/*")) == []
    assert list((archive_root / "registry").glob("*.json")) == []
    assert list(archive_root.rglob(".*.stage.*")) == []


def test_archive_is_idempotent_but_refuses_mutated_archive(tmp_path):
    run = make_run(tmp_path)
    root = tmp_path / "archive"
    first = archive.archive_run(run, root, 36)
    second = archive.archive_run(run, root, 36)
    assert first["status"] == "archived"
    assert second["status"] == "already_archived_verified"
    archived = Path(first["archive_path"])
    (archived / "lineups.parquet").write_bytes(b"tampered")
    try:
        archive.archive_run(run, root, 36)
    except ValueError as exc:
        assert "integrity check failed" in str(exc)
    else:
        raise AssertionError("mutated archive should fail integrity verification")


def test_runtime_feature_snapshot_hash_identity_and_availability_are_checked(tmp_path):
    import pandas as pd

    run = tmp_path / "run"
    run.mkdir()
    candidates = pd.DataFrame([{
        "forecast_record_id": "record-1", "dunkest_player_id": "dk-1", "nba_game_id": "nba-1",
        "expected_min_model_shadow": 22.0, "minutes_shadow_status": "available",
    }])
    candidates.to_parquet(run / "player_forecast_snapshot.parquet", index=False)
    features = pd.DataFrame([{
        "forecast_record_id": "record-1", "dunkest_player_id": "dk-1", "canonical_player_id": "dk-1",
        "nba_game_id": "nba-1", "player_key": "player-one", "feature_match_status": "matched",
        "candidate_key_count": 1, "source_feature_row_count": 1,
        "minutes_shadow_status": "available",
        "forecast_timestamp_utc": "2030-10-20T15:00:00Z",
        "runtime_feature__available_at_utc": "2030-10-20T14:00:00Z",
        "runtime_feature__hgb_input__lag1_nba_min": 20.0,
    }])
    feature_path = run / "runtime_feature_snapshot.parquet"
    features.to_parquet(feature_path, index=False)
    manifest = {"dataset_identifier": "inputset", "inputs": [], "runtime_feature_snapshot": {
        "path": feature_path.name, "sha256": archive.digest(feature_path),
        "candidate_rows": 1, "source_input_dataset_identifier": "inputset",
        "source_input_provenance": [],
        "certification_status": "valid",
    }}

    assert archive.runtime_feature_snapshot_validation(run, manifest)["status"] == "valid"

    features.loc[0, "runtime_feature__available_at_utc"] = "2030-10-20T15:01:00Z"
    features.to_parquet(feature_path, index=False)
    manifest["runtime_feature_snapshot"]["sha256"] = archive.digest(feature_path)
    late = archive.runtime_feature_snapshot_validation(run, manifest)
    assert late["status"] == "invalid"
    assert any("after the forecast" in error for error in late["errors"])


def test_runtime_feature_snapshot_with_missing_columns_fails_cleanly(tmp_path):
    import pandas as pd

    run = make_run(tmp_path)
    feature_path = run / "runtime_feature_snapshot.parquet"
    features = pd.read_parquet(feature_path).drop(columns=["forecast_record_id"])
    features.to_parquet(feature_path, index=False)
    manifest = archive.load_json(run / "manifest.json")
    manifest["runtime_feature_snapshot"]["sha256"] = archive.digest(feature_path)

    result = archive.runtime_feature_snapshot_validation(run, manifest)

    assert result["status"] == "invalid"
    assert any("lacks fields" in error for error in result["errors"])


def test_missing_required_snapshot_fails_closed(tmp_path):
    run = make_run(tmp_path)
    (run / "pre_match_snapshot" / archive.SNAPSHOTS[0]).unlink()
    try:
        archive.archive_run(run, tmp_path / "archive", 36)
    except ValueError as exc:
        assert "snapshots missing" in str(exc)
    else:
        raise AssertionError("missing snapshot should fail closed")


def test_stale_snapshot_is_not_marked_eligible(tmp_path):
    run = make_run(tmp_path)
    name = "current_lineups_market.csv"
    sidecar = run / "pre_match_snapshot" / (name + ".meta.json")
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    sidecar.write_text(json.dumps({"fetched_at": old}))
    out = archive.archive_run(run, tmp_path / "archive", 36)
    assert out["pre_lock_eligible"] is False
    status = {x["path"]: x["status"] for x in out["snapshot_freshness"]}
    assert status[name] == "stale"


def test_snapshot_fetched_after_prediction_is_not_marked_eligible(tmp_path):
    run = make_run(tmp_path)
    manifest = archive.load_json(run / "manifest.json")
    run_time = datetime.fromisoformat(manifest["timestamp"])
    name = "current_lineups_market.csv"
    sidecar = run / "pre_match_snapshot" / (name + ".meta.json")
    sidecar.write_text(json.dumps({
        "fetched_at": (run_time + timedelta(minutes=1)).isoformat()
    }))

    status = {row["path"]: row["status"] for row in archive.freshness_report(run, manifest, 36)}
    assert status[name] == "fetched_after_prediction"
    result = archive.archive_run(run, tmp_path / "archive", 36)
    assert not result["pre_lock_eligible"]


def test_fixture_mapping_freshness_uses_embedded_source_retrieval_time(tmp_path):
    import pandas as pd
    run = make_run(tmp_path)
    manifest = archive.load_json(run / "manifest.json")
    run_time = datetime.fromisoformat(manifest["timestamp"])
    mapping_path = run / "pre_match_snapshot" / "dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet"
    pd.DataFrame([{
        "dunkest_gameweek": 1,
        "mapping_verified": True,
        "source_retrieved_at_utc": (run_time - timedelta(hours=49)).isoformat(),
    }]).to_parquet(mapping_path, index=False)
    status = {x["path"]: x["status"] for x in archive.freshness_report(run, manifest, 36)}
    assert status[mapping_path.name] == "stale"


def test_fixture_mapping_must_be_verified_and_within_prelock_window(tmp_path):
    import pandas as pd
    run = make_run(tmp_path)
    manifest = archive.load_json(run / "manifest.json")
    run_time = pd.Timestamp(manifest["timestamp"])
    mapping_path = run / "pre_match_snapshot" / "dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet"
    mapping = pd.DataFrame([{
        "nba_game_id": "0022600001",
        "game_datetime_utc": (run_time + pd.Timedelta(hours=2)).isoformat(),
        "dunkest_gameweek": 1,
        "fantasy_eligible": True,
        "mapping_verified": True,
        "source_retrieved_at_utc": (run_time - pd.Timedelta(minutes=1)).isoformat(),
        "raw_payload_sha256": "a" * 64,
    }])
    mapping.to_parquet(mapping_path, index=False)
    result = archive.fixture_mapping_validation(run, manifest, 36)
    assert result["status"] == "verified"
    mapping.loc[0, "mapping_verified"] = False
    mapping.to_parquet(mapping_path, index=False)
    result = archive.fixture_mapping_validation(run, manifest, 36)
    assert result["status"] == "invalid"
    assert any("unverified" in error for error in result["errors"])


def test_gameday_mapping_freshness_is_anchored_to_earliest_kickoff(tmp_path):
    import pandas as pd
    run = make_run(tmp_path)
    manifest = archive.load_json(run / "manifest.json")
    run_time = pd.Timestamp(manifest["timestamp"])
    mapping_path = run / "pre_match_snapshot" / "dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet"
    captured = run_time - pd.Timedelta(minutes=1)
    mapping = pd.DataFrame([
        {
            "nba_game_id": "0022600001",
            "game_datetime_utc": (run_time + pd.Timedelta(hours=2)).isoformat(),
            "dunkest_gameweek": 1, "fantasy_eligible": True, "mapping_verified": True,
            "source_retrieved_at_utc": captured.isoformat(), "raw_payload_sha256": "a" * 64,
        },
        {
            "nba_game_id": "0022600002",
            "game_datetime_utc": (run_time + pd.Timedelta(hours=60)).isoformat(),
            "dunkest_gameweek": 1, "fantasy_eligible": True, "mapping_verified": True,
            "source_retrieved_at_utc": captured.isoformat(), "raw_payload_sha256": "b" * 64,
        },
    ])
    mapping.to_parquet(mapping_path, index=False)

    result = archive.fixture_mapping_validation(run, manifest, 36)

    assert result["status"] == "verified"
    assert result["fixture_count"] == 2


def test_postmatch_pipeline_requires_certified_prelock_archive_by_default(tmp_path):
    pipeline_spec = importlib.util.spec_from_file_location(
        "postmatch_pipeline", ROOT / "scripts/run_dunkest_postmatch_oos_pipeline_v1.py"
    )
    pipeline = importlib.util.module_from_spec(pipeline_spec)
    assert pipeline_spec and pipeline_spec.loader
    pipeline_spec.loader.exec_module(pipeline)
    run = make_run(tmp_path)
    archived = archive.archive_run(run, tmp_path / "archive", 36)
    archive_dir = Path(archived["archive_path"])
    try:
        pipeline.validate_archive(archive_dir)
    except ValueError as exc:
        assert "not certified pre-lock evidence" in str(exc)
    else:
        raise AssertionError("ineligible archive must not enter certified OOS evaluation")
    checked = pipeline.validate_archive(archive_dir, allow_ineligible=True)
    assert checked["run_manifest"]["run_id"] == "run_test_001"


def test_postmatch_pipeline_passes_collected_archive_to_evaluator(tmp_path, monkeypatch):
    import subprocess
    pipeline_spec = importlib.util.spec_from_file_location(
        "postmatch_pipeline_flow", ROOT / "scripts/run_dunkest_postmatch_oos_pipeline_v1.py"
    )
    pipeline = importlib.util.module_from_spec(pipeline_spec)
    assert pipeline_spec and pipeline_spec.loader
    pipeline_spec.loader.exec_module(pipeline)

    run_dir = tmp_path / "certified-run"
    run_dir.mkdir()
    run_manifest = {
        "run_id": "run-flow-1",
        "configuration": {"season_id": "26", "target_gameweek": 1},
    }
    monkeypatch.setattr(pipeline, "validate_archive", lambda *_args, **_kwargs: {
        "run_manifest": run_manifest, "archive_manifest": {"pre_lock_eligible": True},
    })
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "build_dunkest_post_match_results_v1.py" in command[1]:
            stdout = json.dumps({"status": "archived_complete", "archive": str(tmp_path / "results")})
        else:
            stdout = json.dumps({"status": "ready", "metrics": {"player_mae": 1.0}})
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    result = pipeline.run_pipeline(
        run_dir, tmp_path / "data", tmp_path / "out"
    )

    assert result["status"] == "completed"
    assert len(calls) == 2
    assert calls[0][calls[0].index("--run-dir") + 1] == str(run_dir)
    assert calls[1][calls[1].index("--run-dir") + 1] == str(run_dir)
    assert calls[1][calls[1].index("--results-dir") + 1] == str(tmp_path / "results")
    assert result["evaluation"]["status"] == "ready"


def test_postmatch_pipeline_does_not_evaluate_when_collector_is_before_safe_cutoff(tmp_path, monkeypatch):
    import subprocess
    pipeline_spec = importlib.util.spec_from_file_location(
        "postmatch_pipeline_early_cutoff", ROOT / "scripts/run_dunkest_postmatch_oos_pipeline_v1.py"
    )
    pipeline = importlib.util.module_from_spec(pipeline_spec)
    assert pipeline_spec and pipeline_spec.loader
    pipeline_spec.loader.exec_module(pipeline)

    run_dir = tmp_path / "certified-run"
    run_dir.mkdir()
    run_manifest = {
        "run_id": "run-flow-early",
        "configuration": {"season_id": "26", "target_gameweek": 1},
    }
    monkeypatch.setattr(pipeline, "validate_archive", lambda *_args, **_kwargs: {
        "run_manifest": run_manifest, "archive_manifest": {"pre_lock_eligible": True},
    })
    calls = []

    def early_collector_result(command, **kwargs):
        calls.append(command)
        assert "build_dunkest_post_match_results_v1.py" in command[1]
        return subprocess.CompletedProcess(
            command,
            2,
            stdout=json.dumps({
                "status": "not_ready",
                "timing_check": False,
                "outcome_files_read": False,
            }),
            stderr="",
        )

    monkeypatch.setattr(pipeline.subprocess, "run", early_collector_result)
    with pytest.raises(RuntimeError, match="collection is not complete/ready"):
        pipeline.run_pipeline(run_dir, tmp_path / "data", tmp_path / "out")

    assert len(calls) == 1
    assert not (tmp_path / "out" / "evaluation").exists()


def test_capture_script_uses_canonical_archiver_and_cli_flag():
    script = (ROOT / "scripts/run_and_archive_prelock_v1.sh").read_text(encoding="utf-8")
    assert 'scripts/archive_dunkest_pre_lock_run_v1.py' in script
    assert '--max-age-hours "$MAX_HOURS"' in script
    assert 'scripts/archive_dunkest_prelock_run_v1.py" --run-id' not in script
    assert "0.0 < max_hours <= 36.0" in script
    assert "if hours <= 0:" in script
    assert "if len(candidates) != 1:" in script
    assert "Refusing to archive an ambiguous run." in script


def test_registry_checks_manifest_hash(tmp_path):
    spec2 = importlib.util.spec_from_file_location(
        "pipeline_hash_test", ROOT / "scripts/run_dunkest_postmatch_oos_pipeline_v1.py"
    )
    pipeline = importlib.util.module_from_spec(spec2)
    assert spec2 and spec2.loader
    spec2.loader.exec_module(pipeline)
    run = make_run(tmp_path)
    result = archive.archive_run(run, tmp_path / "archive", 36)
    folder = Path(result["archive_path"])
    manifest_path = folder / "archive_manifest.json"
    obj = json.loads(manifest_path.read_text())
    obj["pre_lock_eligible"] = True
    manifest_path.write_text(json.dumps(obj))
    try:
        pipeline.validate_archive(folder, allow_ineligible=True)
    except ValueError as exc:
        assert "manifest hash" in str(exc)
    else:
        raise AssertionError("registry hash verification did not detect a changed manifest")


def test_independent_reviewer_rechecks_fixture_mapping_not_only_freshness(tmp_path):
    import pandas as pd
    reviewer_spec = importlib.util.spec_from_file_location(
        "prelock_reviewer", ROOT / "scripts/review_dunkest_pre_lock_archive_v1.py"
    )
    reviewer = importlib.util.module_from_spec(reviewer_spec)
    assert reviewer_spec and reviewer_spec.loader
    reviewer_spec.loader.exec_module(reviewer)

    run = make_run(tmp_path)
    manifest = archive.load_json(run / "manifest.json")
    run_time = pd.Timestamp(manifest["timestamp"])
    mapping_path = run / "pre_match_snapshot" / "dunkest_fixture_mapping_26_lineups_browser_gw1_team_status_v2.parquet"
    mapping = pd.DataFrame([
        {
            "nba_game_id": "0022600001",
            "game_datetime_utc": (run_time + pd.Timedelta(hours=2)).isoformat(),
            "dunkest_gameweek": 1,
            "fantasy_eligible": True,
            "mapping_verified": True,
            "source_retrieved_at_utc": (run_time - pd.Timedelta(minutes=1)).isoformat(),
            "raw_payload_sha256": "a" * 64,
        },
        {
            "nba_game_id": "0022600001",
            "game_datetime_utc": (run_time + pd.Timedelta(hours=2)).isoformat(),
            "dunkest_gameweek": 1,
            "fantasy_eligible": True,
            "mapping_verified": True,
            "source_retrieved_at_utc": (run_time - pd.Timedelta(minutes=1)).isoformat(),
            "raw_payload_sha256": "b" * 64,
        },
    ])
    mapping.to_parquet(mapping_path, index=False)
    archived = archive.archive_run(run, tmp_path / "archive", 36)
    result = reviewer.review(Path(archived["archive_path"]), 36)

    assert result["integrity_ok"] is True
    assert all(item["status"] == "fresh" for item in result["rechecked_snapshot_freshness"])
    assert result["rechecked_fixture_mapping_validation"]["status"] == "invalid"
    assert result["rechecked_pre_lock_eligible"] is False


def test_versioned_snapshot_bundle_validates_all_components_and_hashes(tmp_path):
    run, manifest = make_versioned_snapshot_run(tmp_path)

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "complete"
    assert all(component["status"] == "valid" for component in result["components"].values())
    assert result["components"]["shadow_forecast_snapshot"]["rows"] == 1


def test_versioned_snapshot_accepts_documented_no_history_fallback_without_shadow_features(tmp_path):
    import pandas as pd

    run, manifest = make_versioned_snapshot_run(tmp_path)
    player_path = run / "player_forecast_snapshot.parquet"
    players = pd.read_parquet(player_path)
    players["history_source"] = "history_feature_row_missing"
    players.to_parquet(player_path, index=False)
    manifest["player_forecast_snapshot"]["sha256"] = archive.digest(player_path)
    manifest["player_forecast_snapshot"]["columns"] = list(players.columns)

    runtime_path = run / "runtime_feature_snapshot.parquet"
    runtime = pd.read_parquet(runtime_path)
    runtime["feature_match_status"] = "missing"
    runtime["candidate_key_count"] = 1
    runtime["source_feature_row_count"] = 0
    runtime.to_parquet(runtime_path, index=False)
    manifest["runtime_feature_snapshot"]["sha256"] = archive.digest(runtime_path)

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "complete"

    players["history_source"] = "current_season_game_logs"
    players.to_parquet(player_path, index=False)
    manifest["player_forecast_snapshot"]["sha256"] = archive.digest(player_path)
    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "incomplete"
    assert any("no-history fallback" in error for error in result["errors"])


def test_archive_with_existing_files_stays_ineligible_when_player_ids_are_missing(tmp_path):
    import pandas as pd

    run, manifest = make_versioned_snapshot_run(tmp_path)
    player_path = run / "player_forecast_snapshot.parquet"
    players = pd.read_parquet(player_path)
    players.loc[0, "dunkest_player_id"] = None
    players.loc[0, "canonical_player_id_source"] = "normalized_player_key"
    players.to_parquet(player_path, index=False)
    manifest["player_forecast_snapshot"]["sha256"] = archive.digest(player_path)
    (run / "manifest.json").write_text(json.dumps(manifest))

    result = archive.archive_run(run, tmp_path / "archive", 36)
    sealed = Path(result["archive_path"])
    archive_manifest = archive.load_json(sealed / "archive_manifest.json")

    assert result["pre_lock_eligible"] is False
    assert archive_manifest["pre_lock_eligible"] is False
    assert archive_manifest["versioned_forecast_snapshot_validation"]["status"] == "incomplete"
    assert any(
        "stable Dunkest player ID" in error
        for error in archive_manifest["versioned_forecast_snapshot_validation"]["errors"]
    )
    assert (sealed / "player_forecast_snapshot.parquet").is_file()


def test_versioned_snapshot_bundle_marks_missing_component_incomplete(tmp_path):
    run, manifest = make_versioned_snapshot_run(tmp_path)
    (run / "coach_forecast_snapshot.parquet").unlink()

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "incomplete"
    assert any("coach_forecast_snapshot" in error and "missing" in error for error in result["errors"])


def test_versioned_snapshot_bundle_detects_hash_mismatch(tmp_path):
    run, manifest = make_versioned_snapshot_run(tmp_path)
    manifest["runtime_feature_snapshot"]["sha256"] = "0" * 64

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "unverifiable"
    assert any("hash differs" in error for error in result["errors"])


def test_versioned_snapshot_bundle_detects_duplicate_ids_and_bad_references(tmp_path):
    import pandas as pd

    run, manifest = make_versioned_snapshot_run(tmp_path)
    player_path = run / "player_forecast_snapshot.parquet"
    players = pd.read_parquet(player_path)
    players = pd.concat([players, players], ignore_index=True)
    players.to_parquet(player_path, index=False)
    manifest["player_forecast_snapshot"]["sha256"] = archive.digest(player_path)
    manifest["player_forecast_snapshot"]["candidate_rows"] = 2
    manifest["player_forecast_snapshot"]["columns"] = list(players.columns)
    shadow_path = run / "shadow_forecast_snapshot.parquet"
    shadow = pd.read_parquet(shadow_path)
    shadow.loc[0, "forecast_record_id"] = "different-record"
    shadow.to_parquet(shadow_path, index=False)
    manifest["shadow_forecast_snapshot"]["sha256"] = archive.digest(shadow_path)

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "unverifiable"
    assert any("duplicated" in error for error in result["errors"])
    assert any("IDs do not match" in error for error in result["errors"])


def test_versioned_snapshot_bundle_rejects_timestamps_after_cutoff(tmp_path):
    import pandas as pd

    run, manifest = make_versioned_snapshot_run(tmp_path)
    player_path = run / "player_forecast_snapshot.parquet"
    players = pd.read_parquet(player_path)
    late = pd.Timestamp(manifest["player_forecast_snapshot"]["prediction_cutoff_utc"]) + pd.Timedelta(minutes=1)
    players.loc[0, "forecast_timestamp_utc"] = late.isoformat()
    players.to_parquet(player_path, index=False)
    manifest["player_forecast_snapshot"]["sha256"] = archive.digest(player_path)

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "unverifiable"
    assert any("at/after cutoff" in error for error in result["errors"])


def test_versioned_snapshot_bundle_rejects_unparseable_forecast_timestamp(tmp_path):
    import pandas as pd

    run, manifest = make_versioned_snapshot_run(tmp_path)
    player_path = run / "player_forecast_snapshot.parquet"
    players = pd.read_parquet(player_path)
    players.loc[0, "forecast_timestamp_utc"] = "not-a-timestamp"
    players.to_parquet(player_path, index=False)
    manifest["player_forecast_snapshot"]["sha256"] = archive.digest(player_path)

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "unverifiable"
    assert any("missing timestamps" in error for error in result["errors"])


def test_versioned_snapshot_bundle_flags_ambiguous_runtime_mapping(tmp_path):
    import pandas as pd

    run, manifest = make_versioned_snapshot_run(tmp_path)
    runtime_path = run / "runtime_feature_snapshot.parquet"
    runtime = pd.read_parquet(runtime_path)
    runtime.loc[0, "feature_match_status"] = "ambiguous_feature_identity"
    runtime.to_parquet(runtime_path, index=False)
    manifest["runtime_feature_snapshot"]["sha256"] = archive.digest(runtime_path)

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "mapping_ambiguous"
    assert any("ambiguous" in error for error in result["errors"])


def test_versioned_snapshot_bundle_rejects_incomplete_coach_forecast(tmp_path):
    import pandas as pd

    run, manifest = make_versioned_snapshot_run(tmp_path)
    coach_path = run / "coach_forecast_snapshot.parquet"
    coaches = pd.read_parquet(coach_path).drop(columns=["expected_coach_pdk"])
    coaches.to_parquet(coach_path, index=False)
    manifest["coach_forecast_snapshot"]["sha256"] = archive.digest(coach_path)
    manifest["coach_forecast_snapshot"]["columns"] = list(coaches.columns)

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "incomplete"
    assert any("coach forecast snapshot is incomplete" in error for error in result["errors"])


def test_versioned_snapshot_bundle_enforces_shadow_separation(tmp_path):
    run, manifest = make_versioned_snapshot_run(tmp_path)
    manifest["shadow_forecast_snapshot"]["optimizer_input"] = True

    result = archive.versioned_forecast_snapshot_validation(run, manifest)

    assert result["status"] == "unverifiable"
    assert any("excluded from optimizer" in error for error in result["errors"])

    import pandas as pd
    shadow_path = run / "shadow_forecast_snapshot.parquet"
    shadow = pd.read_parquet(shadow_path)
    shadow["expected_pdk"] = 99.0
    shadow.to_parquet(shadow_path, index=False)
    manifest["shadow_forecast_snapshot"]["sha256"] = archive.digest(shadow_path)
    manifest["shadow_forecast_snapshot"]["optimizer_input"] = False
    separated = archive.versioned_forecast_snapshot_validation(run, manifest)
    assert separated["status"] == "unverifiable"
    assert any("operational PDK prediction" in error for error in separated["errors"])


def test_legacy_archive_remains_reviewable_but_is_not_evaluation_ready(tmp_path):
    reviewer_spec = importlib.util.spec_from_file_location(
        "legacy_prelock_reviewer", ROOT / "scripts/review_dunkest_pre_lock_archive_v1.py"
    )
    reviewer = importlib.util.module_from_spec(reviewer_spec)
    assert reviewer_spec and reviewer_spec.loader
    reviewer_spec.loader.exec_module(reviewer)
    run = make_run(tmp_path)
    archive_root = tmp_path / "archive"
    archived = archive.archive_run(run, archive_root, 36)

    result = reviewer.review(Path(archived["archive_path"]), 36)

    assert result["integrity_ok"] is True
    assert result["status"] == "legacy"
    assert result["rechecked_pre_lock_eligible"] is False


def test_schema_v1_archived_bundle_and_registry_remain_readable_without_rewrite(tmp_path):
    reviewer_spec = importlib.util.spec_from_file_location(
        "schema_v1_prelock_reviewer", ROOT / "scripts/review_dunkest_pre_lock_archive_v1.py"
    )
    reviewer = importlib.util.module_from_spec(reviewer_spec)
    assert reviewer_spec and reviewer_spec.loader
    reviewer_spec.loader.exec_module(reviewer)
    run = make_run(tmp_path)
    archive_root = tmp_path / "archive"
    archived = archive.archive_run(run, archive_root, 36)
    archive_dir = Path(archived["archive_path"])
    archive_manifest_path = archive_dir / "archive_manifest.json"
    archive_manifest = archive.load_json(archive_manifest_path)
    archive_manifest["schema_version"] = 1
    archive_manifest.pop("versioned_forecast_snapshot_validation", None)
    archive_manifest_path.write_text(json.dumps(archive_manifest))
    registry_path = Path(archived["registry_path"])
    registry = archive.load_json(registry_path)
    registry["schema_version"] = 1
    registry.pop("shadow_forecast_snapshot_sha256", None)
    registry.pop("coach_forecast_snapshot_sha256", None)
    registry.pop("versioned_forecast_snapshot_validation", None)
    registry["archive_manifest_sha256"] = archive.digest(archive_manifest_path)
    registry_path.write_text(json.dumps(registry))
    before = {
        path.relative_to(archive_dir).as_posix(): archive.digest(path)
        for path in archive_dir.rglob("*") if path.is_file()
    }

    result = reviewer.review(archive_dir, 36)

    after = {
        path.relative_to(archive_dir).as_posix(): archive.digest(path)
        for path in archive_dir.rglob("*") if path.is_file()
    }
    assert result["integrity_ok"] is True
    assert result["status"] == "legacy"
    assert result["rechecked_pre_lock_eligible"] is False
    assert after == before
    assert archive.archive_run(run, archive_root, 36)["status"] == "already_archived_verified"


def test_complete_versioned_archive_is_reviewed_but_not_certified_without_lock_evidence(tmp_path):
    reviewer_spec = importlib.util.spec_from_file_location(
        "complete_prelock_reviewer", ROOT / "scripts/review_dunkest_pre_lock_archive_v1.py"
    )
    reviewer = importlib.util.module_from_spec(reviewer_spec)
    assert reviewer_spec and reviewer_spec.loader
    reviewer_spec.loader.exec_module(reviewer)
    run, _ = make_versioned_snapshot_run(tmp_path)
    archived = archive.archive_run(run, tmp_path / "archive", 36)

    result = reviewer.review(Path(archived["archive_path"]), 36)

    assert archived["forecast_snapshot_validation"]["status"] == "complete"
    assert result["integrity_ok"] is True
    assert result["rechecked_versioned_forecast_snapshot_validation"]["status"] == "complete"
    assert result["status"] == "not_pre_lock_eligible"
    assert result["rechecked_pre_lock_eligible"] is False


def test_reviewer_never_marks_incomplete_v2_archive_ready(tmp_path):
    reviewer_spec = importlib.util.spec_from_file_location(
        "incomplete_prelock_reviewer", ROOT / "scripts/review_dunkest_pre_lock_archive_v1.py"
    )
    reviewer = importlib.util.module_from_spec(reviewer_spec)
    assert reviewer_spec and reviewer_spec.loader
    reviewer_spec.loader.exec_module(reviewer)
    run, _ = make_versioned_snapshot_run(tmp_path)
    (run / "coach_forecast_snapshot.parquet").unlink()
    archived = archive.archive_run(run, tmp_path / "archive", 36)

    result = reviewer.review(Path(archived["archive_path"]), 36)

    assert archived["pre_lock_eligible"] is False
    assert result["status"] == "incomplete"
    assert result["rechecked_pre_lock_eligible"] is False
    assert result["rechecked_versioned_forecast_snapshot_validation"]["status"] == "incomplete"


def test_reviewer_hash_error_raises_instead_of_returning_a_valid_review(tmp_path):
    reviewer_spec = importlib.util.spec_from_file_location(
        "corrupt_prelock_reviewer", ROOT / "scripts/review_dunkest_pre_lock_archive_v1.py"
    )
    reviewer = importlib.util.module_from_spec(reviewer_spec)
    assert reviewer_spec and reviewer_spec.loader
    reviewer_spec.loader.exec_module(reviewer)
    run, _ = make_versioned_snapshot_run(tmp_path)
    archived = archive.archive_run(run, tmp_path / "archive", 36)
    archive_dir = Path(archived["archive_path"])
    (archive_dir / "coach_forecast_snapshot.parquet").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="Archived file hashes do not match"):
        reviewer.review(archive_dir, 36)


def test_postmatch_gate_accepts_complete_snapshot_bundle_only_as_unverified_diagnostic(tmp_path):
    pipeline_spec = importlib.util.spec_from_file_location(
        "complete_bundle_postmatch_gate", ROOT / "scripts/run_dunkest_postmatch_oos_pipeline_v1.py"
    )
    pipeline = importlib.util.module_from_spec(pipeline_spec)
    assert pipeline_spec and pipeline_spec.loader
    pipeline_spec.loader.exec_module(pipeline)
    run, _ = make_versioned_snapshot_run(tmp_path)
    archived = archive.archive_run(run, tmp_path / "archive", 36)

    checked = pipeline.validate_archive(Path(archived["archive_path"]), allow_ineligible=True)

    assert checked["forecast_snapshot_validation"]["status"] == "complete"
    assert archived["pre_lock_eligible"] is False


def test_postmatch_gate_rejects_incomplete_v2_even_in_diagnostic_mode(tmp_path):
    pipeline_spec = importlib.util.spec_from_file_location(
        "incomplete_bundle_postmatch_gate", ROOT / "scripts/run_dunkest_postmatch_oos_pipeline_v1.py"
    )
    pipeline = importlib.util.module_from_spec(pipeline_spec)
    assert pipeline_spec and pipeline_spec.loader
    pipeline_spec.loader.exec_module(pipeline)
    run, _ = make_versioned_snapshot_run(tmp_path)
    (run / "coach_forecast_snapshot.parquet").unlink()
    archived = archive.archive_run(run, tmp_path / "archive", 36)

    with pytest.raises(ValueError, match="snapshots are incomplete or unverifiable"):
        pipeline.validate_archive(Path(archived["archive_path"]), allow_ineligible=True)



def test_snapshot_names_follow_target_season_and_gameweek(tmp_path):
    run = make_run(tmp_path)
    manifest = archive.load_json(run / "manifest.json")
    manifest["configuration"]["target_gameweek"] = 2
    names = archive.snapshot_names(manifest)
    assert "player_credits_26_gw2.parquet" in names
    assert "injuries_26_gw2.parquet" in names
    assert "coach_market_26_gw2.parquet" in names
    assert "dunkest_fixture_mapping_26_lineups_browser_gw2_team_status_v2.parquet" in names
    # The previous GW1 snapshot must not accidentally satisfy GW2 freshness.
    statuses = {row["path"]: row["status"] for row in archive.freshness_report(run, manifest, 36)}
    assert statuses["player_credits_26_gw2.parquet"] == "missing"
    assert "player_credits_26_gw1.parquet" not in statuses


def test_archive_uses_target_gameweek_snapshot_names_and_refuses_missing_gw2(tmp_path):
    run = make_run(tmp_path)
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["configuration"]["target_gameweek"] = 2
    manifest_path.write_text(json.dumps(manifest))
    try:
        archive.archive_run(run, tmp_path / "archive", 36)
    except ValueError as exc:
        assert "player_credits_26_gw2.parquet" in str(exc)
    else:
        raise AssertionError("GW1 snapshots must not satisfy a GW2 archive")


def test_snapshot_content_validation_rejects_truncated_player_market(tmp_path):
    import pandas as pd
    run = make_run(tmp_path)
    snap = run / "pre_match_snapshot"
    pd.DataFrame([{"player_name": "Example", "cr": 10, "team": "BOS", "role": "G"}]).to_csv(
        snap / "current_lineups_market.csv", index=False
    )
    manifest = archive.load_json(run / "manifest.json")
    result = {row["path"]: row for row in archive.snapshot_content_validation(run, manifest)}
    assert result["current_lineups_market.csv"]["status"] == "invalid"
    assert any("too few rows" in err for err in result["current_lineups_market.csv"]["errors"])


def test_missing_market_is_archived_for_diagnostics_and_reviewer_keeps_it_incomplete(tmp_path):
    reviewer_spec = importlib.util.spec_from_file_location(
        "missing_market_prelock_reviewer", ROOT / "scripts/review_dunkest_pre_lock_archive_v1.py"
    )
    reviewer = importlib.util.module_from_spec(reviewer_spec)
    assert reviewer_spec and reviewer_spec.loader
    reviewer_spec.loader.exec_module(reviewer)
    run, _ = make_versioned_snapshot_run(tmp_path)
    manifest_path = run / "manifest.json"
    manifest = archive.load_json(manifest_path)
    market_name = "dunkest_players_26_gw1.parquet"
    market_path = run / "pre_match_snapshot" / market_name
    market_path.unlink()
    sidecar = market_path.with_name(market_name + ".meta.json")
    sidecar.unlink(missing_ok=True)
    manifest["required_pre_match_inputs"] = {
        "dunkest_market_snapshot": {
            "status": "missing", "path": market_name, "sha256": None, "source": None,
            "reason": "required pre-lock Dunkest market snapshot was absent at archive time",
        }
    }
    manifest["archive_status"] = "incomplete"
    manifest["snapshot_set_complete"] = False
    manifest_path.write_text(json.dumps(manifest))

    archived = archive.archive_run(run, tmp_path / "archive", 36)

    assert archived["status"] == "archived"
    assert archived["pre_lock_eligible"] is False
    review = reviewer.review(Path(archived["archive_path"]), 36)
    assert review["status"] == "incomplete"
    assert review["rechecked_pre_lock_eligible"] is False
    assert review["rechecked_required_pre_match_inputs"]["dunkest_market_snapshot"]["status"] == "missing"


def test_snapshot_content_validation_checks_target_round_and_coach_coverage(tmp_path):
    import pandas as pd
    run = make_run(tmp_path)
    snap = run / "pre_match_snapshot"
    credits_path = snap / "player_credits_26_gw1.parquet"
    pd.DataFrame([{
        "player_name": f"Player {i}", "team_code": "BOS", "role": "G", "cr": 5.0, "gameweek": 2
    } for i in range(410)]).to_parquet(credits_path, index=False)
    coach_path = snap / "coach_market_26_gw1.parquet"
    pd.DataFrame([{
        "coach": f"Coach {i}", "team": f"Team {i}", "coach_cr": 5.0,
        "opponent": "Opponent", "opponent_coach": "Other", "opponent_coach_cr": 5.0, "gameweek": 1
    } for i in range(29)]).to_parquet(coach_path, index=False)
    manifest = archive.load_json(run / "manifest.json")
    result = {row["path"]: row for row in archive.snapshot_content_validation(run, manifest)}
    assert result[credits_path.name]["status"] == "invalid"
    assert any("not linked to target gameweek" in err for err in result[credits_path.name]["errors"])
    assert result[coach_path.name]["status"] == "invalid"
    assert any("all 30 NBA teams" in err for err in result[coach_path.name]["errors"])
