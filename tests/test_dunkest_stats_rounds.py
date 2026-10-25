import json
import logging
from datetime import datetime, timezone

import pandas as pd

from dunkest.config import Settings
from dunkest.data import access
from dunkest.data.cache import read_cache_metadata, write_parquet
from dunkest.data.dunkest import client
from dunkest.data.dunkest.official_pdk import attach_observed_round_pdk_labels
from dunkest.features.builder import _pdk_feature_series


def test_default_config_keeps_nba_and_dunkest_stats_season_ids_separate():
    settings = Settings.from_yaml()

    assert settings.season_id == "26"
    assert settings.dunkest_stats_season_id == "29"


def test_week_round_lookup_uses_dunkest_statistics_season_id(monkeypatch):
    settings = Settings(season_id="26", dunkest_stats_season_id="29")
    calls = []

    def fake_get_json(url, *, params, timeout):
        calls.append((url, params, timeout))
        return ["1", "2", "3"]

    monkeypatch.setattr(client, "get_json", fake_get_json)

    assert client.fetch_week_rounds(settings, 1) == ["1", "2", "3"]
    assert calls[0][1] == {"season_id": "29", "week_number": 1}


def test_stats_refresh_failure_reuses_only_same_gameweek_pregame_cache(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=str(tmp_path), season_id="26", season="2026-27", target_gameweek=2,
        market_cache_max_age_hours=6,
    )
    processed = tmp_path / "processed"
    processed.mkdir()
    names = [f"Player {i:03d}" for i in range(250)]
    cached = pd.DataFrame({
        "player_name": names, "cr": [6.0] * 250, "position": ["G"] * 250,
        "pdk": [float("nan")] * 250, "team_code": ["BOS"] * 250,
        "lineup_group": [""] * 250, "status": ["Available"] * 250,
        "official_plusvalenza": [float("nan")] * 250,
        "gameweek_stats_available": [False] * 250, "actual_pdk": [float("nan")] * 250,
        "gameweek": [2] * 250,
    })
    cached_path = processed / "dunkest_players_26_gw2.parquet"
    write_parquet(cached, cached_path, source="dunkest_api/stats/table", season_id="26", gameweek=2)
    cached_timestamp = read_cache_metadata(cached_path)["fetched_at"]
    market_path = tmp_path / "current_lineups_market.csv"
    pd.DataFrame({
        "player_name": names, "cr": [6.2] * 250, "role": ["G"] * 250,
        "team": ["BOS"] * 250,
    }).to_csv(market_path, index=False)
    market_path.with_suffix(".csv.meta.json").write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(), "source": "dunkest_lineups_browser",
    }))
    monkeypatch.setattr(
        access.dk_module,
        "fetch_nba_season_players",
        lambda *_: (_ for _ in ()).throw(RuntimeError("DNS unavailable")),
    )
    monkeypatch.setattr(
        access.dk_module,
        "fetch_dunkest_gameweek_players",
        lambda *_: (_ for _ in ()).throw(AssertionError("cached pregame rows must skip live GW fetches")),
    )

    result = access.get_dunkest_data(settings, 2)

    assert len(result) == 250
    assert result["cr"].eq(6.2).all()
    assert result["actual_pdk"].isna().all()
    assert not result["gameweek_stats_available"].any()
    assert read_cache_metadata(cached_path)["fetched_at"] == cached_timestamp


