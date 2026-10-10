import pandas as pd
import json

from dunkest.rules.eligibility import filter_injured
from dunkest.config import Settings
from dunkest.data import access


def test_injured_players_are_removed_but_questionable_stay_eligible():
    predictions = pd.DataFrame({"player_name": ["Out Player", "Questionable Player", "Healthy Player"]})
    injuries = pd.DataFrame({
        "player_name": ["Out Player", "Questionable Player"],
        "status": ["OUT", "Questionable"],
    })

    eligible = filter_injured(predictions, injuries)

    assert eligible["player_name"].tolist() == ["Questionable Player", "Healthy Player"]


def test_lineups_surname_only_out_row_removes_unique_player_even_when_column_team_is_wrong():
    predictions = pd.DataFrame({
        "player_name": ["Jimmy Butler", "Healthy Player"],
        "team": ["GSW", "BOS"],
    })
    injuries = pd.DataFrame({"player_name": ["Butler"], "team": ["LAL"], "status": ["OUT"]})

    eligible = filter_injured(predictions, injuries)

    assert eligible["player_name"].tolist() == ["Healthy Player"]


def test_fresh_lineups_status_replaces_stale_cached_injury_rows(tmp_path, monkeypatch):
    (tmp_path / "current_lineups_market.csv").write_text(
        "player_name,team,status\nAvailable Player,BOS,AVAILABLE\nOut Player,NYK,OUT\n",
        encoding="utf-8",
    )
    settings = Settings(data_dir=str(tmp_path))
    cached = pd.DataFrame({
        "player_name": ["Available Player", "Older Injury"],
        "team": ["BOS", "CHI"],
        "status": ["OUT", "OUT"],
    })
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(access, "read_parquet", lambda path: cached.copy())

    injuries = access.get_injuries(settings)

    assert set(injuries["player_name"]) == {"Out Player", "Older Injury"}


def test_complete_lineups_snapshot_drops_stale_cached_out_rows(tmp_path, monkeypatch):
    market_path = tmp_path / "current_lineups_market.csv"
    market_path.write_text(
        "player_name,team,status,dunkest_turn\n"
        "Healthy Player,BOS,AVAILABLE,1\n"
        "Current Out,NYK,OUT,1\n",
        encoding="utf-8",
    )
    (tmp_path / "current_lineups_market.csv.meta.json").write_text(json.dumps({
        "source": "dunkest_lineups_browser",
        "dunkest_turn": 1,
        "availability_snapshot_complete": True,
    }), encoding="utf-8")
    settings = Settings(data_dir=str(tmp_path))
    settings.target_dunkest_turn = 1
    cached = pd.DataFrame({
        "player_name": ["Healthy Player", "Old Turn Out"],
        "team": ["BOS", "CHI"], "status": ["OUT", "OUT"],
    })
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(access, "read_parquet", lambda path: cached.copy())

    injuries = access.get_injuries(settings)

    assert injuries[["player_name", "team", "status"]].to_dict("records") == [
        {"player_name": "Current Out", "team": "NYK", "status": "OUT"}
    ]


def test_authoritative_lineups_turn_snapshot_drops_stale_injury_cache(tmp_path, monkeypatch):
    (tmp_path / "current_lineups_market.csv").write_text(
        "player_name,team,status,dunkest_turn\nHealthy Player,BOS,AVAILABLE,2\n",
        encoding="utf-8",
    )
    (tmp_path / "lineups_availability.csv").write_text(
        "player_name,team,status,dunkest_turn\n"
        "Round One Out,NYK,OUT,1\n"
        "Round Two Out,CHI,OUT,2\n",
        encoding="utf-8",
    )
    settings = Settings(data_dir=str(tmp_path))
    settings.target_gameweek = 1
    settings.target_dunkest_turn = 2
    cached = pd.DataFrame({
        "player_name": ["Healthy Player", "Older Injury"],
        "team": ["BOS", "CHI"], "status": ["OUT", "OUT"],
    })
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(access, "read_parquet", lambda path: cached.copy())

    injuries = access.get_injuries(settings)

    assert set(injuries["player_name"]) == {"Round Two Out"}
