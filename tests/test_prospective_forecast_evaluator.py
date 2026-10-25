import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "evaluate_prospective_forecasts_v1",
    ROOT / "scripts" / "evaluate_prospective_forecasts_v1.py",
)
evaluator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evaluator)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_archives(tmp_path, outcome_rows=None):
    archive = tmp_path / "prelock" / "season_id=26" / "gw=1" / "run-1"
    snapshot = archive / "pre_match_snapshot"
    snapshot.mkdir(parents=True)
    forecasts = pd.DataFrame([
        {
            "forecast_run_id": "run-1", "forecast_record_id": f"forecast-{i}",
            "dunkest_player_id": f"dk-{i}", "nba_game_id": "game-1",
            "expected_pdk": float(i * 10), "forecast_timestamp_utc": "2026-10-01T09:00:00Z",
            "prediction_cutoff_utc": "2026-10-01T11:00:00Z", "role": "G" if i == 1 else "F",
        }
        for i in (1, 2, 3)
    ])
    forecast_path = archive / "player_forecast_snapshot.parquet"
    forecasts.to_parquet(forecast_path, index=False)
    mapping_path = snapshot / "dunkest_fixture_mapping_26_gw1.parquet"
    pd.DataFrame([{
        "dunkest_gameweek": 1, "nba_game_id": "game-1",
        "mapping_verified": True, "game_datetime_utc": "2026-10-01T12:00:00Z",
    }]).to_parquet(mapping_path, index=False)
    run_manifest = {
        "schema_version": 2, "run_id": "run-1", "timestamp": "2026-10-01T09:05:00Z",
        "configuration": {"season_id": "26", "target_gameweek": 1},
        "inputs": [{"path": "input.parquet", "sha256": "a" * 64}],
        "player_forecast_snapshot": {
            "path": forecast_path.name, "sha256": _sha(forecast_path),
            "forecast_timestamp_utc": "2026-10-01T09:00:00Z",
            "prediction_cutoff_utc": "2026-10-01T11:00:00Z", "model_version": "model-v1",
        },
    }
    (archive / "manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")
    meta = {"schema_version": 2, "run_id": "run-1", "max_snapshot_age_hours": 36}
    (archive / "archive_manifest.json").write_text(json.dumps(meta), encoding="utf-8")
    prelock_registry = archive.parents[2] / "registry" / "run-1.json"
    prelock_registry.parent.mkdir(parents=True)
    prelock_registry.write_text(json.dumps({
        "run_id": "run-1", "archive_manifest_sha256": _sha(archive / "archive_manifest.json"),
    }), encoding="utf-8")

    results = tmp_path / "data" / "archive" / "26" / "gw1" / "post_match_result-1"
    results.mkdir(parents=True)
    if outcome_rows is None:
        outcome_rows = [
            {
                "forecast_run_id": "run-1", "forecast_record_id": f"forecast-{i}",
                "dunkest_player_id": f"dk-{i}", "nba_game_id": "game-1",
                "actual_pdk_official": float(i * 10 + 1), "actual_pdk_status": "official_verified",
                "actual_pdk_source": "official_dunkest", "outcome_status": "appeared",
            }
            for i in (1, 2, 3)
        ]
    outcome_path = results / "player_results.parquet"
    outcome_frame = pd.DataFrame(outcome_rows)
    if "fixture_verified" not in outcome_frame:
        outcome_frame["fixture_verified"] = True
    outcome_frame.to_parquet(outcome_path, index=False)
    coach_path = results / "coach_results.parquet"
    pd.DataFrame(columns=["coach", "nba_game_id", "actual_coach_pdk"]).to_parquet(coach_path, index=False)
    source = {"path": "/data/official_dunkest_player_games_2026-27.parquet", "sha256": "f" * 64}
    result_manifest = {
        "schema_version": 3, "season_id": "26", "dunkest_gameweek": 1,
        "run_id": "run-1", "retrieved_at_utc": "2026-10-01T17:00:00Z",
        "source_file_fingerprints": {"official_player_games": source},
        "sha256": {"player_results.parquet": _sha(outcome_path), "coach_results.parquet": _sha(coach_path)},
    }
    (results / "manifest.json").write_text(json.dumps(result_manifest), encoding="utf-8")
    registry_dir = results.parent / "registry"
    registry_dir.mkdir(parents=True)
    (registry_dir / f"{results.name}.json").write_text(json.dumps({
        "archive_id": results.name, "season_id": "26", "dunkest_gameweek": 1,
        "manifest_sha256": _sha(results / "manifest.json"),
        "sha256": result_manifest["sha256"],
    }), encoding="utf-8")
    return archive, results


