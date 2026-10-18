import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.pipeline.season_opener import _model_artifact_metadata
from dunkest.report.artifacts import (
    _source_fingerprint,
    save_post_match_snapshot,
    save_pre_match_snapshot,
    save_run_artifacts,
)


def test_source_fingerprint_covers_operational_scripts_and_config(tmp_path):
    files = {
        "src/dunkest/example.py": "VALUE = 1\n",
        "scripts/capture.py": "print('capture')\n",
        "config/season_opener.yaml": "training_target: target_pdk_official\n",
        "run-season-opener.sh": "echo run\n",
        "tests/not_runtime.py": "SHOULD_NOT_BE_INCLUDED = True\n",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    settings = SimpleNamespace(root=tmp_path)
    first = _source_fingerprint(settings)
    assert first["python_files"] == 2
    assert first["shell_files"] == 1
    assert first["config_files"] == 1
    assert first["files"] == 4

    (tmp_path / "scripts/capture.py").write_text(
        "print('capture changed')\n", encoding="utf-8"
    )
    second = _source_fingerprint(settings)
    assert second["sha256"] != first["sha256"]

    (tmp_path / "config/season_opener.yaml").write_text(
        "training_target: explicit_proxy\n", encoding="utf-8"
    )
    third = _source_fingerprint(settings)
    assert third["sha256"] != second["sha256"]


from dunkest.data.dunkest.fixtures import load_pre_match_snapshot


def test_run_manifest_captures_reproducibility_metadata(tmp_path):
    settings = Settings(
        data_dir=str(tmp_path),
        target_gameweek=2,
        random_state=19,
        rolling_windows=[3, 7],
    )
    processed = tmp_path / "processed"
    processed.mkdir()
    player_cache = processed / f"player_game_logs_{settings.season}.parquet"
    player_cache.write_bytes(b"captured-input")
    player_cache.with_suffix(player_cache.suffix + ".meta.json").write_text(
        json.dumps({"fetched_at": "2026-10-01T12:00:00+00:00", "source": "test", "rows": 12}),
        encoding="utf-8",
    )
    minute_label_cache = processed / "dunkest_nba_player_games_enriched_2018-25_v1.parquet"
    minute_label_cache.write_bytes(b"minute-label-training-input")
    official_overlay = processed / f"player_game_logs_{settings.season}_official_pdk_overlay_v4.parquet"
    official_overlay.write_bytes(b"official-pdk-inference-input")
    plus_anchor = processed / "plusvalenza_history_multiseason_26_pre_gw1_5y_nba_v4.parquet"
    plus_anchor.write_bytes(b"plusvalenza-anchor-input")
    plus_season = processed / "plusvalenza_history_nba_25_through_gw91_v4.parquet"
    plus_season.write_bytes(b"plusvalenza-season-input")
    market_file = tmp_path / "current_lineups_market.csv"
    market_file.write_text("player_name,cr\nPlayer One,8.0\n", encoding="utf-8")
    rookie_official = tmp_path / "rookie_official_pdk.csv"
    rookie_official.write_text("player_key,draft_year\nplayer-one,2025\n", encoding="utf-8")
    market_meta = {"fetched_at": "2026-10-12T20:47:03+00:00", "source": "official-lineups-api"}
    market_file.with_name(market_file.name + ".meta.json").write_text(
        json.dumps(market_meta), encoding="utf-8"
    )
    availability_file = tmp_path / "lineups_availability.csv"
    availability_file.write_text(
        "player_name,team,status,dunkest_turn,observed_at_utc\n"
        "Player One,BOS,OUT,1,2026-10-12T20:40:00+00:00\n",
        encoding="utf-8",
    )
    availability_meta = {
        "fetched_at": "2026-10-12T20:47:04+00:00",
        "source": "dunkest_lineups_browser_availability",
        "dunkest_turn": 1,
        "rows": 1,
        "rows_observed_at_utc": 1,
    }
    availability_file.with_name(availability_file.name + ".meta.json").write_text(
        json.dumps(availability_meta), encoding="utf-8"
    )
    models = {
        "ridge": object(),
        "rf": object(),
        "_feature_cols": ["pdk_mean_5", "rest_days"],
        "_training_target": "target_pdk_official",
        "_training_target_source": "official_dunkest_pdk",
        "_training_rows": 1800,
        "_training_rows_before_target_filter": 2200,
        "_official_labels_available_before_filter": 1800,
        "_training_date_min_utc": "2025-10-01T00:00:00+00:00",
        "_training_date_max_utc": "2026-04-12T00:00:00+00:00",
        "_training_minute_labels_dataset": str(minute_label_cache),
        "_training_minute_labels_matched_rows": 1700,
        "_weights": {"ridge": 0.75, "rf": 0.25},
        "_projection_weights": {"minutes": 0.6, "ensemble": 0.4, "prior": 0.0},
        "_calibration_samples": 120,
        "_interval_diagnostics": [
            {"dimension": "history_games", "cohort": "0-4", "n": 40}
        ],
        "_interval_diagnostic_scope": "cross-fitted cohort diagnostic",
    }

    run_metadata = {
        "official_pdk_overlay_source": str(official_overlay),
        "official_pdk_overlay_label_rows": 41,
        "credit_proxy_reference_rows": 42,
        "credit_proxy_reference_source": "prior_season_game_logs_official_pdk_mean_with_proxy_fallback",
        "plusvalenza_reference_incomplete_seasons": ["16", "22", "25"],
    }
    output = save_run_artifacts(
        settings, pd.DataFrame(), [], models, run_metadata=run_metadata
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["run_metadata"] == run_metadata
    assert manifest["configuration"]["random_state"] == 19
    assert manifest["random_seed"] == 19
    assert len(manifest["config_sha256"]) == 64
    assert manifest["source_fingerprint"]["python_files"] > 0
    assert len(manifest["source_fingerprint"]["sha256"]) == 64
    assert manifest["optimizer_parameters"]["budget"] == settings.budget
    assert manifest["dataset_identifier"] == hashlib.sha256(
        json.dumps(manifest["inputs"], sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    if manifest["git_hash"] is None:
        assert manifest["git_hash_unavailable_reason"]
    assert manifest["configuration"]["rolling_windows"] == [3, 7]
    assert manifest["model_details"]["effective_models"] == ["rf", "ridge"]
    assert manifest["model_details"]["feature_columns"] == ["pdk_mean_5", "rest_days"]
    assert manifest["model_details"]["training_target"] == "target_pdk_official"
    assert manifest["model_details"]["training_target_source"] == "official_dunkest_pdk"
    assert manifest["model_details"]["training_rows"] == 1800
    assert manifest["model_details"]["training_rows_before_target_filter"] == 2200
    assert manifest["model_details"]["official_labels_available_before_filter"] == 1800
    assert manifest["model_details"]["training_date_min_utc"] == "2025-10-01T00:00:00+00:00"
    assert manifest["model_details"]["training_date_max_utc"] == "2026-04-12T00:00:00+00:00"
    assert manifest["model_details"]["training_minute_labels_dataset"] == str(minute_label_cache)
    assert manifest["model_details"]["training_minute_labels_matched_rows"] == 1700
    assert manifest["model_details"]["model_weights"] == {"ridge": 0.75, "rf": 0.25}
    assert manifest["model_details"]["calibration_samples"] == 120
    assert manifest["model_details"]["interval_diagnostics"] == [
        {"dimension": "history_games", "cohort": "0-4", "n": 40}
    ]
    assert manifest["model_details"]["interval_diagnostic_scope"] == (
        "cross-fitted cohort diagnostic"
    )
    assert manifest["runtime"]["packages"]["pandas"]

    input_hashes = {entry["path"]: entry["sha256"] for entry in manifest["inputs"]}
    player_input = next(
        entry for entry in manifest["inputs"]
        if entry["path"] == f"processed/player_game_logs_{settings.season}.parquet"
    )
    assert player_input["cache_metadata"]["source"] == "test"
    assert player_input["cache_metadata"]["fetched_at"] == "2026-10-01T12:00:00+00:00"
    assert input_hashes["processed/player_game_logs_2026-27.parquet"] == hashlib.sha256(
        b"captured-input"
    ).hexdigest()
    assert input_hashes[
        "processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
    ] == hashlib.sha256(b"minute-label-training-input").hexdigest()
    assert input_hashes[
        f"processed/player_game_logs_{settings.season}_official_pdk_overlay_v4.parquet"
    ] == hashlib.sha256(b"official-pdk-inference-input").hexdigest()
    assert input_hashes["processed/plusvalenza_history_multiseason_26_pre_gw1_5y_nba_v4.parquet"] == hashlib.sha256(
        b"plusvalenza-anchor-input"
    ).hexdigest()
    assert input_hashes["processed/plusvalenza_history_nba_25_through_gw91_v4.parquet"] == hashlib.sha256(
        b"plusvalenza-season-input"
    ).hexdigest()
    assert input_hashes["rookie_official_pdk.csv"] == hashlib.sha256(
        b"player_key,draft_year\nplayer-one,2025\n"
    ).hexdigest()
    assert input_hashes["current_lineups_market.csv"] == hashlib.sha256(
        b"player_name,cr\nPlayer One,8.0\n"
    ).hexdigest()
    snapshot_entries = {
        entry["path"]: entry for entry in manifest["pre_match_snapshot"]["files"]
    }
    meta_name = "current_lineups_market.csv.meta.json"
    assert meta_name in snapshot_entries
    archived_meta = output / "pre_match_snapshot" / meta_name
    assert json.loads(archived_meta.read_text(encoding="utf-8"))["fetched_at"] == (
        "2026-10-12T20:47:03+00:00"
    )
    assert snapshot_entries[meta_name]["sha256"] == hashlib.sha256(
        archived_meta.read_bytes()
    ).hexdigest()
    availability_meta_name = "lineups_availability.csv.meta.json"
    assert availability_meta_name in snapshot_entries
    archived_availability_meta = output / "pre_match_snapshot" / availability_meta_name
    assert json.loads(archived_availability_meta.read_text(encoding="utf-8"))["source"] == (
        "dunkest_lineups_browser_availability"
    )
    assert snapshot_entries[availability_meta_name]["sha256"] == hashlib.sha256(
        archived_availability_meta.read_bytes()
    ).hexdigest()


def test_season_opener_manifest_keeps_training_provenance(tmp_path):
    settings = Settings(data_dir=str(tmp_path), target_gameweek=1)
    models = {
        "ridge": object(),
        "rf": object(),
        "_feature_cols": ["pdk_mean_5", "rest_days"],
        "_training_target": "target_pdk_official",
        "_training_target_source": "official_dunkest_pdk",
        "_training_rows": 18141,
        "_training_rows_before_target_filter": 24100,
        "_official_labels_available_before_filter": 24052,
        "_training_date_min_utc": "2025-10-01T00:00:00+00:00",
        "_training_date_max_utc": "2026-04-12T00:00:00+00:00",
        "_training_minute_labels_dataset": "processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet",
        "_training_minute_labels_matched_rows": 17000,
        "_weights": {"ridge": 0.6, "rf": 0.4},
        "_projection_weights": {"minutes": 0.5, "ensemble": 0.4, "prior": 0.1},
        "_calibration_samples": 300,
        "_interval_diagnostics": [],
        "_interval_diagnostic_scope": "cross-fitted diagnostic",
    }
    artifact_models = _model_artifact_metadata(models)
    output = save_run_artifacts(settings, pd.DataFrame(), [], artifact_models)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    details = manifest["model_details"]

    assert details["effective_models"] == ["rf", "ridge"]
    assert details["training_target"] == "target_pdk_official"
    assert details["training_target_source"] == "official_dunkest_pdk"
    assert details["training_rows"] == 18141
    assert details["training_rows_before_target_filter"] == 24100
    assert details["official_labels_available_before_filter"] == 24052
    assert details["training_minute_labels_dataset"] == "processed/dunkest_nba_player_games_enriched_2018-25_v1.parquet"
    assert details["training_minute_labels_matched_rows"] == 17000
    assert details["feature_columns"] == ["pdk_mean_5", "rest_days"]
    assert details["model_weights"] == {"ridge": 0.6, "rf": 0.4}
    assert details["projection_weights"] == {"minutes": 0.5, "ensemble": 0.4, "prior": 0.1}
    assert details["calibration_samples"] == 300


def test_post_match_snapshot_archives_hashes_and_evaluation_provenance(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season="2026-27", season_id="26")
    player_results = pd.DataFrame([{
        "player_name": "Player One", "nba_game_id": "game-1", "actual_pdk": 12.5,
    }])
    coach_results = pd.DataFrame([{
        "coach": "Coach One", "nba_game_id": "game-1", "actual_coach_pdk": 18.0,
    }])

    archive = save_post_match_snapshot(
        settings,
        1,
        player_results,
        coach_results,
        source="official player results + verified coach scoring formula",
        metadata={
            "run_id": "run-1",
            "source_files": {"players": "official_results.parquet"},
            "coverage_audit": {"player": 1.0, "coach": 1.0},
        },
    )

    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["run_id"] == "run-1"
    assert manifest["source_fingerprint"]["python_files"] > 0
    assert len(manifest["source_fingerprint"]["sha256"]) == 64
    assert manifest["source_files"]["players"] == "official_results.parquet"
    assert manifest["coverage_audit"] == {"player": 1.0, "coach": 1.0}
    assert manifest["sha256"]["player_results.parquet"] == hashlib.sha256(
        (archive / "player_results.parquet").read_bytes()
    ).hexdigest()
    assert manifest["sha256"]["coach_results.parquet"] == hashlib.sha256(
        (archive / "coach_results.parquet").read_bytes()
    ).hexdigest()
    registry = json.loads(
        (archive.parent / "registry" / f"{archive.name}.json").read_text(encoding="utf-8")
    )
    assert registry["manifest_sha256"] == hashlib.sha256(
        (archive / "manifest.json").read_bytes()
    ).hexdigest()
    pd.testing.assert_frame_equal(
        pd.read_parquet(archive / "player_results.parquet"), player_results
    )


def test_post_match_snapshot_rejects_reserved_metadata_before_creating_archive(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    with pytest.raises(ValueError, match="cannot override reserved fields"):
        save_post_match_snapshot(
            settings,
            1,
            pd.DataFrame(),
            pd.DataFrame(),
            source="official results",
            metadata={"sha256": {"fake": "hash"}},
        )
    assert not (tmp_path / "archive").exists()


def test_post_match_snapshot_registry_failure_removes_new_unregistered_archive(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    original_open = Path.open

    def fail_registry_creation(path, mode="r", *args, **kwargs):
        if path.parent.name == "registry" and mode == "x":
            raise OSError("simulated registry write failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_registry_creation)
    with pytest.raises(OSError, match="simulated registry write failure"):
        save_post_match_snapshot(
            settings,
            1,
            pd.DataFrame([{"player_name": "P", "actual_pdk": 1.0}]),
            pd.DataFrame([{"coach": "C", "actual_coach_pdk": 1.0}]),
            source="official results",
        )

    gw_root = tmp_path / "archive" / "26" / "gw1"
    assert list(gw_root.glob("post_match_*")) == []
    assert list((gw_root / "registry").glob("*.json")) == []


def test_pre_match_archive_is_immutable_and_rejects_realized_targets(tmp_path):
    from dunkest.report.artifacts import save_pre_match_snapshot

    settings = Settings(data_dir=str(tmp_path), season_id="26")
    path = save_pre_match_snapshot(
        settings,
        2,
        {
            "player_market.parquet": pd.DataFrame({
                "player_name": ["Player One"], "cr": [8.5], "team_code": ["BOS"]
            }),
            "injuries.parquet": pd.DataFrame({
                "player_name": ["Player Two"], "status": ["OUT"]
            }),
        },
        source="unit_test",
    )
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["season_id"] == "26"
    assert manifest["dunkest_gameweek"] == 2
    assert manifest["source"] == "unit_test"
    assert manifest["source_fingerprint"]["python_files"] > 0
    assert len(manifest["source_fingerprint"]["sha256"]) == 64
    assert set(manifest["sha256"]) == {"player_market.parquet", "injuries.parquet"}
    assert all(len(value) == 64 for value in manifest["sha256"].values())

    with pytest.raises(ValueError, match="Outcome-bearing column"):
        save_pre_match_snapshot(
            settings, 2,
            {"player_market.parquet": pd.DataFrame({"player_name": ["Player One"], "actual_pdk": [19.0]})},
            source="unit_test",
        )


def test_pre_match_archive_loader_requires_hashes_and_capture_before_tipoff(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    lock = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2)
    market = pd.DataFrame({
        "player_name": [f"Player {i}" for i in range(250)],
        "team_code": ["BOS"] * 250,
        "role": ["G"] * 250,
        "cr": [6.0] * 250,
        "gameweek": [1] * 250,
        "lineup_group": ["G"] * 250,
        "status": ["AVAILABLE"] * 250,
    })
    mapping = pd.DataFrame({
        "nba_game_id": ["0022600001"],
        "game_datetime_utc": [lock],
        "dunkest_gameweek": [1],
        "dunkest_turn": [1],
        "mapping_verified": [True],
        "fantasy_eligible": [True],
        "home_team": ["BOS"], "away_team": ["NYK"],
    })
    archive = save_pre_match_snapshot(
        settings, 1, {
            "player_market.parquet": market,
            "fixture_mapping.parquet": mapping,
            "injuries.parquet": pd.DataFrame({"player_name": ["Player 0"], "team": ["BOS"], "status": ["OUT"]}),
            "coach_market.parquet": pd.DataFrame({
                "coach": ["Coach BOS"], "team": ["BOS"], "coach_cr": [6.0],
                "opponent": ["NYK"], "nba_game_id": ["0022600001"],
            }),
        },
        source="unit_test",
    )
    loaded = load_pre_match_snapshot(settings, 1)
    assert loaded is not None
    assert loaded["path"] == archive
    assert len(loaded["tables"]["_normalized_player_market"]) == 250

    # Tampering with a single archived parquet invalidates the entire snapshot.
    with (archive / "player_market.parquet").open("ab") as stream:
        stream.write(b"tampered")
    assert load_pre_match_snapshot(settings, 1) is None


def test_pre_match_archive_failure_never_publishes_partial_directory(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26")

    def interrupt_write(self, path, *args, **kwargs):
        from pathlib import Path

        Path(path).write_bytes(b"partial parquet")
        raise KeyboardInterrupt("simulated interruption")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", interrupt_write)
    with pytest.raises(KeyboardInterrupt, match="simulated interruption"):
        save_pre_match_snapshot(
            settings,
            1,
            {"player_market.parquet": pd.DataFrame({"player_name": ["Player One"]})},
            source="unit_test",
        )

    archive_root = tmp_path / "archive" / "26" / "gw1"
    assert list(archive_root.glob("pre_match_*")) == []
    assert list(archive_root.glob(".*.tmp-*")) == []


def test_post_match_archive_failure_never_publishes_partial_directory(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    original = pd.DataFrame.to_parquet
    writes = 0

    def interrupt_second_write(self, path, *args, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 2:
            from pathlib import Path

            Path(path).write_bytes(b"partial parquet")
            raise OSError("simulated disk interruption")
        return original(self, path, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", interrupt_second_write)
    with pytest.raises(OSError, match="simulated disk interruption"):
        save_post_match_snapshot(
            settings,
            1,
            pd.DataFrame({"actual_pdk": [12.5]}),
            pd.DataFrame({"actual_coach_pdk": [7.0]}),
            source="unit_test",
        )

    archive_root = tmp_path / "archive" / "26" / "gw1"
    assert list(archive_root.glob("post_match_*")) == []
    assert list(archive_root.glob(".*.tmp-*")) == []
