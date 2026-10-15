from __future__ import annotations

import json
import hashlib

import pandas as pd

from dunkest.data.dunkest.fixtures import (
    _fixture_mapping_temporal_validity,
    _snapshot_freshness_as_of,
)


def test_historical_snapshot_freshness_is_measured_at_lock_not_now(tmp_path):
    snapshot = tmp_path / "market.parquet"
    snapshot.write_bytes(b"snapshot")
    fetched = pd.Timestamp("2025-01-02T19:00:00Z")
    (tmp_path / "market.parquet.meta.json").write_text(
        json.dumps({"fetched_at": fetched.isoformat()}), encoding="utf-8"
    )

    passed, reason = _snapshot_freshness_as_of(
        snapshot, pd.Timestamp("2025-01-02T20:00:00Z")
    )

    assert passed
    assert reason == "available 1.0h before historical lock"


def test_historical_snapshot_captured_after_lock_is_rejected(tmp_path):
    snapshot = tmp_path / "market.parquet"
    snapshot.write_bytes(b"snapshot")
    fetched = pd.Timestamp("2025-01-02T20:01:00Z")
    (tmp_path / "market.parquet.meta.json").write_text(
        json.dumps({"fetched_at": fetched.isoformat()}), encoding="utf-8"
    )

    passed, reason = _snapshot_freshness_as_of(
        snapshot, pd.Timestamp("2025-01-02T20:00:00Z")
    )

    assert not passed
    assert "after the historical lock" in reason


def test_historical_fixture_mapping_age_is_relative_to_its_fixture():
    mapping = pd.DataFrame(
        {
            "game_datetime_utc": ["2025-01-02T20:00:00Z"],
            "source_retrieved_at_utc": ["2025-01-02T19:00:00Z"],
        }
    )

    passed, reason = _fixture_mapping_temporal_validity(mapping)

    assert passed
    assert "before each fixture lock" in reason


def test_fixture_mapping_after_kickoff_is_rejected():
    mapping = pd.DataFrame(
        {
            "game_datetime_utc": ["2025-01-02T20:00:00Z"],
            "source_retrieved_at_utc": ["2025-01-02T20:01:00Z"],
        }
    )

    passed, reason = _fixture_mapping_temporal_validity(mapping)

    assert not passed
    assert "after a fixture lock" in reason


