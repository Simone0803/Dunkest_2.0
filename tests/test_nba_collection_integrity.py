import json

import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.data import access
from dunkest.data.nba import collector


def _game_log():
    return pd.DataFrame(
        [{
            "GAME_DATE": "2026-01-01",
            "MIN": "20:00",
            "PTS": 10,
            "REB": 3,
            "AST": 2,
            "STL": 1,
            "BLK": 0,
            "BLKA": 0,
            "TOV": 1,
            "FGM": 4,
            "FGA": 9,
            "FG3M": 1,
            "FG3A": 3,
            "FTM": 1,
            "FTA": 2,
            "OREB": 0,
            "DREB": 3,
            "PF": 2,
            "MATCHUP": "BOS vs. NYK",
            "WL": "W",
        }]
    )


def _install_fake_player_api(monkeypatch, failures=()):
    from nba_api.stats.endpoints import playergamelogs
    from nba_api.stats.static import players

    active_players = [
        {"id": 1, "full_name": "Player One"},
        {"id": 2, "full_name": "Player Two"},
    ]
    monkeypatch.setattr(players, "get_active_players", lambda: active_players)
    calls = {"bulk": 0}

    class FakePlayerGameLogs:
        def __init__(self, **_kwargs):
            calls["bulk"] += 1
            if failures:
                raise RuntimeError("simulated timeout")

        def get_data_frames(self):
            rows = []
            for player in active_players:
                for row in _game_log().to_dict("records"):
                    rows.append({**row, "PLAYER_ID": player["id"], "PLAYER_NAME": player["full_name"]})
            return [pd.DataFrame(rows)]

    monkeypatch.setattr(playergamelogs, "PlayerGameLogs", FakePlayerGameLogs)
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)
    return calls


def test_player_collection_reports_failed_entities_after_bounded_retries(monkeypatch):
    calls = _install_fake_player_api(monkeypatch, failures={"bulk"})

    with pytest.warns(RuntimeWarning, match="1/2 failed"):
        result = collector.fetch_player_game_logs(
            Settings(max_player_log_entries=0), player_names=["Player One", "Player Two"]
        )

    report = result.attrs["collection_report"]
    assert report["collection_complete"] is False
    assert report["expected_entities"] == 2
    assert report["attempted_entities"] == 2
    assert report["failed_entities"] == 1
    assert report["failed_entity_names"] == ["NBA PlayerGameLogs endpoint"]
    assert calls["bulk"] == 3


def test_player_limit_marks_truncated_collection_incomplete(monkeypatch):
    _install_fake_player_api(monkeypatch)

    with pytest.warns(RuntimeWarning, match="1 omitted by limit"):
        result = collector.fetch_player_game_logs(
            Settings(max_player_log_entries=1), player_names=["Player One", "Player Two"]
        )

    report = result.attrs["collection_report"]
    assert report["collection_complete"] is False
    assert report["expected_entities"] == 2
    assert report["attempted_entities"] == 1
    assert report["truncated_entities"] == 1


def test_player_collection_normalizes_requested_names_and_reports_unmatched(monkeypatch):
    _install_fake_player_api(monkeypatch)
    with pytest.warns(RuntimeWarning, match="did not match these requested Dunkest names"):
        result = collector.fetch_player_game_logs(
            Settings(max_player_log_entries=0),
            player_names=["Player One Jr.", "Unmatched Dunkest Name"],
        )

    report = result.attrs["collection_report"]
    assert set(result["PLAYER_NAME"]) == {"Player One"}
    assert report["unmatched_requested_players"] == ["Unmatched Dunkest Name"]


def test_prior_season_fallback_reports_partial_player_logs(monkeypatch):
    from nba_api.stats.endpoints import playergamelog, playergamelogs
    from nba_api.stats.static import players

    from dunkest.data.nba import prior_season

    monkeypatch.setattr(
        playergamelogs,
        "PlayerGameLogs",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("league endpoint unavailable")),
    )
    monkeypatch.setattr(
        players,
        "get_players",
        lambda: [
            {"id": 1, "full_name": "Player One"},
            {"id": 2, "full_name": "Player Two"},
        ],
    )
    calls = {1: 0, 2: 0}

    class FakePlayerGameLog:
        def __init__(self, player_id, **_kwargs):
            calls[player_id] += 1
            if player_id == 2:
                raise RuntimeError("simulated timeout")

        def get_data_frames(self):
            return [_game_log()]

    monkeypatch.setattr(playergamelog, "PlayerGameLog", FakePlayerGameLog)
    monkeypatch.setattr(prior_season.time, "sleep", lambda _seconds: None)

    with pytest.warns(RuntimeWarning, match="1/2 failed"):
        result = prior_season.fetch_prior_season_game_logs(Settings())

    report = result.attrs["collection_report"]
    assert report["collection_complete"] is False
    assert report["failed_entities"] == 1
    assert report["failed_entity_names"] == ["Player Two"]
    assert calls[2] == 3


