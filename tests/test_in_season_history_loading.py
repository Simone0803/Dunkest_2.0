import pandas as pd
import pytest

from dunkest.config import Settings
from dunkest.data import access
from dunkest.data.cache import read_cache_metadata, write_parquet
from dunkest.data.access import _merge_complete_player_log_update
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import predict_players
from dunkest.pipeline import train
from dunkest.pipeline.train import _player_feature_history
from dunkest.pipeline import train


def _logs(rows):
    frame = pd.DataFrame(rows, columns=[
        "PLAYER_ID", "PLAYER_NAME", "GAME_ID", "GAME_DATE",
        "TEAM_ABBREVIATION", "MATCHUP", "OPPONENT", "MIN", "PTS",
        "REB", "AST", "STL", "BLK", "TOV", "OREB", "DREB",
        "FGM", "FGA", "FTM", "FTA", "FG3M", "PDK",
    ])
    frame["GAME_DATE"] = pd.to_datetime(frame["GAME_DATE"], utc=True).dt.tz_convert(None)
    return frame


def _log(player_id, game_id, date, pdk, minutes, team="NYK"):
    return {
        "PLAYER_ID": player_id, "PLAYER_NAME": "Mitchell Robinson",
        "GAME_ID": game_id, "GAME_DATE": date,
        "TEAM_ABBREVIATION": team, "MATCHUP": f"{team} vs. BOS",
        "OPPONENT": "BOS", "MIN": minutes, "PTS": 8, "REB": 10,
        "AST": 1, "STL": 1, "BLK": 2, "TOV": 1, "OREB": 4,
        "DREB": 6, "FGM": 4, "FGA": 6, "FTM": 0, "FTA": 0,
        "FG3M": 0, "PDK": pdk,
    }


def test_prior_history_is_used_when_current_season_file_is_empty(tmp_path):
    settings = Settings(data_dir=str(tmp_path), target_gameweek=2)
    prior_path = tmp_path / "processed" / "player_game_logs_2025-26.parquet"
    prior = _logs([_log(1629011, "0022500001", "2025-10-25", 24, 20)])
    write_parquet(prior, prior_path, source="fixture", collection_complete=True)

    history = _player_feature_history(settings, pd.DataFrame())

    assert len(history) == 1
    assert history.loc[0, "PLAYER_NAME"] == "Mitchell Robinson"
    assert history.loc[0, "PDK"] == 24


def test_mitchell_robinson_history_reaches_predictor_across_seasons(tmp_path):
    settings = Settings(data_dir=str(tmp_path), target_gameweek=2, rolling_windows=[3])
    prior_path = tmp_path / "processed" / "player_game_logs_2025-26.parquet"
    prior = _logs([
        _log(1629011, "0022500001", "2025-10-25", 20, 20),
        _log(1629011, "0022500002", "2025-10-27", 40, 20),
    ])
    write_parquet(prior, prior_path, source="fixture", collection_complete=True)
    current = _logs([_log(1629011, "0022600001", "2026-10-22", 45, 30)])

    history = _player_feature_history(settings, current)
    schedule = pd.DataFrame([{
        "GAME_DATE": "2026-10-25", "HOME_TEAM": "NYK", "AWAY_TEAM": "BOS",
    }])
    features = build_feature_matrix(settings, history, schedule=schedule)
    inference = features.loc[features["is_inference"]]
    market = pd.DataFrame([{
        "player_name": "Mitchell Robinson", "team_code": "NYK", "position": "C",
        "role": "C", "cr": 6.5, "status": "AVAILABLE", "lineup_group": "",
    }])
    models = {"_feature_cols": [], "_weights": {}, "_residual_std": 1.0}

    prediction = predict_players(settings, models, inference, market).iloc[0]

    assert prediction["has_history"]
    assert prediction["current_season_games"] == 1
    assert prediction["pdk_per_min_current_season"] == pytest.approx(45 / 30)
    assert prediction["prior_seasons_games"] == 2
    assert prediction["pdk_per_min_prior_seasons"] == pytest.approx(60 / 40)
    assert prediction["history_games_before_target"] == 3
    assert prediction["history_source"] == "current_and_prior_season_game_logs"
    assert prediction["pdk_rate_for_projection"] == pytest.approx(1.5)
    assert prediction["projection_source"] == "current_season_shrunk"


