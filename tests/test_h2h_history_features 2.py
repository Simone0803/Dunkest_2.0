"""Regression tests for strict-time player-vs-opponent historical features."""
import importlib.util
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/backtest_dunkest_historical_credits_matchup_walk_forward_v4.py"
SPEC = importlib.util.spec_from_file_location("dunkest_h2h_v4", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _source_rows():
    return pd.DataFrame({
        "nba_NBA_GAME_DATE_PARSED": pd.to_datetime(["2024-01-01", "2024-01-05", "2024-01-10", "2024-01-10"]),
        "dunkest_player_name": ["Test Player"] * 4,
        "opponentTeamCode": ["BOS"] * 4,
        "pdk": [10.0, 20.0, 999.0, 30.0],
        "min": [20.0, 30.0, 48.0, 25.0],
        "gameValidForDunkest": [True, True, True, False],
    })


def test_h2h_features_exclude_target_day_and_invalid_pdk(tmp_path, monkeypatch):
    source = tmp_path / "history.parquet"
    _source_rows().to_parquet(source)
    monkeypatch.setattr(MODULE, "ENRICHED", source)
    d = pd.DataFrame({"target_date": pd.to_datetime(["2024-01-10"]),
        "player_key": ["testplayer"], "target_opponent": ["BOS"], "prev5_pdk_mean": [12.0]})
    result, audit = MODULE.attach_player_opponent_history(d)
    row = result.iloc[0]
    assert row["h2h_games_prev5"] == 2
    assert row["h2h_valid_pdk_games_prev5"] == 2
    assert row["h2h_pdk_mean_prev5"] == 15.0
    assert row["h2h_minutes_mean_prev5"] == 25.0
    assert row["h2h_pdk_mean_shrunk_prev5"] == 13.2
    assert audit["rows_with_prior_h2h_game"] == 1


def test_h2h_features_are_missing_when_no_prior_opponent_game(tmp_path, monkeypatch):
    source = tmp_path / "history.parquet"
    _source_rows().to_parquet(source)
    monkeypatch.setattr(MODULE, "ENRICHED", source)
    d = pd.DataFrame({"target_date": pd.to_datetime(["2023-12-31"]),
        "player_key": ["testplayer"], "target_opponent": ["BOS"], "prev5_pdk_mean": [12.0]})
    result, _ = MODULE.attach_player_opponent_history(d)
    row = result.iloc[0]
    assert row["h2h_games_prev5"] == 0
    assert pd.isna(row["h2h_pdk_mean_prev5"])
    assert row["h2h_pdk_mean_shrunk_prev5"] == 12.0


def test_h2h_lookup_does_not_mix_other_opponents(tmp_path, monkeypatch):
    source = tmp_path / "history.parquet"
    rows = _source_rows()
    rows.loc[0, "opponentTeamCode"] = "NYK"
    rows.to_parquet(source)
    monkeypatch.setattr(MODULE, "ENRICHED", source)
    d = pd.DataFrame({"target_date": pd.to_datetime(["2024-01-10"]),
        "player_key": ["testplayer"], "target_opponent": ["BOS"], "prev5_pdk_mean": [12.0]})
    result, _ = MODULE.attach_player_opponent_history(d)
    assert result.iloc[0]["h2h_pdk_mean_prev5"] == 20.0
    assert result.iloc[0]["h2h_games_prev5"] == 1
