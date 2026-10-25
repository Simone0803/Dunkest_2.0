from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dunkest.data.dunkest.fixtures import _snapshot_freshness


def test_snapshot_freshness_rejects_old_source_timestamp(tmp_path: Path):
    source = tmp_path / "market.parquet"
    source.write_bytes(b"market")
    fetched = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    (tmp_path / "market.parquet.meta.json").write_text(json.dumps({"fetched_at": fetched}))
    passed, reason = _snapshot_freshness(source, max_age_hours=36)
    assert not passed
    assert "stale" in reason


def test_snapshot_freshness_requires_metadata_not_file_mtime(tmp_path: Path):
    source = tmp_path / "market.parquet"
    source.write_bytes(b"market")
    passed, reason = _snapshot_freshness(source, max_age_hours=36)
    assert not passed
    assert "metadata" in reason


def test_snapshot_freshness_accepts_recent_timestamp(tmp_path: Path):
    source = tmp_path / "market.parquet"
    source.write_bytes(b"market")
    fetched = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    (tmp_path / "market.parquet.meta.json").write_text(json.dumps({"fetched_at": fetched}))
    passed, reason = _snapshot_freshness(source, max_age_hours=36)
    assert passed
    assert "fresh" in reason



def test_backtest_readiness_rejects_stale_fixture_bridge(tmp_path: Path):
    import pandas as pd
    from dunkest.config import Settings
    from dunkest.data.dunkest.fixtures import check_backtest_readiness

    processed = tmp_path / "processed"
    processed.mkdir()
    old = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    mapping = pd.DataFrame([{
        "season_id": "26", "nba_season": "2026-27", "nba_game_id": "0022600001",
        "game_datetime_utc": "2027-10-20T23:00:00Z", "game_date_local": "2027-10-20",
        "home_team": "BOS", "away_team": "PHI", "home_team_eligible": True,
        "away_team_eligible": True, "dunkest_gameweek": 1, "dunkest_turn": 1,
        "fantasy_eligible": True, "mapping_verified": True, "eligibility_reason": "verified",
        "source": "test_fixture", "source_url_or_endpoint": "test", "source_retrieved_at_utc": old,
        "mapping_version": "test", "raw_payload_sha256": "a" * 64,
    }])
    mapping.to_parquet(processed / "dunkest_fixture_mapping_26_test.parquet", index=False)
    settings = Settings(season="2026-27", season_id="26", target_gameweek=1, data_dir=str(tmp_path))
    result = check_backtest_readiness(settings, 1)
    assert not result["checks"]["FIXTURE_MAPPING"]["pass"]
    assert "stale" in result["checks"]["FIXTURE_MAPPING"]["reason"]
