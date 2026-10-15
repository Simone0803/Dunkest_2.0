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
    _merge_live_market_pool,
)
from dunkest.data.dunkest.opening import (
    _load_credits_csv, fetch_opening_coach_market, fetch_opening_market_pool,
)


def test_live_market_is_full_candidate_pool_and_overrides_season_metadata():
    season_players = pd.DataFrame([{
        "player_name": "Luka Doncic", "cr": 9.0, "position": "G",
        "role": "G", "team_code": "DAL", "pdk": 8.2,
    }])
    live_market = pd.DataFrame([
        {
            "player_name": "Luka Dončić", "cr": 12.5, "position": "F",
            "team_code": "LAL", "lineup_group": "QUINTETTO", "status": "AVAILABLE",
        },
        {
            "player_name": "Unlisted Rookie", "cr": 4.0, "position": "G",
            "team_code": "UTA", "lineup_group": "PANCHINA", "status": "AVAILABLE",
        },
    ])

    result = _merge_live_market_pool(season_players, live_market).set_index("player_name")

    assert len(result) == 2
    assert result.loc["Luka Doncic", "cr"] == 12.5
    assert result.loc["Luka Doncic", "team_code"] == "LAL"
    assert result.loc["Luka Doncic", "role"] == "F"
    assert result.loc["Luka Doncic", "pdk"] == 8.2
    assert result.loc["Unlisted Rookie", "cr"] == 4.0
    assert result.loc["Unlisted Rookie", "team_code"] == "UTA"
    assert pd.isna(result.loc["Unlisted Rookie", "pdk"])



def test_opening_market_pool_appends_live_only_candidates_and_keeps_unknown_history(tmp_path, monkeypatch):
    market_path = tmp_path / "current_lineups_market.csv"
    pd.DataFrame([
        {"player_name": "Known Player", "cr": 9.0, "team": "BOS", "role": "G",
         "lineup_group": "QUINTETTO", "status": "AVAILABLE"},
        {"player_name": "Ariel Hukporti", "cr": 4.0, "team": "PHI", "role": "C",
         "lineup_group": "", "status": ""},
        {"player_name": "Confirmed Out", "cr": 4.0, "team": "LAC", "role": "C",
         "lineup_group": "INDISPONIBILI", "status": "OUT"},
    ]).to_csv(market_path, index=False)

    settings = Settings(
        data_dir=str(tmp_path), season_id="26", opening_prior_season_id="25",
        min_cr=4.0, max_cr=35.0,
    )

    def fake_season_players(cfg):
        if str(cfg.season_id) == "25":
            return pd.DataFrame([{
                "player_name": "Known Player", "cr": 8.0, "position": "G",
                "role": "G", "team_code": "BOS", "pdk": 10.0, "cr_official": 8.0,
            }])
        return pd.DataFrame([{
            "player_name": "Known Player", "cr": 9.0, "position": "G",
            "role": "G", "team_code": "BOS", "pdk": 9.0, "cr_official": 9.0,
        }])

    monkeypatch.setattr("dunkest.data.dunkest.opening.dk_client.fetch_nba_season_players", fake_season_players)
    monkeypatch.setattr(
        "dunkest.data.access.get_injuries",
        lambda cfg: pd.DataFrame(columns=["player_name", "team", "status"]),
    )

    result = fetch_opening_market_pool(
        settings, credits_file=market_path, use_pdk_cr_proxy=False,
    ).set_index("player_name")

    assert set(result.index) == {"Known Player", "Ariel Hukporti"}
    assert result.loc["Ariel Hukporti", "team_code"] == "PHI"
    assert result.loc["Ariel Hukporti", "role"] == "C"
    assert result.loc["Ariel Hukporti", "cr"] == 4.0
    assert pd.isna(result.loc["Ariel Hukporti", "prior_pdk"])
    assert result.loc["Known Player", "prior_pdk"] == 10.0