def test_completed_game_updates_later_gameweek_rate_but_not_prior_cutoff():
    features = pd.DataFrame([{
        "PLAYER_NAME": "Mitchell Robinson", "is_inference": True,
        "NBA_GAME_DATETIME_UTC": pd.Timestamp("2026-10-28"),
    }])
    base = _logs([
        _log(1629011, "0022500001", "2025-10-25", 20, 20),
        _log(1629011, "0022500002", "2025-10-27", 40, 20),
    ])
    gw1 = _logs([_log(1629011, "0022600001", "2026-10-20", 30, 30)])
    gw2 = _logs([_log(1629011, "0022600002", "2026-10-22", 60, 30)])

    before_gw2 = build_feature_matrix(
        Settings(rolling_windows=[3]), pd.concat([base, gw1], ignore_index=True),
        schedule=pd.DataFrame([{"GAME_DATE": "2026-10-22", "HOME_TEAM": "NYK", "AWAY_TEAM": "BOS"}]),
    )
    before_gw3 = build_feature_matrix(
        Settings(rolling_windows=[3]), pd.concat([base, gw1, gw2], ignore_index=True),
        schedule=pd.DataFrame([{"GAME_DATE": "2026-10-28", "HOME_TEAM": "NYK", "AWAY_TEAM": "BOS"}]),
    )

    gw2_rate = before_gw2.loc[before_gw2["is_inference"], "pdk_per_min_current_season"].iloc[0]
    gw3_rate = before_gw3.loc[before_gw3["is_inference"], "pdk_per_min_current_season"].iloc[0]
    assert gw2_rate == pytest.approx(1.0)
    assert gw3_rate == pytest.approx(1.5)


def test_current_season_log_refresh_is_an_idempotent_upsert():
    previous = _logs([
        _log(1629011, "0022600001", "2026-10-20", 30, 30),
        _log(1629011, "0022600002", "2026-10-22", 60, 30),
    ])
    # A corrected complete refresh can update a row, add a new game, and omit
    # an older row without deleting the already saved history.
    fetched = _logs([
        _log(1629011, "0022600001", "2026-10-20", 31, 30),
        _log(1629011, "0022600003", "2026-10-24", 45, 30),
    ])

    merged, counts = _merge_complete_player_log_update(previous, fetched)
    repeated, repeated_counts = _merge_complete_player_log_update(merged, fetched)

    assert len(merged) == 3
    assert counts == {"fetched": 2, "added": 1, "refreshed": 1, "retained": 1}
    assert merged.set_index("GAME_ID").loc["0022600001", "PDK"] == 31
    assert repeated["GAME_ID"].is_unique
    assert len(repeated) == len(merged)
    assert repeated_counts["added"] == 0
    assert repeated_counts["refreshed"] == 2


def test_complete_refresh_persists_new_games_and_retains_older_ones(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=True)
    path = tmp_path / "processed" / f"player_game_logs_{settings.season}.parquet"
    old = _logs([_log(1, "G1", "2026-10-20", 30, 30)])
    old["data_source"] = "nba_api/playergamelog"
    write_parquet(
        old, path, source="nba_api/playergamelog", season=settings.season,
        collection_complete=True,
    )
    monkeypatch.setattr(access, "cache_valid", lambda *a, **k: False)
    monkeypatch.setattr(
        access.dk_module, "fetch_nba_season_players",
        lambda *_: pd.DataFrame([{"player_name": "Mitchell Robinson", "cr": 6.5, "pdk": 30}]),
    )

    def fetch(*_args, **_kwargs):
        result = _logs([_log(1, "G2", "2026-10-22", 45, 30)])
        result.attrs["collection_report"] = {
            "collection_complete": True, "expected_entities": 1,
            "attempted_entities": 1, "failed_entities": 0,
            "truncated_entities": 0,
        }
        return result

    monkeypatch.setattr(access.nba, "fetch_player_game_logs", fetch)

    updated = access.get_player_data(settings, force_refresh=True)

    assert set(updated["GAME_ID"]) == {"G1", "G2"}
    assert len(updated) == 2
    metadata = read_cache_metadata(path)
    assert metadata["collection_complete"] is True
    assert metadata["rows"] == 2