def test_single_round_fetch_uses_official_totals_and_exact_round(monkeypatch):
    settings = Settings(season_id="26", dunkest_stats_season_id="29")
    calls = []
    monkeypatch.setattr(client, "fetch_week_rounds", lambda _settings, _week: ["1", "2", "3"])

    def fake_table(_settings, **params):
        calls.append(params)
        return pd.DataFrame([{
            "player_name": "Donovan Mitchell", "team_code": "CLE", "role": "G",
            "pdk": 38.0, "cr": 14.1, "plus": 0.2, "min": 35,
        }])

    monkeypatch.setattr(client, "fetch_stats_table", fake_table)

    result = client.fetch_dunkest_round_players(settings, 1, 3)

    assert result.loc[0, "pdk"] == 38.0
    assert result.loc[0, "cr"] == 14.1
    assert result.loc[0, "plus"] == 0.2
    assert result.loc[0, "dunkest_round"] == 3
    assert calls[0]["season_id"] == "29"
    assert calls[0]["stats_type"] == "tot"
    assert calls[0]["weeks"] == [1]
    assert calls[0]["rounds"] == ["3"]


def test_round_snapshot_preserves_the_first_observed_credits(tmp_path):
    settings = Settings(
        data_dir=str(tmp_path), season_id="26", dunkest_stats_season_id="29"
    )
    original = pd.DataFrame([{
        "player_name": "Donovan Mitchell", "team_code": "CLE", "role": "G",
        "pdk": 38.0, "cr": 14.1, "plus": 0.2, "min": 35,
    }])
    corrected_later = original.assign(cr=14.5, plus=0.6)

    assert access.save_dunkest_round_snapshot(settings, original, 1, 3)
    assert not access.save_dunkest_round_snapshot(settings, corrected_later, 1, 3)

    saved = pd.read_parquet(
        tmp_path / "processed" / "dunkest_stats_26_gw1_round3.parquet"
    )
    assert len(saved) == 1
    assert saved.loc[0, "pdk"] == 38.0
    assert saved.loc[0, "cr"] == 14.1
    assert saved.loc[0, "plus"] == 0.2
    assert saved.loc[0, "gameweek"] == 1
    assert saved.loc[0, "dunkest_round"] == 3
    assert pd.notna(saved.loc[0, "observed_at_utc"])


def test_gw1_round_stats_and_credits_are_archived_for_gw2_market(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=str(tmp_path), season_id="26", dunkest_stats_season_id="29",
        target_gameweek=2,
    )
    market_path = settings.data_path / "current_lineups_market.csv"
    market_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "player_name": "Donovan Mitchell", "role": "G", "team": "CLE",
        "cr": 14.1, "lineup_group": "QUINTETTO", "status": "AVAILABLE",
    }]).to_csv(market_path, index=False)
    market_path.with_suffix(".csv.meta.json").write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }))

    monkeypatch.setattr(access.dk_module, "fetch_nba_season_players", lambda _s: pd.DataFrame([{
        "player_name": "Donovan Mitchell", "team_code": "CLE", "position": "G",
        "cr": 14.1, "pdk": 30.0,
    }]))

    def gameweek_stats(_settings, week):
        if week != 1:
            return pd.DataFrame()
        return pd.DataFrame([{
            "player_name": "Donovan Mitchell", "team_code": "CLE", "role": "G",
            "cr": 14.1, "pdk": 30.0, "plus": 0.2, "dunkest_rounds": "1,2,3",
        }])

    monkeypatch.setattr(access.dk_module, "fetch_dunkest_gameweek_players", gameweek_stats)
    monkeypatch.setattr(access.dk_module, "fetch_dunkest_round_players", lambda _s, week, rnd: pd.DataFrame([{
        "player_name": "Donovan Mitchell", "team_code": "CLE", "role": "G",
        "cr": 14.1, "pdk": 38.0 if rnd == 3 else 22.0, "plus": 0.2,
        "min": 35, "gameweek": week, "dunkest_round": rnd,
    }]))

    market = access.get_dunkest_data(settings, gameweek=2, force_refresh=True)

    assert market.loc[0, "prior_pdk"] == 30.0
    for rnd in (1, 2, 3):
        saved = pd.read_parquet(
            tmp_path / "processed" / f"dunkest_stats_26_gw1_round{rnd}.parquet"
        )
        assert len(saved) == 1
        assert saved.loc[0, "gameweek"] == 1
        assert saved.loc[0, "cr"] == 14.1
    assert pd.read_parquet(
        tmp_path / "processed" / "dunkest_stats_26_gw1_round3.parquet"
    ).loc[0, "pdk"] == 38.0