def test_live_market_rejects_ambiguous_normalized_player_identities():
    live_market = pd.DataFrame([
        {"player_name": "Luka Doncic", "cr": 12.0, "position": "G", "team_code": "LAL"},
        {"player_name": "Luka Dončić", "cr": 12.0, "position": "G", "team_code": "LAL"},
    ])

    with pytest.raises(RuntimeError, match="duplicate normalized player identities"):
        _merge_live_market_pool(pd.DataFrame(), live_market)


@pytest.mark.parametrize("field,value", [
    ("cr", None),
    ("position", ""),
    ("team_code", ""),
])
def test_live_market_rejects_incomplete_candidate_rows(field, value):
    live_market = pd.DataFrame([{
        "player_name": "Incomplete Market Row", "cr": 8.0,
        "position": "G", "team_code": "BOS",
    }])
    live_market.loc[0, field] = value

    with pytest.raises(RuntimeError, match="missing or invalid name, CR, role, or team"):
        _merge_live_market_pool(pd.DataFrame(), live_market)


def test_get_dunkest_data_keeps_live_only_players_in_prediction_market(tmp_path, monkeypatch):
    market_path = tmp_path / "current_lineups_market.csv"
    pd.DataFrame([
        {"player_name": "Known Player", "cr": 11.0, "team": "BOS", "role": "G",
         "lineup_group": "QUINTETTO", "status": "AVAILABLE"},
        {"player_name": "Unlisted Rookie", "cr": 4.0, "team": "UTA", "role": "C",
         "lineup_group": "PANCHINA", "status": "AVAILABLE"},
    ]).to_csv(market_path, index=False)
    metadata_path = market_path.with_suffix(market_path.suffix + ".meta.json")
    metadata_path.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")

    settings = Settings(data_dir=str(tmp_path), season_id="26", target_gameweek=2)
    season_players = pd.DataFrame([{
        "player_name": "Known Player", "cr": 9.0, "position": "F",
        "role": "F", "team_code": "ATL", "pdk": 10.0,
    }])
    monkeypatch.setattr(access.dk_module, "fetch_nba_season_players", lambda *_: season_players.copy())
    monkeypatch.setattr(
        access.dk_module,
        "fetch_dunkest_gameweek_players",
        lambda _settings, gameweek: (
            pd.DataFrame([{
                "player_name": "Known Player", "cr": 11.0, "pdk": 13.0, "plus": 0.2,
            }])
            if gameweek == 2 else pd.DataFrame()
        ),
    )
    monkeypatch.setattr(access, "write_parquet", lambda *args, **kwargs: None)

    result = access.get_dunkest_data(settings, gameweek=2, force_refresh=True).set_index("player_name")

    assert set(result.index) == {"Known Player", "Unlisted Rookie"}
    assert result.loc["Known Player", "cr"] == 11.0
    assert result.loc["Known Player", "role"] == "G"
    assert result.loc["Known Player", "team_code"] == "BOS"
    assert result.loc["Known Player", "prior_pdk"] == 10.0
    assert result.loc["Known Player", "pdk"] == 10.0
    assert result.loc["Known Player", "actual_pdk"] == 13.0
    assert result.loc["Unlisted Rookie", "cr"] == 4.0
    assert result.loc["Unlisted Rookie", "team_code"] == "UTA"
    assert pd.isna(result.loc["Unlisted Rookie", "prior_pdk"])
    assert pd.isna(result.loc["Unlisted Rookie", "actual_pdk"])


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


def test_lineups_csv_preserves_turn_specific_rotation_annotations(tmp_path):
    path = tmp_path / "turn_annotations.csv"
    path.write_text(
        "player_name,cr,team,role,lineup_group_turn1,starter_turn1,status_turn1,"
        "lineup_group_turn2,starter_turn2,status_turn2,"
        "lineup_group_turn3,starter_turn3,status_turn3\n"
        "Player A,8.0,BOS,G,QUINTETTO,true,AVAILABLE,PANCHINA,false,AVAILABLE,,,\n",
        encoding="utf-8",
    )
    loaded = _load_credits_csv(path).iloc[0]

    assert loaded["lineup_group_turn1"] == "QUINTETTO"
    assert bool(loaded["starter_turn1"]) is True
    assert loaded["status_turn1"] == "AVAILABLE"
    assert loaded["lineup_group_turn2"] == "PANCHINA"
    assert bool(loaded["starter_turn2"]) is False
    assert loaded["status_turn2"] == "AVAILABLE"
    assert loaded["lineup_group_turn3"] == ""


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
            "actual_pdk": 0.0, "prior_pdk": 9.0, "gameweek_stats_available": True,
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