def test_gw2_refresh_failure_uses_only_recent_complete_real_nba_cache(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season="2026-27", target_gameweek=2)
    path = tmp_path / "processed" / "player_game_logs_2026-27.parquet"
    logs = _logs([_log(1629011, "0022600001", "2026-10-20", 30, 30)])
    logs["data_source"] = "nba_api/playergamelog"
    write_parquet(
        logs,
        path,
        source="nba_api/playergamelog",
        season="2026-27",
        collection_complete=True,
    )
    monkeypatch.setattr(
        train,
        "get_player_data",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("DNS unavailable")),
    )

    cached = train._current_player_logs_for_gameweek(settings)

    assert cached["GAME_ID"].tolist() == ["0022600001"]
    assert cached["data_source"].eq("nba_api/playergamelog").all()


def test_refresh_failure_rejects_incomplete_or_synthetic_log_cache(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), season="2026-27", target_gameweek=2)
    path = tmp_path / "processed" / "player_game_logs_2026-27.parquet"
    monkeypatch.setattr(
        train,
        "get_player_data",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("DNS unavailable")),
    )
    logs = _logs([_log(1629011, "0022600001", "2026-10-20", 30, 30)])
    for source, complete in (("nba_api/playergamelog", False), ("synthetic_dunkest_market", True)):
        write_parquet(
            logs,
            path,
            source=source,
            season="2026-27",
            collection_complete=complete,
        )
        with pytest.raises(RuntimeError, match="DNS unavailable"):
            train._current_player_logs_for_gameweek(settings)


def test_complete_empty_refresh_does_not_erase_saved_games(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path), use_nba_api_logs=True)
    path = tmp_path / "processed" / f"player_game_logs_{settings.season}.parquet"
    old = _logs([_log(1, "G1", "2026-10-20", 30, 30)])
    old["data_source"] = "nba_api/playergamelog"
    write_parquet(
        old, path, source="nba_api/playergamelog", season=settings.season,
        collection_complete=True,
    )
    monkeypatch.setattr(access, "cache_valid", lambda *a, **k: False)
    monkeypatch.setattr(
        access.dk_module, "fetch_nba_season_players",
        lambda *_: pd.DataFrame([{"player_name": "Mitchell Robinson", "cr": 6.5, "pdk": 30}]),
    )

    def fetch(*_args, **_kwargs):
        result = pd.DataFrame()
        result.attrs["collection_report"] = {
            "collection_complete": True, "expected_entities": 1,
            "attempted_entities": 1, "failed_entities": 0,
            "truncated_entities": 0, "unmatched_requested_count": 0,
        }
        return result

    monkeypatch.setattr(access.nba, "fetch_player_game_logs", fetch)

    updated = access.get_player_data(settings, force_refresh=True)

    assert updated["GAME_ID"].tolist() == ["G1"]
    assert updated["PDK"].tolist() == [30]


def test_post_opener_training_forces_current_season_refresh(monkeypatch):
    calls = []

    def fake_get_player_data(settings, *, force_refresh=False):
        calls.append((settings.target_gameweek, force_refresh))
        return pd.DataFrame()

    monkeypatch.setattr(train, "get_player_data", fake_get_player_data)

    train._current_player_logs_for_gameweek(Settings(target_gameweek=1))
    train._current_player_logs_for_gameweek(Settings(target_gameweek=2))

    assert calls == [(1, False), (2, True)]