def test_empty_prior_round_scrape_is_reported_and_not_archived(tmp_path, monkeypatch, caplog):
    settings = Settings(
        data_dir=str(tmp_path), season_id="26", dunkest_stats_season_id="29",
        target_gameweek=2,
    )
    market_path = settings.data_path / "current_lineups_market.csv"
    market_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "player_name": "Donovan Mitchell", "role": "G", "team": "CLE", "cr": 14.1,
        "lineup_group": "QUINTETTO", "status": "AVAILABLE",
    }]).to_csv(market_path, index=False)
    market_path.with_suffix(".csv.meta.json").write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }))
    monkeypatch.setattr(access.dk_module, "fetch_nba_season_players", lambda _s: pd.DataFrame([{
        "player_name": "Donovan Mitchell", "team_code": "CLE", "position": "G",
        "cr": 14.1, "pdk": 30.0,
    }]))

    def gameweek_stats(_settings, week):
        return pd.DataFrame([{
            "player_name": "Donovan Mitchell", "team_code": "CLE", "role": "G",
            "cr": 14.1, "pdk": 30.0, "plus": 0.2,
            **({"dunkest_rounds": "1"} if week == 1 else {}),
        }])

    monkeypatch.setattr(access.dk_module, "fetch_dunkest_gameweek_players", gameweek_stats)
    monkeypatch.setattr(
        access.dk_module, "fetch_dunkest_round_players",
        lambda _settings, _week, _round: pd.DataFrame(),
    )

    caplog.set_level(logging.WARNING, logger=access.__name__)
    access.get_dunkest_data(settings, gameweek=2, force_refresh=True)

    assert "are empty; no PDK/CR snapshot was archived" in caplog.text
    assert not (tmp_path / "processed" / "dunkest_stats_26_gw1_round1.parquet").exists()


def _round_join_logs():
    return pd.DataFrame([{
        "PLAYER_ID": 123,
        "PLAYER_NAME": "Donovan Mitchell",
        "TEAM_ABBREVIATION": "CLE",
        "GAME_ID": "0022600001",
        "GAME_DATE": "2026-10-20",
        "PTS": 28,
        "AST": 5,
        "REB": 4,
        "STL": 1,
        "BLK": 0,
        "OREB": 1,
        "DREB": 3,
        "TOV": 2,
        "PDK": 32.0,
    }])


def _round_join_snapshot(observed_at="2026-10-21T09:00:00+00:00"):
    return pd.DataFrame([{
        "player_name": "Donovan Mitchell",
        "team_code": "CLE",
        "pdk": 34.0,
        "cr": 14.1,
        "plus": 0.2,
        "pts": 28,
        "ast": 5,
        "reb": 4,
        "stl": 1,
        "blk": 0,
        "oreb": 1,
        "dreb": 3,
        "tov": 2,
        "observed_at_utc": observed_at,
    }])


