import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.data import access
from dunkest.data.access import (
    add_official_plusvalenza,
    add_previous_credit_change,
    get_plusvalenza_history,
    save_player_credit_snapshot,
    _check_live_market_freshness,
)
from dunkest.data.dunkest.opening import _load_credits_csv, fetch_opening_coach_market


def test_lineups_csv_preserves_coaches_and_parses_dunkest_credit_notation(tmp_path):
    path = tmp_path / "lineups.csv"
    path.write_text(
        'player_name,cr,team,role,lineup_group,starter,status\n'
        'Nikola Jokic,30 CR,DEN,C,QUINTETTO,true,AVAILABLE\n'
        'Joe Mazzulla,"8,5 CR",BOS,HC,COACH,,AVAILABLE\n',
        encoding="utf-8",
    )
    loaded = _load_credits_csv(path)
    coach = fetch_opening_coach_market(path)

    assert loaded.loc[loaded["player_name"] == "Joe Mazzulla", "role"].iloc[0] == "HC"
    assert loaded.loc[loaded["player_name"] == "Joe Mazzulla", "cr_file"].iloc[0] == 8.5
    jokic = loaded.loc[loaded["player_name"] == "Nikola Jokic"].iloc[0]
    assert jokic["starter"]
    assert jokic["lineup_group"] == "QUINTETTO"
    assert jokic["status"] == "AVAILABLE"
    bos = coach.loc[coach["team"] == "BOS"].iloc[0]
    assert bos["coach"] == "Joe Mazzulla"
    assert bos["coach_cr"] == 8.5
    assert len(coach) == 30


def test_lineups_coach_snapshot_has_all_30_teams_and_official_credits():
    coaches = fetch_opening_coach_market(None)

    assert len(coaches) == 30
    assert coaches["team"].nunique() == 30
    assert (pd.to_numeric(coaches["coach_cr"], errors="coerce") >= 4).all()


def test_player_credit_snapshots_measure_real_week_over_week_changes(tmp_path):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    save_player_credit_snapshot(
        settings,
        pd.DataFrame([{"player_name": "Jokić Jr.", "team_code": "DEN", "cr": 10.0}]),
        1,
    )

    result = add_previous_credit_change(
        settings,
        pd.DataFrame([
            {"player_name": "Jokic", "cr": 12.0},
            {"player_name": "New Player", "cr": 6.0},
        ]),
        2,
    )

    assert result.loc[0, "cr_change_last_gameweek"] == 2.0
    assert pd.isna(result.loc[1, "cr_change_last_gameweek"])


def test_cached_matchday_market_still_saves_credit_snapshot(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    cached_market = pd.DataFrame(
        [{
            "player_name": "Player A", "team_code": "BOS", "cr": 8.0,
            "official_plusvalenza": 0.2,
            "actual_pdk": 0.0, "gameweek_stats_available": True,
        }]
    )
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        access,
        "read_parquet",
        lambda path: cached_market if path.name == "dunkest_players_26_gw2.parquet" else None,
    )

    result = access.get_dunkest_data(settings, gameweek=2)

    snapshot = tmp_path / "processed" / "player_credits_26_gw2.parquet"
    assert pd.isna(result.loc[0, "cr_change_last_gameweek"])
    assert snapshot.exists()


def test_official_plusvalenza_maps_to_market_names_with_accents():
    market = pd.DataFrame(
        [{"player_name": "Luka Dončić"}, {"player_name": "Nikola Jokić"}]
    )
    week_stats = pd.DataFrame(
        [{"player_name": "Luka Doncic", "plus": 0.6}, {"player_name": "Nikola Jokic", "plus": -0.2}]
    )

    result = add_official_plusvalenza(market, week_stats)

    assert result["official_plusvalenza"].tolist() == [0.6, -0.2]


def test_official_plusvalenza_history_collects_all_prior_seasons_and_caches(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26", opening_prior_season_id="25")
    calls = []
    nba_seasons = {"25", "22", "19", "16", "13"}

    def fake_week(_settings, gameweek):
        season = str(_settings.season_id)
        calls.append((season, gameweek))
        if season not in nba_seasons and season != "24":
            return pd.DataFrame()
        return pd.DataFrame(
            [{
                "player_name": "Player A", "team_code": "BJK" if season == "24" else "BOS", "role": "G",
                "cr": 8.0, "pdk": 20.0 + gameweek / 10, "plus": 0.1,
                "min": 30.0, "starter": 1,
            }]
        )

    monkeypatch.setattr(access.dk_module, "fetch_dunkest_gameweek_players", fake_week)
    first = get_plusvalenza_history(settings)
    assert set(first["season_id"].astype(str)) == nba_seasons
    assert len(first) == len(access.PLUSVALENZA_SAMPLE_GAMEWEEKS) * settings.capital_gain_history_seasons
    assert first.groupby("season_id")["gameweek"].nunique().eq(
        len(access.PLUSVALENZA_SAMPLE_GAMEWEEKS)
    ).all()
    assert ("24", 1) in calls  # Euroleague-like team codes are detected then excluded.

    monkeypatch.setattr(
        access.dk_module,
        "fetch_dunkest_gameweek_players",
        lambda *_args: (_ for _ in ()).throw(AssertionError("cache should be used")),
    )
    cached = get_plusvalenza_history(settings)
    assert len(cached) == len(first)


def test_timestamped_live_market_is_rejected_when_stale(tmp_path):
    market = tmp_path / "current_lineups_market.csv"
    market.write_text("player_name,cr,team,role\nA,5,BOS,G\n", encoding="utf-8")
    metadata = market.with_suffix(market.suffix + ".meta.json")
    metadata.write_text(
        json.dumps({
            "fetched_at": (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(),
            "source": "test",
        }),
        encoding="utf-8",
    )
    settings = Settings(market_cache_max_age_hours=6)

    with pytest.raises(RuntimeError, match="Lineups market is stale"):
        _check_live_market_freshness(settings, market)


def test_legacy_live_market_without_metadata_warns(tmp_path):
    market = tmp_path / "current_lineups_market.csv"
    market.write_text("player_name,cr,team,role\nA,5,BOS,G\n", encoding="utf-8")

    with pytest.warns(RuntimeWarning, match="no freshness metadata"):
        _check_live_market_freshness(Settings(), market)
