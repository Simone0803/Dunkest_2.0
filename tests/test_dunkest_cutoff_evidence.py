import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

from dunkest.data.dunkest import fixtures

ROOT = Path(__file__).resolve().parents[1]
_ARCHIVE_SPEC = importlib.util.spec_from_file_location(
    "cutoff_archive_validation", ROOT / "scripts/archive_dunkest_pre_lock_run_v1.py"
)
archive = importlib.util.module_from_spec(_ARCHIVE_SPEC)
assert _ARCHIVE_SPEC and _ARCHIVE_SPEC.loader
_ARCHIVE_SPEC.loader.exec_module(archive)


def _api_responses():
    config = {
        "data": {
            "current_schedule_id": 57,
            "current_matchday": {"id": 300, "number": 1},
        }
    }
    matchday = {
        "data": {
            "id": 300,
            "number": 1,
            "rounds": [{
                "id": 9001,
                "number": 1,
                "matches": [{
                    "id": 9901,
                    "started_at": "2030-10-20T19:00:00+02:00",
                    "home_team": {"abbreviation": "BOS", "is_valid": True},
                    "away_team": {"abbreviation": "NYK", "is_valid": True},
                }],
            }, {
                "id": 9002,
                "number": 2,
                "matches": [{
                    "id": 9902,
                    "started_at": "2030-10-21T20:30:00+02:00",
                    "home_team": {"abbreviation": "ATL", "is_valid": True},
                    "away_team": {"abbreviation": "MIA", "is_valid": True},
                }],
            }],
        }
    }
    return config, matchday


def _fixture_mapping(*, wrong_turn=False):
    return pd.DataFrame([
        {
            "nba_game_id": "nba-1", "dunkest_match_id": "9901",
            "game_datetime_utc": "2030-10-20T17:00:00Z",
            "home_team": "BOS", "away_team": "NYK",
            "dunkest_gameweek": 1, "dunkest_turn": 2 if wrong_turn else 1,
            "mapping_verified": True, "fantasy_eligible": True,
        },
        {
            "nba_game_id": "nba-2", "dunkest_match_id": "9902",
            "game_datetime_utc": "2030-10-21T18:30:00Z",
            "home_team": "ATL", "away_team": "MIA",
            "dunkest_gameweek": 1, "dunkest_turn": 2,
            "mapping_verified": True, "fantasy_eligible": True,
        },
    ])


def _capture(monkeypatch):
    config, matchday = _api_responses()
    urls = []

    def fake_get_json(url, *, timeout):
        urls.append(url)
        return config if url.endswith("/leagues/1/config") else matchday

    monkeypatch.setattr(fixtures, "get_json", fake_get_json)
    calendar, metadata = fixtures.fetch_official_dunkest_gameweek_calendar(1)
    assert len(urls) == 2
    return calendar, metadata


def test_official_rule_cutoff_converts_source_timezone_and_links_turns(monkeypatch):
    calendar, metadata = _capture(monkeypatch)

    assert calendar.loc[calendar["dunkest_turn"].eq(1), "game_datetime_utc"].iloc[0] == pd.Timestamp("2030-10-20T17:00:00Z")
    assert calendar.loc[calendar["dunkest_turn"].eq(1), "dunkest_turn_cutoff_utc"].iloc[0] == pd.Timestamp("2030-10-20T16:59:00Z")
    evidence = fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(), calendar, metadata, gameweek=1
    )

    assert evidence["status"] == "certified"
    assert evidence["cutoff_kind"] == "official_rule_derived"
    assert evidence["cutoff_utc"] == "2030-10-20T16:59:00+00:00"
    assert evidence["turn_cutoffs_utc"]["2"] == "2030-10-21T18:29:00+00:00"
    assert evidence["timezone"].startswith("UTC")
    assert len(evidence["evidence_sha256"]) == 64