def test_exact_round_boxscore_overlay_attaches_only_when_available_by_cutoff(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _round_join_snapshot().to_parquet(
        processed / "dunkest_stats_26_gw1_round1.parquet", index=False
    )

    result = attach_observed_round_pdk_labels(
        _round_join_logs(), tmp_path, season_id="26",
        target_cutoff_utc="2026-10-22T12:00:00Z",
    )

    assert result.loc[0, "PDK_OFFICIAL_VALID"] == 34.0
    assert result.loc[0, "PDK_OFFICIAL_AVAILABLE_AT_UTC"] == "2026-10-21T09:00:00+00:00"
    assert result.attrs["round_pdk_overlay"]["matched"] == 1
    assert _pdk_feature_series(result).iloc[0] == 34.0


def test_round_pdk_captured_after_target_cutoff_is_not_used(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _round_join_snapshot("2026-10-23T15:00:00+00:00").to_parquet(
        processed / "dunkest_stats_26_gw1_round1.parquet", index=False
    )

    result = attach_observed_round_pdk_labels(
        _round_join_logs(), tmp_path, season_id="26",
        target_cutoff_utc="2026-10-23T12:00:00Z",
    )

    assert "PDK_OFFICIAL_VALID" not in result or pd.isna(result.loc[0, "PDK_OFFICIAL_VALID"])
    assert result.attrs["round_pdk_overlay"]["eligible_before_cutoff"] == 0
    assert _pdk_feature_series(result).iloc[0] == 32.0


def test_round_pdk_signature_requires_all_boxscore_fields_and_unique_match(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    snapshot = _round_join_snapshot()
    snapshot.loc[0, "tov"] = 7
    snapshot.to_parquet(processed / "dunkest_stats_26_gw1_round1.parquet", index=False)

    result = attach_observed_round_pdk_labels(
        _round_join_logs(), tmp_path, season_id="26",
        target_cutoff_utc="2026-10-22T12:00:00Z",
    )

    assert pd.isna(result.loc[0, "PDK_OFFICIAL_VALID"])
    assert result.attrs["round_pdk_overlay"]["unmatched"] == 1

    duplicate = pd.concat([_round_join_logs(), _round_join_logs()], ignore_index=True)
    snapshot = _round_join_snapshot()
    snapshot.to_parquet(processed / "dunkest_stats_26_gw1_round1.parquet", index=False)
    ambiguous = attach_observed_round_pdk_labels(
        duplicate, tmp_path, season_id="26",
        target_cutoff_utc="2026-10-22T12:00:00Z",
    )

    assert ambiguous["PDK_OFFICIAL_VALID"].isna().all()
    assert ambiguous.attrs["round_pdk_overlay"]["ambiguous"] == 1


def test_progressive_gw1_gw2_gw3_round_pdk_updates_respect_each_cutoff(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    logs = pd.DataFrame([
        _round_join_logs().iloc[0].to_dict(),
        {
            **_round_join_logs().iloc[0].to_dict(),
            "GAME_ID": "0022600017",
            "GAME_DATE": "2026-10-22",
            "PTS": 35,
            "PDK": 40.0,
        },
    ])
    first = _round_join_snapshot("2026-10-21T09:00:00+00:00")
    second = _round_join_snapshot("2026-10-23T15:00:00+00:00")
    first.loc[0, ["pts", "pdk", "cr"]] = [28, 34.0, 14.1]
    second.loc[0, ["pts", "pdk", "cr"]] = [35, 41.0, 14.5]
    first.to_parquet(processed / "dunkest_stats_26_gw1_round1.parquet", index=False)
    second.to_parquet(processed / "dunkest_stats_26_gw2_round1.parquet", index=False)

    gw2 = attach_observed_round_pdk_labels(
        logs, tmp_path, season_id="26", target_cutoff_utc="2026-10-23T12:00:00Z"
    )
    gw3 = attach_observed_round_pdk_labels(
        logs, tmp_path, season_id="26", target_cutoff_utc="2026-10-24T12:00:00Z"
    )

    assert gw2["PDK_OFFICIAL_VALID"].notna().sum() == 1
    assert gw2.loc[gw2["GAME_ID"].eq("0022600001"), "PDK_OFFICIAL_VALID"].iloc[0] == 34.0
    assert pd.isna(gw2.loc[gw2["GAME_ID"].eq("0022600017"), "PDK_OFFICIAL_VALID"].iloc[0])
    assert gw3["PDK_OFFICIAL_VALID"].tolist() == [34.0, 41.0]
    assert first.loc[0, "cr"] == 14.1
    assert second.loc[0, "cr"] == 14.5
    assert gw2.attrs["round_pdk_overlay"]["matched"] == 1
    assert gw3.attrs["round_pdk_overlay"]["matched"] == 2