def test_team_collection_reports_failed_entities_after_bounded_retries(monkeypatch):
    from nba_api.stats.endpoints import teamgamelog
    from nba_api.stats.static import teams

    monkeypatch.setattr(
        teams,
        "get_teams",
        lambda: [
            {"id": 1, "abbreviation": "BOS"},
            {"id": 2, "abbreviation": "NYK"},
        ],
    )
    calls = {1: 0, 2: 0}

    class FakeTeamGameLog:
        def __init__(self, team_id, **_kwargs):
            calls[team_id] += 1
            if team_id == 2:
                raise RuntimeError("simulated timeout")

        def get_data_frames(self):
            return [pd.DataFrame([{"GAME_DATE": "2026-01-01"}])]

    monkeypatch.setattr(teamgamelog, "TeamGameLog", FakeTeamGameLog)
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)

    with pytest.warns(RuntimeWarning, match="1/2 failed"):
        result = collector.fetch_team_game_logs(Settings())

    report = result.attrs["collection_report"]
    assert report["collection_complete"] is False
    assert report["expected_entities"] == 2
    assert report["failed_entities"] == 1
    assert report["failed_entity_names"] == ["NYK"]
    assert calls[2] == 3


def test_incomplete_player_collection_is_not_cached(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=True, allow_synthetic_logs=False)
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        access.dk_module,
        "fetch_nba_season_players",
        lambda _settings: pd.DataFrame(
            [{"player_name": "Player One", "cr": 8.0, "pdk": 10.0}]
        ),
    )
    incomplete = pd.DataFrame([{"PLAYER_NAME": "Player One"}])
    incomplete.attrs["collection_report"] = {
        "collection_complete": False,
        "expected_entities": 2,
        "attempted_entities": 2,
        "failed_entities": 1,
        "truncated_entities": 0,
    }
    monkeypatch.setattr(access.nba, "fetch_player_game_logs", lambda *args, **kwargs: incomplete)
    writes = []
    monkeypatch.setattr(access, "write_parquet", lambda *args, **kwargs: writes.append(args))

    with pytest.raises(RuntimeError, match="Log NBA reali completi non disponibili"):
        access.get_player_data(settings)

    assert writes == []


def test_complete_empty_current_season_collection_is_saved_without_synthetic_rows(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=True, allow_synthetic_logs=False)
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        access.dk_module,
        "fetch_nba_season_players",
        lambda _settings: pd.DataFrame([{"player_name": "Player One", "cr": 8.0, "pdk": 10.0}]),
    )
    empty = pd.DataFrame()
    empty.attrs["collection_report"] = {
        "collection_complete": True,
        "expected_entities": 1,
        "attempted_entities": 1,
        "failed_entities": 0,
        "truncated_entities": 0,
        "unmatched_requested_count": 0,
    }
    monkeypatch.setattr(access.nba, "fetch_player_game_logs", lambda *args, **kwargs: empty)
    writes = []
    monkeypatch.setattr(access, "write_parquet", lambda frame, path, **kwargs: writes.append((frame, kwargs)))

    result = access.get_player_data(settings, force_refresh=True)

    assert result.empty
    assert writes and writes[0][1]["source"] == "nba_api/playergamelog"
    assert writes[0][1]["collection_complete"] is True