def _eligible_review(*args, **kwargs):
    return {"status": "verified_pre_lock", "rechecked_pre_lock_eligible": True}


def test_reconciles_by_forecast_stable_player_and_game_ids(tmp_path, monkeypatch):
    archive, results = _fixture_archives(tmp_path)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)

    report, rows = evaluator.evaluate_archive(archive, results_dir=results)

    assert report["evaluation_status"] == "ready"
    assert report["official_oos_metrics"] is True
    assert rows["reconciliation_status"].tolist() == ["reconciled_official"] * 3
    assert set(rows["bundle_id"]) == {"run-1"}
    assert set(rows["nba_game_id"]) == {"game-1"}


def test_duplicate_outcome_and_identity_mismatch_are_not_auto_resolved(tmp_path, monkeypatch):
    archive, _ = _fixture_archives(tmp_path)
    outcomes = [
        {
            "forecast_run_id": "run-1", "forecast_record_id": "forecast-1",
            "dunkest_player_id": "dk-1", "nba_game_id": "game-1",
            "actual_pdk_official": 11.0, "actual_pdk_status": "official_verified",
            "actual_pdk_source": "official_dunkest", "outcome_status": "appeared",
        },
        {
            "forecast_run_id": "run-1", "forecast_record_id": "forecast-1",
            "dunkest_player_id": "dk-1", "nba_game_id": "game-1",
            "actual_pdk_official": 12.0, "actual_pdk_status": "official_verified",
            "actual_pdk_source": "official_dunkest", "outcome_status": "appeared",
        },
        {
            "forecast_run_id": "run-1", "forecast_record_id": "forecast-2",
            "dunkest_player_id": "wrong-player", "nba_game_id": "game-1",
            "actual_pdk_official": 21.0, "actual_pdk_status": "official_verified",
            "actual_pdk_source": "official_dunkest", "outcome_status": "appeared",
        },
    ]
    _, results = _fixture_archives(tmp_path / "other", outcomes)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)

    report, rows = evaluator.evaluate_archive(archive, results_dir=results)

    assert rows.set_index("forecast_record_id").loc["forecast-1", "reconciliation_status"] == "mapping_ambiguous"
    assert rows.set_index("forecast_record_id").loc["forecast-2", "reconciliation_status"] == "mapping_ambiguous"
    assert report["official_oos_metrics"] is False


def test_duplicate_outcome_player_game_pair_is_ambiguous_even_with_distinct_forecast_ids(tmp_path, monkeypatch):
    archive, _ = _fixture_archives(tmp_path)
    outcomes = [{
        "forecast_run_id": "run-1", "forecast_record_id": f"different-{suffix}",
        "dunkest_player_id": "dk-1", "nba_game_id": "game-1",
        "actual_pdk_official": float(10 + suffix), "actual_pdk_status": "official_verified",
        "actual_pdk_source": "official_dunkest", "outcome_status": "appeared",
    } for suffix in (1, 2)]
    _, results = _fixture_archives(tmp_path / "other", outcomes)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)

    _, rows = evaluator.evaluate_archive(archive, results_dir=results)

    row = rows.set_index("forecast_record_id").loc["forecast-1"]
    assert row["reconciliation_status"] == "mapping_ambiguous"
    assert row["exclusion_reason"] == "duplicate_outcome_player_game_identity"


