import json
from datetime import datetime, timezone

import pandas as pd

from dunkest.config import Settings
from dunkest.data import access


def test_opening_coach_catalog_works_before_schedule_is_published(tmp_path, monkeypatch):
    monkeypatch.setattr(access, "get_schedule", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(access, "get_future_schedule", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(access.nba, "fetch_schedule", lambda *args, **kwargs: pd.DataFrame())
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=False)
    market = pd.DataFrame(
        [
            {"coach": "Coach A", "team": "BOS", "coach_cr": 8.0},
            {"coach": "Coach B", "team": "NYK", "coach_cr": 7.0},
        ]
    )

    result = access.get_coach_data(settings, gameweek=1, force_refresh=True, coach_market=market)

    assert set(result["team"]) == {"BOS", "NYK"}
    assert set(result["coach"]) == {"Coach A", "Coach B"}
    assert result["opponent_coach_cr"].isna().all()


def test_partial_turn_mapping_keeps_unmatched_coaches_in_candidate_market(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    market = pd.DataFrame(
        [
            {"coach": "Coach A", "team": "BOS", "coach_cr": 8.0},
            {"coach": "Coach B", "team": "NYK", "coach_cr": 7.0},
            {"coach": "Coach C", "team": "CHA", "coach_cr": 6.0},
            {"coach": "Coach D", "team": "UTA", "coach_cr": 5.0},
        ]
    )
    mapping = pd.DataFrame([{
        "game_datetime_utc": pd.Timestamp("2026-10-20", tz="UTC"),
        "home_team": "BOS",
        "away_team": "NYK",
        "nba_game_id": "game-1",
        "dunkest_turn": 1,
        "source": "lineups",
        "fantasy_eligible": True,
    }])
    monkeypatch.setattr(access, "get_fixture_mapping", lambda *args, **kwargs: mapping)
    monkeypatch.setattr(access, "_historical_coach_scores", lambda *_args: {"CHA": 4.2, "UTA": 3.8})
    monkeypatch.setattr(access, "write_parquet", lambda *args, **kwargs: None)

    result = access.get_coach_data(
        settings, gameweek=1, force_refresh=True, coach_market=market
    )

    assert set(result["team"]) == {"BOS", "NYK", "CHA", "UTA"}
    fallback = result.set_index("team").loc[["CHA", "UTA"]]
    assert fallback["opponent"].eq("").all()
    assert fallback["prior_coach_pdk"].to_dict() == {"CHA": 4.2, "UTA": 3.8}


def test_live_lineups_market_bypasses_cached_coach_data(tmp_path, monkeypatch):
    market_path = tmp_path / "current_lineups_market.csv"
    market_path.write_text(
        "player_name,cr,team,role\nCoach A,11,BOS,HC\nCoach B,7,NYK,HC\n",
        encoding="utf-8",
    )
    market_path.with_suffix(market_path.suffix + ".meta.json").write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    stale_cache_reads = []
    schedule = pd.DataFrame(
        [{
            "GAME_DATE": pd.Timestamp("2026-10-20"),
            "HOME_TEAM": "BOS",
            "AWAY_TEAM": "NYK",
            "NBA_WEEK_NUMBER": 1,
            "GAME_STATUS": 1,
        }]
    )
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        access,
        "read_parquet",
        lambda path: stale_cache_reads.append(path) or pd.DataFrame(),
    )
    monkeypatch.setattr(access, "write_parquet", lambda *args, **kwargs: None)
    monkeypatch.setattr(access, "get_future_schedule", lambda *args, **kwargs: schedule)
    monkeypatch.setattr(access.dk_module, "fetch_coach_cr_table", lambda *args: pd.DataFrame())

    result = access.get_coach_data(settings, gameweek=1)

    assert stale_cache_reads == []
    assert result.set_index("team").loc["BOS", "coach_cr"] == 11.0
