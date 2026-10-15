import pandas as pd

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


def test_team_specific_surname_only_out_never_removes_player_from_another_team():
    predictions = pd.DataFrame({
        "player_name": ["Jimmy Butler", "Healthy Player"],
        "team": ["GSW", "BOS"],
    })
    injuries = pd.DataFrame({"player_name": ["Butler"], "team": ["LAL"], "status": ["OUT"]})

    eligible = filter_injured(predictions, injuries)

    assert eligible["player_name"].tolist() == ["Jimmy Butler", "Healthy Player"]


def test_abbreviated_out_excludes_only_matching_initial_when_teammates_share_surname():
    predictions = pd.DataFrame({
        "player_name": ["Baba Miller", "Jordan Miller", "Brandon Miller", "Healthy Player"],
        "team": ["LAC", "LAC", "CHA", "BOS"],
    })
    injuries = pd.DataFrame({
        "player_name": ["J. Miller"], "team": ["LAC"], "status": ["OUT"],
    })

    eligible = filter_injured(predictions, injuries)

    assert eligible["player_name"].tolist() == [
        "Baba Miller", "Brandon Miller", "Healthy Player",
    ]


def test_official_full_name_out_does_not_remove_different_player_with_same_surname():
    predictions = pd.DataFrame({
        "player_name": ["Baba Miller", "Jordan Miller", "Healthy Player"],
        "team": ["LAC", "LAC", "BOS"],
    })
    injuries = pd.DataFrame({
        "player_name": ["Baba Miller"], "team": ["LAC"], "status": ["OUT"],
    })

    eligible = filter_injured(predictions, injuries)

    assert eligible["player_name"].tolist() == ["Jordan Miller", "Healthy Player"]


def test_official_dunkest_injury_page_is_authoritative_over_lineups_status(tmp_path, monkeypatch):
    (tmp_path / "current_lineups_market.csv").write_text(
        "player_name,team,status,dunkest_turn\n"
        "Lineups Only Out,NYK,OUT,1\n"
        "Official Player,BOS,AVAILABLE,1\n",
        encoding="utf-8",
    )
    (tmp_path / "lineups_availability.csv").write_text(
        "player_name,team,status,dunkest_turn\nLineups Only Out,NYK,OUT,1\n",
        encoding="utf-8",
    )
    settings = Settings(data_dir=str(tmp_path))
    settings.target_gameweek = 2
    settings.target_dunkest_turn = 1
    official = pd.DataFrame({
        "player_name": ["Official Player", "J. Butler"],
        "team": ["BOS", "GSW"],
        "status": ["AVAILABLE", "OUT"],
    })
    calls = []
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: False)
    monkeypatch.setattr(access.dk_module, "scrape_injuries", lambda *args, **kwargs: calls.append(True) or official.copy())

    injuries = access.get_injuries(settings)

    assert calls == [True]
    assert set(injuries["player_name"]) == {"Official Player", "J. Butler"}
    assert injuries.loc[injuries.player_name.eq("J. Butler"), "status"].item() == "OUT"
    assert "Lineups Only Out" not in set(injuries.player_name)
    metadata = access.read_cache_metadata(tmp_path / "processed" / "injuries.parquet")
    assert metadata["source"] == "dunkest_official_injuries_page"
    assert metadata["gameweek"] == 2


def test_official_injury_cache_is_scoped_to_same_gameweek(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path))
    settings.target_gameweek = 2
    cache_path = tmp_path / "processed" / "injuries.parquet"
    cache_path.parent.mkdir(parents=True)
    cache_path.touch()
    cached = pd.DataFrame({
        "player_name": ["Cached Official Out"], "team": ["NYK"], "status": ["OUT"],
    })
    monkeypatch.setattr(access, "read_cache_metadata", lambda path: {
        "source": "dunkest_official_injuries_page", "season_id": settings.season_id,
        "gameweek": 2,
    })
    monkeypatch.setattr(access, "read_parquet", lambda path: cached.copy())
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        access, "dk_module",
        type("Client", (), {"scrape_injuries": staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should use scoped cache")))})(),
    )

    injuries = access.get_injuries(settings)

    assert injuries.player_name.tolist() == ["Cached Official Out"]


def test_new_gameweek_refetches_injury_page_instead_of_reusing_previous_gameweek(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path))
    settings.target_gameweek = 3
    old = pd.DataFrame({"player_name": ["Old GW Out"], "team": ["CHI"], "status": ["OUT"]})
    current = pd.DataFrame({"player_name": ["Current GW Out"], "team": ["BOS"], "status": ["OUT"]})
    monkeypatch.setattr(access, "read_cache_metadata", lambda path: {
        "source": "dunkest_official_injuries_page", "season_id": settings.season_id,
        "gameweek": 2,
    })
    monkeypatch.setattr(access, "read_parquet", lambda path: old.copy())
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(access.dk_module, "scrape_injuries", lambda *args, **kwargs: current.copy())

    injuries = access.get_injuries(settings)

    assert injuries.player_name.tolist() == ["Current GW Out"]


def test_official_injury_scrape_failure_does_not_fall_back_to_lineups(tmp_path, monkeypatch):
    (tmp_path / "lineups_availability.csv").write_text(
        "player_name,team,status,dunkest_turn\nLineups Out,NYK,OUT,1\n",
        encoding="utf-8",
    )
    settings = Settings(data_dir=str(tmp_path))
    settings.target_gameweek = 4
    monkeypatch.setattr(access, "read_cache_metadata", lambda path: {})
    monkeypatch.setattr(access, "read_parquet", lambda path: None)
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        access.dk_module, "scrape_injuries",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("site unavailable")),
    )

    import pytest
    with pytest.raises(RuntimeError, match="non uso lo scraping Lineups come fallback"):
        access.get_injuries(settings)