def test_missing_null_and_unofficial_outcomes_are_excluded_explicitly(tmp_path, monkeypatch):
    archive, _ = _fixture_archives(tmp_path)
    outcomes = [{
        "forecast_run_id": "run-1", "forecast_record_id": "forecast-1",
        "dunkest_player_id": "dk-1", "nba_game_id": "game-1",
        "actual_pdk_official": None, "actual_pdk_status": "missing",
        "actual_pdk_source": None, "outcome_status": "outcome_missing",
    }, {
        "forecast_run_id": "run-1", "forecast_record_id": "forecast-2",
        "dunkest_player_id": "dk-2", "nba_game_id": "game-1",
        "actual_pdk_official": 99.0, "actual_pdk_status": "official_verified",
        "actual_pdk_source": "nba_boxscore_rule_proxy", "outcome_status": "appeared",
    }]
    _, results = _fixture_archives(tmp_path / "other", outcomes)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)

    report, rows = evaluator.evaluate_archive(archive, results_dir=results)

    assert rows["reconciliation_status"].tolist() == ["outcome_missing", "outcome_unverified", "outcome_missing"]
    assert report["counts"]["excluded"] == 3
    assert report["metrics"] is None


def test_ineligible_bundle_is_rejected_by_reviewer_gate(tmp_path, monkeypatch):
    archive, results = _fixture_archives(tmp_path)
    monkeypatch.setattr(evaluator, "review_prelock_archive", lambda *a, **k: {
        "status": "incomplete", "rechecked_pre_lock_eligible": False,
    })

    with pytest.raises(ValueError, match="did not certify"):
        evaluator.evaluate_archive(archive, results_dir=results)


def test_invalid_or_preforecast_outcome_timestamp_is_rejected(tmp_path, monkeypatch):
    archive, results = _fixture_archives(tmp_path)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)
    manifest_path = results / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["retrieved_at_utc"] = "not-a-time"
    manifest_path.write_text(json.dumps(manifest))
    registry_path = results.parent / "registry" / f"{results.name}.json"
    registry = json.loads(registry_path.read_text())
    registry["manifest_sha256"] = _sha(manifest_path)
    registry_path.write_text(json.dumps(registry))

    with pytest.raises(ValueError, match="timestamp is invalid or not after"):
        evaluator.evaluate_archive(archive, results_dir=results)


def test_outcome_before_safe_postgame_cutoff_is_rejected(tmp_path, monkeypatch):
    archive, results = _fixture_archives(tmp_path)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)
    manifest_path = results / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["retrieved_at_utc"] = "2026-10-01T15:59:00Z"
    manifest_path.write_text(json.dumps(manifest))
    registry_path = results.parent / "registry" / f"{results.name}.json"
    registry = json.loads(registry_path.read_text())
    registry["manifest_sha256"] = _sha(manifest_path)
    registry_path.write_text(json.dumps(registry))

    with pytest.raises(ValueError, match="predates the conservative post-game"):
        evaluator.evaluate_archive(archive, results_dir=results)


def test_no_evaluable_rows_is_not_a_valid_empty_metric_result(tmp_path, monkeypatch):
    archive, _ = _fixture_archives(tmp_path)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)

    report, rows = evaluator.evaluate_archive(archive)

    assert len(rows) == 3
    assert report["evaluation_status"] == "not_ready"
    assert report["official_oos_metrics"] is False
    assert report["metrics"] is None
    assert report["counts"]["forecasted"] == 3
    assert report["counts"]["excluded"] == 3


def test_known_mae_rmse_bias_and_role_cohorts(tmp_path, monkeypatch):
    archive, results = _fixture_archives(tmp_path)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)
    report, _ = evaluator.evaluate_archive(archive, results_dir=results)

    assert report["metrics"]["overall"] == {
        "n": 3, "mae": 1.0, "rmse": 1.0, "bias_predicted_minus_actual": -1.0,
    }
    assert report["metrics"]["by_role"]["G"]["n"] == 1
    assert report["metrics"]["by_observed_pdk_band"]["10-<20"]["n"] == 1