def test_complete_collection_with_unmatched_market_player_keeps_real_logs_and_reports_gap(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=True, allow_synthetic_logs=False)
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        access.dk_module,
        "fetch_nba_season_players",
        lambda _settings: pd.DataFrame([
            {"player_name": "Player One", "cr": 8.0, "pdk": 10.0},
            {"player_name": "Rookie Name", "cr": 6.0, "pdk": float("nan")},
        ]),
    )
    result = pd.DataFrame([{"PLAYER_NAME": "Player One", "GAME_ID": "game-1", "PLAYER_ID": 1}])
    result.attrs["collection_report"] = {
        "collection_complete": True,
        "expected_entities": 1,
        "attempted_entities": 1,
        "failed_entities": 0,
        "truncated_entities": 0,
        "unmatched_requested_count": 1,
    }
    monkeypatch.setattr(access.nba, "fetch_player_game_logs", lambda *args, **kwargs: result)
    writes = []
    monkeypatch.setattr(access, "write_parquet", lambda frame, path, **kwargs: writes.append((frame, kwargs)))

    collected = access.get_player_data(settings, force_refresh=True)

    assert collected["PLAYER_NAME"].tolist() == ["Player One"]
    assert "Rookie Name" not in set(collected["PLAYER_NAME"])
    assert collected["data_source"].eq("nba_api/playergamelog").all()
    assert len(writes) == 1
    assert writes[0][1]["collection_complete"] is True
    assert writes[0][1]["unmatched_requested_count"] == 1


def test_complete_empty_collection_with_unmatched_market_players_is_not_synthesized(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=True, allow_synthetic_logs=False)
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        access.dk_module,
        "fetch_nba_season_players",
        lambda _settings: pd.DataFrame([
            {"player_name": "Player One", "cr": 8.0, "pdk": 10.0},
            {"player_name": "Rookie Name", "cr": 6.0, "pdk": float("nan")},
        ]),
    )
    empty = pd.DataFrame()
    empty.attrs["collection_report"] = {
        "collection_complete": True, "expected_entities": 1, "attempted_entities": 1,
        "failed_entities": 0, "truncated_entities": 0,
        "unmatched_requested_count": 1,
    }
    monkeypatch.setattr(access.nba, "fetch_player_game_logs", lambda *args, **kwargs: empty)
    writes = []
    monkeypatch.setattr(access, "write_parquet", lambda frame, path, **kwargs: writes.append((frame, kwargs)))

    result = access.get_player_data(settings, force_refresh=True)

    assert result.empty
    assert writes and writes[0][1]["source"] == "nba_api/playergamelog"
    assert writes[0][1]["collection_complete"] is True
    assert writes[0][1]["unmatched_requested_count"] == 1


def test_team_collection_failure_is_not_cached(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=True)
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: False)
    incomplete = pd.DataFrame([{"TEAM_ABBREVIATION": "BOS"}])
    incomplete.attrs["collection_report"] = {
        "collection_complete": False,
        "expected_entities": 30,
        "attempted_entities": 30,
        "failed_entities": 1,
        "truncated_entities": 0,
    }
    monkeypatch.setattr(access.nba, "fetch_team_game_logs", lambda *_args: incomplete)
    writes = []
    monkeypatch.setattr(access, "write_parquet", lambda *args, **kwargs: writes.append(args))

    with pytest.raises(RuntimeError, match="team game-log collection is incomplete"):
        access.get_team_data(settings)

    assert writes == []


def test_unverified_legacy_player_cache_is_refetched(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=True)
    cache_path = tmp_path / "processed" / f"player_game_logs_{settings.season}.parquet"
    metadata_path = cache_path.with_suffix(cache_path.suffix + ".meta.json")
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps({"source": "nba_api/playergamelog", "fetched_at": "2026-10-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(access, "cache_valid", lambda *args, **kwargs: True)
    cache_reads = []
    monkeypatch.setattr(
        access, "read_parquet", lambda path: cache_reads.append(path) or pd.DataFrame()
    )
    monkeypatch.setattr(
        access.dk_module,
        "fetch_nba_season_players",
        lambda _settings: pd.DataFrame(
            [{"player_name": "Player One", "cr": 8.0, "pdk": 10.0}]
        ),
    )
    complete = pd.DataFrame([{"PLAYER_NAME": "Player One"}])
    complete.attrs["collection_report"] = {
        "collection_complete": True,
        "expected_entities": 1,
        "attempted_entities": 1,
        "failed_entities": 0,
        "truncated_entities": 0,
    }
    monkeypatch.setattr(access.nba, "fetch_player_game_logs", lambda *args, **kwargs: complete)
    monkeypatch.setattr(access, "write_parquet", lambda *args, **kwargs: None)

    result = access.get_player_data(settings)

    assert cache_reads == []
    assert result["data_source"].eq("nba_api/playergamelog").all()
