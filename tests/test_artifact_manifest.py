import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.pipeline.season_opener import _model_artifact_metadata
from dunkest.report.artifacts import (
    _gameweek_fixture_snapshot,
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
    assert manifest["player_forecast_snapshot"]["certification"]["pre_lock_eligible"] is False
    assert manifest["player_forecast_snapshot"]["certification"][
        "candidate_stable_identity_verified"
    ] is False
    assert manifest["player_forecast_snapshot"]["prediction_cutoff_utc"] is None
    assert manifest["player_forecast_snapshot"]["cutoff_status"] == "uncertified"
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


def test_run_manifest_archives_cutoff_evidence_but_does_not_certify_without_candidates(tmp_path):
    settings = Settings(data_dir=str(tmp_path), target_gameweek=1)
    evidence = {
        "status": "certified",
        "cutoff_kind": "official_rule_derived",
        "cutoff_utc": "2030-10-20T16:59:00+00:00",
        "evidence_sha256": "a" * 64,
        "acquired_at_utc": {
            "config": "2030-10-19T10:00:00+00:00",
            "matchday": "2030-10-19T10:00:01+00:00",
        },
        "evidence_payloads": {"config": {"data": {}}, "matchday": {"data": {}}},
    }
    predictions = pd.DataFrame()
    predictions.attrs.update({
        "forecast_timestamp_utc": "2030-10-20T16:00:00+00:00",
        "dunkest_lock_utc": evidence["cutoff_utc"],
        "dunkest_lock_source": "official_rule_derived:first_match_start_minus_1_minute",
        "dunkest_lock_source_sha256": evidence["evidence_sha256"],
        "dunkest_lock_verified": True,
        "dunkest_cutoff_evidence": evidence,
    })

    output = save_run_artifacts(settings, predictions, [])
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    descriptor = manifest["player_forecast_snapshot"]
    evidence_path = output / descriptor["cutoff_evidence_path"]

    assert evidence_path.is_file()
    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == descriptor["cutoff_evidence_file_sha256"]
    assert descriptor["cutoff_status"] == "certified"
    assert descriptor["certification_status"] == "uncertified"
    assert descriptor["certification"]["pre_lock_eligible"] is False


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


def _prospective_snapshot_inputs():
    player = {
        "player_name": "Player One", "dunkest_player_id": "dk-101", "team": "BOS",
        "role": "G", "opponent": "NYK", "nba_game_id": "game-1", "dunkest_turn": 1,
        "fixture_verified": True, "game_datetime_utc": "2030-10-20T17:00:00Z",
        "availability_observed_at_utc": "2030-10-20T10:00:00Z",
        "expected_min": 28.0, "expected_min_model_shadow": 26.0,
        "pdk_rate_for_projection": 0.6, "p_play": 0.9,
        "ensemble_pdk": 17.0, "prior_pdk": 16.0, "implied_min": 30.0,
        "has_history": True, "n_games": 30.0,
        "historical_rf_pdk": 15.0, "historical_rf_blend_weight": 0.1,
        "component_minutes_pdk": 16.8, "component_ensemble_pdk": 15.87,
        "component_prior_pdk": 14.93,
        "projection_weight_minutes": 0.5, "projection_weight_ensemble": 0.4,
        "projection_weight_prior": 0.1,
        "expected_pdk_conditional": 16.0, "expected_pdk": 14.4,
    }
    coach_rows = pd.DataFrame([
        {"coach": "Coach BOS", "team": "BOS", "nba_game_id": "game-1",
         "dunkest_turn": 1, "coach_cr": 8.0, "expected_coach_pdk": 12.5,
         "p10_coach_pdk": 4.0, "p90_coach_pdk": 20.0},
        {"coach": "Coach NYK", "team": "NYK", "nba_game_id": "game-1",
         "dunkest_turn": 1, "coach_cr": 7.5, "expected_coach_pdk": 10.0,
         "p10_coach_pdk": 2.0, "p90_coach_pdk": 18.0},
    ])
    predictions = pd.DataFrame([{
        "player_name": "Player One", "team": "BOS", "role": "G", "cr": 8.0,
        "expected_pdk": 14.4,
    }])
    predictions.attrs.update({
        "candidate_forecasts": pd.DataFrame([player]),
        "runtime_feature_snapshot": pd.DataFrame([{
            "PLAYER_NAME": "Player One", "pdk_mean_5": 15.0,
            "hgb_input__min_mean_5": 28.0,
        }]),
        "minutes_shadow_feature_columns": ["min_mean_5"],
        "forecast_timestamp_utc": "2030-10-20T10:01:00Z",
    })
    return predictions, coach_rows


def test_versioned_player_shadow_and_complete_coach_snapshots(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="30", target_gameweek=2)
    processed = settings.data_path / "processed"
    processed.mkdir(parents=True)
    pd.DataFrame([{
        "player_name": f"Player {i}", "cr": 5.0, "team_code": "BOS", "position": "G"
    } for i in range(400)]).to_parquet(
        processed / "dunkest_players_30_gw2.parquet", index=False
    )
    legacy_dir = tmp_path / "predictions" / "legacy-run"
    legacy_dir.mkdir(parents=True)
    legacy_manifest = legacy_dir / "manifest.json"
    legacy_manifest.write_text('{"run_id":"legacy-run"}\n', encoding="utf-8")
    original_legacy_bytes = legacy_manifest.read_bytes()
    predictions, coaches = _prospective_snapshot_inputs()

    output = save_run_artifacts(
        settings, predictions, [], coach_forecasts=coaches
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    player_desc = manifest["player_forecast_snapshot"]
    runtime_desc = manifest["runtime_feature_snapshot"]
    shadow_desc = manifest["shadow_forecast_snapshot"]
    coach_desc = manifest["coach_forecast_snapshot"]

    assert manifest["schema_version"] == 2
    assert player_desc["schema_version"] == 1
    assert runtime_desc["schema_version"] == 1
    assert shadow_desc["schema_version"] == 1
    assert coach_desc["schema_version"] == 1
    assert manifest["archive_status"] == "complete"
    market_descriptor = manifest["required_pre_match_inputs"]["dunkest_market_snapshot"]
    assert market_descriptor["status"] == "present"
    copied_market = output / "pre_match_snapshot" / market_descriptor["path"]
    assert hashlib.sha256(copied_market.read_bytes()).hexdigest() == market_descriptor["sha256"]
    assert manifest["prospective_evaluation_status"] == "awaiting_reconciled_outcomes"

    player_path = output / player_desc["path"]
    shadow_path = output / shadow_desc["path"]
    coach_path = output / coach_desc["path"]
    player_snapshot = pd.read_parquet(player_path)
    shadow_snapshot = pd.read_parquet(shadow_path)
    coach_snapshot = pd.read_parquet(coach_path)
    for descriptor, path in ((player_desc, player_path), (runtime_desc, output / runtime_desc["path"]),
                             (shadow_desc, shadow_path), (coach_desc, coach_path)):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == descriptor["sha256"]
    assert player_snapshot["forecast_record_id"].is_unique
    assert coach_snapshot["forecast_record_id"].is_unique
    assert player_snapshot.loc[0, "forecast_schema_version"] == 1
    assert player_snapshot.loc[0, "expected_min"] == pytest.approx(28.0)
    assert player_snapshot.loc[0, "expected_min_model_shadow"] == pytest.approx(26.0)
    assert player_snapshot.loc[0, "projection_weight_minutes"] == pytest.approx(0.5)
    assert pd.Timestamp(player_snapshot.loc[0, "forecast_timestamp_utc"]) == pd.Timestamp("2030-10-20T10:01:00Z")
    assert pd.Timestamp(coach_snapshot.loc[0, "forecast_timestamp_utc"]) == pd.Timestamp("2030-10-20T10:01:00Z")
    assert len(coach_snapshot) == 2
    assert shadow_snapshot.loc[0, "expected_min_model_shadow"] == pytest.approx(26.0)
    assert shadow_desc["optimizer_input"] is False
    assert "expected_min_model_shadow" not in pd.read_parquet(output / "predictions.parquet").columns
    assert legacy_manifest.read_bytes() == original_legacy_bytes


def test_missing_dunkest_market_is_recorded_and_marks_run_incomplete(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="30", target_gameweek=2)
    predictions, coaches = _prospective_snapshot_inputs()

    output = save_run_artifacts(settings, predictions, [], coach_forecasts=coaches)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    market = manifest["required_pre_match_inputs"]["dunkest_market_snapshot"]
    assert market == {
        "status": "missing",
        "path": "dunkest_players_30_gw2.parquet",
        "sha256": None,
        "source": None,
        "reason": "required pre-lock Dunkest market snapshot was absent at archive time",
    }
    assert manifest["snapshot_set_complete"] is False
    assert manifest["archive_status"] == "incomplete"
    assert not (output / "pre_match_snapshot" / "dunkest_players_30_gw2.parquet").exists()


def test_gameweek_mapping_snapshot_is_a_verified_source_slice(tmp_path):
    source = tmp_path / "season_mapping.parquet"
    captured = pd.Timestamp("2026-10-20T10:00:00Z")
    rows = []
    for gameweek, game_id in ((2, "g2"), (3, "g3")):
        rows.append({
            "season_id": "26", "nba_season": "2026-27", "nba_game_id": game_id,
            "dunkest_match_id": f"dk-{gameweek}",
            "game_datetime_utc": captured + pd.Timedelta(days=2),
            "game_date_local": "2026-10-22", "home_team": "BOS", "away_team": "NYK",
            "home_team_eligible": True, "away_team_eligible": False,
            "dunkest_gameweek": gameweek, "dunkest_turn": 1,
            "fantasy_eligible": True, "mapping_verified": True,
            "eligibility_reason": "verified", "source": "lineups",
            "source_url_or_endpoint": "https://example.invalid/fixture",
            "source_retrieved_at_utc": captured, "mapping_version": "lineups_browser_season_multigw_v1",
            "raw_payload_sha256": ("a" if gameweek == 2 else "b") * 64,
        })
    pd.DataFrame(rows).to_parquet(source, index=False)

    snapshot = _gameweek_fixture_snapshot(
        source, season_id="26", gameweek=2,
        forecast_timestamp=pd.Timestamp("2026-10-20T11:00:00Z"),
    )

    assert snapshot["season_id"].astype(str).tolist() == ["26"]
    assert snapshot["dunkest_gameweek"].astype(int).tolist() == [2]
    assert snapshot["nba_game_id"].tolist() == ["g2"]
    assert snapshot.loc[0, "mapping_version"] == "lineups_browser_season_multigw_v1"


def test_run_writer_uses_archive_gameweek_mapping_name_without_copying_season_map(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26", target_gameweek=2)
    processed = settings.data_path / "processed"
    processed.mkdir(parents=True)
    source = processed / "dunkest_fixture_mapping_26_lineups_browser_season_multigw_v1.parquet"
    pd.DataFrame([{
        "season_id": "26", "nba_season": "2026-27", "nba_game_id": "g2",
        "dunkest_match_id": "dk-2", "game_datetime_utc": "2030-10-22T10:00:00Z",
        "game_date_local": "2030-10-22", "home_team": "BOS", "away_team": "NYK",
        "home_team_eligible": True, "away_team_eligible": False,
        "dunkest_gameweek": 2, "dunkest_turn": 1, "fantasy_eligible": True,
        "mapping_verified": True, "eligibility_reason": "verified", "source": "lineups",
        "source_url_or_endpoint": "https://example.invalid/fixture",
        "source_retrieved_at_utc": "2030-10-20T09:00:00Z",
        "mapping_version": "lineups_browser_season_multigw_v1", "raw_payload_sha256": "a" * 64,
    }]).to_parquet(source, index=False)
    predictions, coaches = _prospective_snapshot_inputs()

    output = save_run_artifacts(settings, predictions, [], coach_forecasts=coaches)

    snapshot_dir = output / "pre_match_snapshot"
    expected = snapshot_dir / "dunkest_fixture_mapping_26_lineups_browser_gw2_team_status_v2.parquet"
    assert expected.is_file()
    assert not (snapshot_dir / source.name).exists()
    stored = pd.read_parquet(expected)
    source_frame = pd.read_parquet(source)
    from dunkest.data.dunkest.fixtures import validate_fixture_mapping
    pd.testing.assert_frame_equal(
        stored, validate_fixture_mapping(source_frame).reset_index(drop=True)
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    mapping_entries = [
        item for item in manifest["pre_match_snapshot"]["files"]
        if item["path"].startswith("dunkest_fixture_mapping_")
    ]
    assert [item["path"] for item in mapping_entries] == [expected.name]


@pytest.mark.parametrize(
    ("season_id", "gameweek", "forecast_timestamp", "message"),
    [
        ("27", 2, "2026-10-20T11:00:00Z", "no rows"),
        ("26", 4, "2026-10-20T11:00:00Z", "no rows"),
        ("26", 2, "2026-10-20T09:00:00Z", "post-forecast"),
    ],
)
def test_gameweek_mapping_snapshot_rejects_missing_or_incoherent_source(
    tmp_path, season_id, gameweek, forecast_timestamp, message,
):
    source = tmp_path / "season_mapping.parquet"
    pd.DataFrame([{
        "season_id": "26", "nba_season": "2026-27", "nba_game_id": "g2",
        "dunkest_match_id": "dk-2", "game_datetime_utc": "2026-10-22T10:00:00Z",
        "game_date_local": "2026-10-22", "home_team": "BOS", "away_team": "NYK",
        "home_team_eligible": True, "away_team_eligible": False,
        "dunkest_gameweek": 2, "dunkest_turn": 1, "fantasy_eligible": True,
        "mapping_verified": True, "eligibility_reason": "verified", "source": "lineups",
        "source_url_or_endpoint": "https://example.invalid/fixture",
        "source_retrieved_at_utc": "2026-10-20T10:00:00Z",
        "mapping_version": "lineups_browser_season_multigw_v1", "raw_payload_sha256": "a" * 64,
    }]).to_parquet(source, index=False)

    with pytest.raises(ValueError, match=message):
        _gameweek_fixture_snapshot(
            source, season_id=season_id, gameweek=gameweek,
            forecast_timestamp=pd.Timestamp(forecast_timestamp),
        )


def test_snapshot_persistence_failure_is_logged_and_marks_archive_incomplete(tmp_path, monkeypatch, caplog):
    settings = Settings(data_dir=str(tmp_path), season_id="30", target_gameweek=2)
    predictions, coaches = _prospective_snapshot_inputs()
    original_to_parquet = pd.DataFrame.to_parquet

    def fail_coach_snapshot(self, path, *args, **kwargs):
        if str(path).endswith("coach_forecast_snapshot.parquet"):
            raise OSError("simulated coach snapshot disk failure")
        return original_to_parquet(self, path, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_coach_snapshot)
    output = save_run_artifacts(settings, predictions, [], coach_forecasts=coaches)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["archive_status"] == "incomplete"
    assert manifest["snapshot_set_complete"] is False
    assert manifest["coach_forecast_snapshot"]["status"] == "incomplete"
    assert manifest["coach_forecast_snapshot"]["sha256"] is None
    assert manifest["persistence_errors"] == [{
        "artifact": "coach_forecast", "error_type": "OSError",
        "message": "simulated coach snapshot disk failure",
    }]
    assert "Could not persist coach_forecast snapshot" in caplog.text
    assert not (output / "coach_forecast_snapshot.parquet").exists()


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