def test_official_calendar_acquisition_is_idempotent_for_same_payload(monkeypatch):
    first_calendar, first = _capture(monkeypatch)
    second_calendar, second = _capture(monkeypatch)
    first_result = fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(), first_calendar, first, gameweek=1
    )
    second_result = fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(), second_calendar, second, gameweek=1
    )

    assert first["matchday_payload_sha256"] == second["matchday_payload_sha256"]
    assert first_result["turn_cutoffs_utc"] == second_result["turn_cutoffs_utc"]
    assert first_result["evidence_sha256"] == second_result["evidence_sha256"]


def test_cutoff_is_uncertified_when_official_source_or_cutoff_is_unknown(monkeypatch):
    calendar, metadata = _capture(monkeypatch)

    missing = fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(), calendar, {}, gameweek=1
    )
    assert missing["status"] == "uncertified"

    source_after_lock = dict(metadata)
    source_after_lock["config_retrieved_at_utc"] = "2030-10-20T17:00:00Z"
    source_after_lock["matchday_retrieved_at_utc"] = "2030-10-20T17:00:00Z"
    late = fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(), calendar, source_after_lock, gameweek=1
    )
    assert late["status"] == "uncertified"
    assert late["reason"] == "official_cutoff_evidence_acquired_after_gameweek_lock"


def test_cutoff_rejects_tampered_payload_wrong_gameweek_and_turn_mismatch(monkeypatch):
    calendar, metadata = _capture(monkeypatch)
    altered = dict(metadata)
    altered["evidence_payloads"] = {**metadata["evidence_payloads"], "matchday": {"data": {"id": -1}}}
    assert fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(), calendar, altered, gameweek=1
    )["reason"] == "official_matchday_payload_missing_or_hash_mismatch"

    assert fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(), calendar, metadata, gameweek=2
    )["status"] == "uncertified"
    assert fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(wrong_turn=True), calendar, metadata, gameweek=1
    )["reason"] == "fixture_to_official_turn_link_missing_or_ambiguous"


def test_naive_official_match_start_is_not_accepted_as_cutoff(monkeypatch):
    config, matchday = _api_responses()
    matchday["data"]["rounds"][0]["matches"][0]["started_at"] = "2030-10-20T19:00:00"
    payloads = iter((config, matchday))
    monkeypatch.setattr(fixtures, "get_json", lambda url, *, timeout: next(payloads))

    try:
        fixtures.fetch_official_dunkest_gameweek_calendar(1)
    except ValueError as exc:
        assert "Malformed official Dunkest match" in str(exc)
    else:
        raise AssertionError("timezone-naive official timestamps must not certify a cutoff")