def test_legacy_cached_matchday_without_prior_pdk_is_refreshed(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26")
    legacy_cache = pd.DataFrame([{
        "player_name": "Player A", "team_code": "BOS", "cr": 8.0, "pdk": 9.0,
        "official_plusvalenza": 0.2, "actual_pdk": 0.0,
        "gameweek_stats_available": True,
    }])
    refreshed = pd.DataFrame([{
        "player_name": "Player A", "team_code": "BOS", "cr": 8.0, "pdk": 9.0,
    }])
    calls = []
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(access, "read_parquet", lambda *_: legacy_cache)
    monkeypatch.setattr(
        access.dk_module, "fetch_nba_season_players",
        lambda *_: calls.append("season") or refreshed.copy(),
    )
    monkeypatch.setattr(
        access.dk_module, "fetch_dunkest_gameweek_players",
        lambda *_: pd.DataFrame(),
    )
    monkeypatch.setattr(access, "write_parquet", lambda *args, **kwargs: None)

    result = access.get_dunkest_data(settings, gameweek=2)

    assert calls == ["season"]
    assert result.loc[0, "prior_pdk"] == 9.0


def test_official_plusvalenza_maps_to_market_names_with_accents():
    market = pd.DataFrame(
        [{"player_name": "Luka Dončić"}, {"player_name": "Nikola Jokić"}]
    )
    week_stats = pd.DataFrame(
        [{"player_name": "Luka Doncic", "plus": 0.6}, {"player_name": "Nikola Jokic", "plus": -0.2}]
    )

    result = add_official_plusvalenza(market, week_stats)

    assert result["official_plusvalenza"].tolist() == [0.6, -0.2]


def test_official_plusvalenza_history_requires_broad_nba_team_coverage_and_caches(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season_id="26", opening_prior_season_id="25")
    calls = []
    nba_seasons = {"19", "13", "9", "7", "5"}
    nba_teams = sorted(access.NBA_TEAM_CODES)[:30]

    def fake_week(_settings, gameweek):
        season = str(_settings.season_id)
        calls.append((season, gameweek))
        if season in nba_seasons:
            teams = nba_teams
        elif season == "24":
            teams = ["BJK"]  # Euroleague-like competition with a non-NBA code.
        elif season in {"25", "22", "16", "8", "6"}:
            teams = ["BOS", "GSW"]  # False NBA candidates with only two teams.
        else:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "player_name": f"Player {i:02d}", "team_code": team, "role": "G",
                "cr": 8.0, "pdk": 20.0 + gameweek / 10, "plus": 0.1,
                "min": 30.0, "starter": 1,
            }
            for i, team in enumerate(teams)
        ])

    monkeypatch.setattr(access.dk_module, "fetch_dunkest_gameweek_players", fake_week)
    first = get_plusvalenza_history(settings)
    assert set(first["season_id"].astype(str)) == nba_seasons
    assert len(first) == len(access.PLUSVALENZA_SAMPLE_GAMEWEEKS) * settings.capital_gain_history_seasons * 30
    assert first.groupby("season_id")["gameweek"].nunique().eq(
        len(access.PLUSVALENZA_SAMPLE_GAMEWEEKS)
    ).all()
    assert ("24", 1) in calls  # Non-NBA competition is rejected.
    assert ("25", 1) in calls and ("22", 1) in calls and ("16", 1) in calls
    assert set(access._plusvalenza_season_team_coverage(first).values()) == {30}

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