def test_backtest_readiness_uses_archived_inputs_without_live_snapshots(tmp_path):
    from dunkest.config import Settings
    from dunkest.data.dunkest.fixtures import check_backtest_readiness

    processed = tmp_path / "processed"
    processed.mkdir()
    lock = pd.Timestamp("2025-01-02T20:00:00Z")
    captured = lock - pd.Timedelta(hours=1)
    nba_game_id = "0022500001"
    mapping = pd.DataFrame([{
        "season_id": "25", "nba_season": "2025-26", "nba_game_id": nba_game_id,
        "game_datetime_utc": lock, "game_date_local": lock.date(),
        "home_team": "BOS", "away_team": "PHI", "home_team_eligible": True,
        "away_team_eligible": True, "dunkest_gameweek": 1, "dunkest_turn": 1,
        "fantasy_eligible": True, "mapping_verified": True, "eligibility_reason": "verified",
        "source": "test_fixture", "source_url_or_endpoint": "test",
        "source_retrieved_at_utc": captured, "mapping_version": "test",
        "raw_payload_sha256": "a" * 64,
    }])
    mapping.to_parquet(processed / "dunkest_fixture_mapping_25_test.parquet", index=False)

    def write_snapshot(name: str, frame: pd.DataFrame) -> None:
        path = processed / name
        frame.to_parquet(path, index=False)
        path.with_suffix(path.suffix + ".meta.json").write_text(
            json.dumps({"fetched_at": captured.isoformat()}), encoding="utf-8"
        )

    write_snapshot("player_credits_25_gw1.parquet", pd.DataFrame([{
        "player_name": "Player One", "team_code": "BOS", "role": "G",
        "gameweek": 1, "cr": 10.0,
    }]))
    write_snapshot("injuries_25_gw1.parquet", pd.DataFrame([{
        "player_name": "Player One", "team": "BOS", "status": "Available", "gameweek": 1,
    }]))
    write_snapshot("coach_market_25_gw1.parquet", pd.DataFrame([{
        "coach": "Coach One", "team": "BOS", "coach_cr": 10.0,
        "opponent": "PHI", "date": lock.date(), "nba_game_id": nba_game_id,
        "fixture_source": "test_fixture",
    }]))
    # Legacy processed aggregates are not the immutable fixture-linked result
    # archive and must not make this backtest round appear ready.
    write_snapshot("dunkest_players_25_gw1.parquet", pd.DataFrame([{
        "player_name": "Player One", "actual_pdk": 10.0,
        "gameweek_stats_available": True, "nba_game_id": nba_game_id,
    }]))
    write_snapshot("dunkest_coach_results_25_gw1.parquet", pd.DataFrame([{
        "team": "BOS", "nba_game_id": nba_game_id, "actual_coach_pdk": 10.0,
    }]))
    legacy_only = check_backtest_readiness(
        Settings(season="2025-26", season_id="25", target_gameweek=1, data_dir=str(tmp_path)), 1
    )
    assert not legacy_only["checks"]["ACTUAL_RESULTS"]["pass"]
    assert not legacy_only["backtest_ready"]

    archive_dir = tmp_path / "archive" / "25" / "gw1" / "post_match_test"
    archive_dir.mkdir(parents=True)
    pd.DataFrame([{
        "player_name": "Player One", "actual_pdk": 10.0,
        "nba_game_id": nba_game_id,
    }]).to_parquet(archive_dir / "player_results.parquet", index=False)
    pd.DataFrame([{
        "coach": "Coach One", "team": "BOS", "nba_game_id": nba_game_id,
        "actual_coach_pdk": 10.0,
    }]).to_parquet(archive_dir / "coach_results.parquet", index=False)
    archive_hashes = {
        name: hashlib.sha256((archive_dir / name).read_bytes()).hexdigest()
        for name in ("player_results.parquet", "coach_results.parquet")
    }
    (archive_dir / "manifest.json").write_text(json.dumps({
        "season_id": "25", "dunkest_gameweek": 1, "schema_version": 1,
        "source": "official Dunkest player results + verified NBA coach reconstruction",
        "retrieved_at_utc": "2025-01-03T12:00:00Z", "sha256": archive_hashes,
        "coverage_audit": {
            "timing_check_passed": True,
            "player": {"prediction_coverage": 1.0},
            "coach": {"coverage": 1.0},
        },
    }), encoding="utf-8")

    settings = Settings(season="2025-26", season_id="25", target_gameweek=1, data_dir=str(tmp_path))
    result = check_backtest_readiness(settings, 1)

    assert result["backtest_ready"]
    assert result["checks"]["PRE_MATCH_DATA"]["pass"]
    assert not result["checks"]["LINEUPS_MARKET_SNAPSHOT"]["pass"]
    assert not result["checks"]["LINEUPS_AVAILABILITY_SNAPSHOT"]["pass"]

    archive_manifest = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
    archive_manifest["coverage_audit"]["player"]["prediction_coverage"] = 0.5
    archive_manifest["coverage_audit"]["coach"]["coverage"] = 0.5
    (archive_dir / "manifest.json").write_text(json.dumps(archive_manifest), encoding="utf-8")
    partial_coverage = check_backtest_readiness(settings, 1)
    assert partial_coverage["backtest_ready"]

    pd.DataFrame([{
        "coach": "Coach One", "team": "BOS", "nba_game_id": nba_game_id,
        "actual_coach_pdk": float("nan"),
    }]).to_parquet(archive_dir / "coach_results.parquet", index=False)
    manifest_path = archive_dir / "manifest.json"
    archive_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive_manifest["sha256"]["coach_results.parquet"] = hashlib.sha256(
        (archive_dir / "coach_results.parquet").read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(archive_manifest), encoding="utf-8")
    invalid_actuals = check_backtest_readiness(settings, 1)
    assert not invalid_actuals["checks"]["ACTUAL_RESULTS"]["pass"]
    assert not invalid_actuals["backtest_ready"]