def test_archive_certification_requires_untampered_official_cutoff_evidence(monkeypatch, tmp_path):
    calendar, metadata = _capture(monkeypatch)
    evidence = fixtures.certify_official_gameweek_cutoffs(
        _fixture_mapping(), calendar, metadata, gameweek=1
    )
    evidence.update({
        "cutoff_semantics": metadata["cutoff_semantics"],
        "source": metadata["source"],
        "evidence_payloads": metadata["evidence_payloads"],
    })
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    evidence_path = run_dir / "dunkest_cutoff_evidence.json"
    evidence_bytes = (json.dumps(evidence, sort_keys=True, indent=2) + "\n").encode()
    evidence_path.write_bytes(evidence_bytes)
    forecast_time = "2030-10-20T16:30:00Z"
    forecast_rows = []
    for player, team, opponent, turn, nba_game_id, dunkest_match_id in (
        ("Player One", "BOS", "NYK", 1, "nba-1", "9901"),
        ("Player Two", "ATL", "MIA", 2, "nba-2", "9902"),
    ):
        forecast_rows.append({
            "player_key": player.lower().replace(" ", "-"),
            "canonical_player_id": f"dk-{turn}",
            "canonical_player_id_source": "dunkest_player_id",
            "dunkest_player_id": f"dk-{turn}",
            "forecast_run_id": "run-1",
            "forecast_record_id": f"record-{turn}",
            "player_name": player, "team": team, "opponent": opponent,
            "dunkest_turn": turn, "nba_game_id": nba_game_id,
            "dunkest_match_id": dunkest_match_id, "fixture_verified": True,
            "role": "G", "lineup_group": "QUINTETTO", "status": "Available",
            "cr": 10.0, "expected_min": 24.0, "expected_pdk_conditional": 12.0,
            "expected_min_model_shadow": 23.0,
            "minutes_hybrid_status": "available", "minutes_shadow_status": "available",
            "expected_pdk": 12.0, "p_play": 1.0,
            "forecast_timestamp_utc": forecast_time,
            "prediction_cutoff_utc": evidence["cutoff_utc"],
            "dunkest_turn_cutoff_utc": evidence["turn_cutoffs_utc"][str(turn)],
            "lineups_availability_observed_at_utc": "2030-10-20T15:00:00Z",
            "injury_availability_observed_at_utc": "2030-10-20T15:00:00Z",
            "forecast_model_version": "test-model",
        })
    forecast_path = run_dir / "player_forecast_snapshot.parquet"
    pd.DataFrame(forecast_rows).to_parquet(forecast_path, index=False)
    feature_path = run_dir / "runtime_feature_snapshot.parquet"
    pd.DataFrame([{
        "forecast_record_id": row["forecast_record_id"],
        "dunkest_player_id": row["dunkest_player_id"],
        "canonical_player_id": row["canonical_player_id"],
        "nba_game_id": row["nba_game_id"],
        "player_key": row["player_key"],
        "feature_match_status": "matched",
        "candidate_key_count": 1,
        "source_feature_row_count": 1,
        "minutes_shadow_status": "available",
        "runtime_feature__hgb_input__lag1_nba_min": 22.0,
    } for row in forecast_rows]).to_parquet(feature_path, index=False)
    run_manifest = {
        "timestamp": forecast_time,
        "configuration": {"target_gameweek": 1},
        "player_forecast_snapshot": {
            "path": forecast_path.name,
            "sha256": hashlib.sha256(forecast_path.read_bytes()).hexdigest(),
            "candidate_rows": 2,
            "forecast_timestamp_utc": forecast_time,
            "prediction_cutoff_utc": evidence["cutoff_utc"],
            "cutoff_verified": True,
            "cutoff_basis": "official_rule_derived:first_match_start_minus_1_minute",
            "cutoff_source_sha256": evidence["evidence_sha256"],
            "cutoff_status": "certified",
            "certification_status": "certified",
            "cutoff_kind": "official_rule_derived",
            "cutoff_semantics": metadata["cutoff_semantics"],
            "cutoff_evidence_path": evidence_path.name,
            "cutoff_evidence_file_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
            "certification": {
                "pre_lock_eligible": True,
                "exact_dunkest_cutoff_verified": True,
            },
        },
        "runtime_feature_snapshot": {
            "path": feature_path.name,
            "sha256": hashlib.sha256(feature_path.read_bytes()).hexdigest(),
            "candidate_rows": 2,
            "source_input_dataset_identifier": "test-inputs",
            "source_input_provenance": [],
            "certification_status": "valid",
        },
        "dataset_identifier": "test-inputs",
        "inputs": [],
    }

    valid = archive.player_forecast_snapshot_validation(run_dir, run_manifest)
    assert valid["status"] == "valid", valid["errors"]

    missing_evidence_manifest = json.loads(json.dumps(run_manifest))
    missing_evidence_manifest["player_forecast_snapshot"].pop("cutoff_evidence_path")
    missing_evidence = archive.player_forecast_snapshot_validation(run_dir, missing_evidence_manifest)
    assert missing_evidence["status"] == "invalid"
    assert any("cutoff evidence file is missing" in error for error in missing_evidence["errors"])

    evidence_path.write_text(evidence_path.read_text().replace("9901", "9909"))
    altered = archive.player_forecast_snapshot_validation(run_dir, run_manifest)
    assert altered["status"] == "invalid"
    assert any("missing, altered" in error for error in altered["errors"])
