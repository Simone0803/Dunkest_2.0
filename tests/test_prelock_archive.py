from __future__ import annotations
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    fetched = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    for name in archive.SNAPSHOTS:
        (snap / name).write_bytes(("snapshot:" + name).encode())
        if name in archive.FRESHNESS_REQUIRED:
            (snap / (name + ".meta.json")).write_text(json.dumps({"fetched_at": fetched}))
    return run


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


def test_capture_script_uses_canonical_archiver_and_cli_flag():
    script = (ROOT / "scripts/run_and_archive_prelock_v1.sh").read_text(encoding="utf-8")
    assert 'scripts/archive_dunkest_pre_lock_run_v1.py' in script
    assert '--max-age-hours "$MAX_HOURS"' in script
    assert 'scripts/archive_dunkest_prelock_run_v1.py" --run-id' not in script


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