def test_partial_coverage_is_diagnostic_and_never_official_oos(tmp_path, monkeypatch):
    archive, _ = _fixture_archives(tmp_path)
    partial = [{
        "forecast_run_id": "run-1", "forecast_record_id": "forecast-1",
        "dunkest_player_id": "dk-1", "nba_game_id": "game-1",
        "actual_pdk_official": 11.0, "actual_pdk_status": "official_verified",
        "actual_pdk_source": "official_dunkest", "outcome_status": "appeared",
    }]
    _, results = _fixture_archives(tmp_path / "other", partial)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)

    report, _ = evaluator.evaluate_archive(archive, results_dir=results)

    assert report["evaluation_status"] == "partial"
    assert report["metric_scope"] == "verified_subset_diagnostic_only"
    assert report["official_oos_metrics"] is False
    assert report["metrics"]["overall"]["n"] == 1


def test_repeated_report_and_rows_are_reproducible(tmp_path, monkeypatch):
    archive, results = _fixture_archives(tmp_path)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)
    first_report, first_rows = evaluator.evaluate_archive(archive, results_dir=results)
    second_report, second_rows = evaluator.evaluate_archive(archive, results_dir=results)

    assert first_report == second_report
    pd.testing.assert_frame_equal(first_rows, second_rows)


def test_outcome_source_must_be_authenticated_and_postgame_complete(tmp_path, monkeypatch):
    archive, results = _fixture_archives(tmp_path)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)
    manifest_path = results / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source_file_fingerprints"].pop("official_player_games")
    manifest_path.write_text(json.dumps(manifest))
    registry_path = results.parent / "registry" / f"{results.name}.json"
    registry = json.loads(registry_path.read_text())
    registry["manifest_sha256"] = _sha(manifest_path)
    registry_path.write_text(json.dumps(registry))

    report, rows = evaluator.evaluate_archive(archive, results_dir=results)

    assert report["evaluation_status"] == "not_ready"
    assert report["official_oos_metrics"] is False
    assert set(rows["reconciliation_status"]) == {"outcome_unverified"}
    assert any("fingerprinted official" in item for item in report["limitations"])


def test_explicitly_postponed_game_is_not_scored_as_zero(tmp_path, monkeypatch):
    archive, _ = _fixture_archives(tmp_path)
    postponed = [{
        "forecast_run_id": "run-1", "forecast_record_id": "forecast-1",
        "dunkest_player_id": "dk-1", "nba_game_id": "game-1",
        "actual_pdk_official": None, "actual_pdk_status": "missing",
        "actual_pdk_source": None, "outcome_status": "postponed_verified",
    }]
    _, results = _fixture_archives(tmp_path / "other", postponed)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)

    _, rows = evaluator.evaluate_archive(archive, results_dir=results)

    result = rows.set_index("forecast_record_id").loc["forecast-1"]
    assert result["reconciliation_status"] == "game_postponed"
    assert pd.isna(result["actual_pdk"])


def test_outcome_with_unverified_fixture_mapping_is_excluded(tmp_path, monkeypatch):
    archive, _ = _fixture_archives(tmp_path)
    outcomes = [{
        "forecast_run_id": "run-1", "forecast_record_id": "forecast-1",
        "dunkest_player_id": "dk-1", "nba_game_id": "game-1", "fixture_verified": False,
        "actual_pdk_official": 11.0, "actual_pdk_status": "official_verified",
        "actual_pdk_source": "official_dunkest", "outcome_status": "appeared",
    }]
    _, results = _fixture_archives(tmp_path / "other", outcomes)
    monkeypatch.setattr(evaluator, "review_prelock_archive", _eligible_review)

    _, rows = evaluator.evaluate_archive(archive, results_dir=results)

    row = rows.set_index("forecast_record_id").loc["forecast-1"]
    assert row["reconciliation_status"] == "mapping_ambiguous"
    assert row["exclusion_reason"] == "outcome_fixture_mapping_not_verified"
