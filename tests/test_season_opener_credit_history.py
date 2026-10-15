import pandas as pd
import pytest
import warnings

from dunkest.config import Settings
from dunkest.pipeline.season_opener import (
    _build_opening_market_value_history, _load_opening_credit_history,
)


def _history():
    return pd.DataFrame({
        "player_name": ["Example Player"],
        "pdk": [12.5],
        "min": [24.0],
        "cr": [7.0],
    })


def test_opening_credit_history_prefers_season_qualified_file(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _history().assign(pdk=15.0).to_parquet(
        processed / "dunkest_players_25_gw35.parquet", index=False
    )
    _history().assign(pdk=9.0).to_parquet(
        processed / "dunkest_players_gw35.parquet", index=False
    )
    settings = Settings(data_dir=str(tmp_path), opening_prior_season_id="25")

    result = _load_opening_credit_history(settings)

    assert result.loc[0, "pdk"] == 15.0


def test_opening_credit_history_falls_back_to_valid_legacy_file(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _history().to_parquet(processed / "dunkest_players_gw35.parquet", index=False)
    settings = Settings(data_dir=str(tmp_path), opening_prior_season_id="25")

    with pytest.warns(RuntimeWarning, match="legacy"):
        result = _load_opening_credit_history(settings)

    assert result.loc[0, "player_name"] == "Example Player"
    assert result.loc[0, "pdk"] == 12.5


def test_opening_credit_history_ignores_invalid_legacy_file(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame({"player_name": ["Example Player"], "pdk": [0.0], "min": [0.0], "cr": [4.0]}).to_parquet(
        processed / "dunkest_players_gw35.parquet", index=False
    )
    settings = Settings(data_dir=str(tmp_path), opening_prior_season_id="25")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _load_opening_credit_history(settings)

    assert len(caught) == 2
    assert "nessuna riga" in str(caught[0].message)
    assert result.empty


def test_market_value_prior_uses_season_means_not_single_gameweek_scores():
    logs = pd.DataFrame({
        "PLAYER_NAME": ["Veteran Player"] * 5 + ["Rookie Player"] * 3,
        "MIN": [20.0, 22.0, 18.0, 21.0, 19.0, 10.0, 20.0, 30.0],
        "PDK": [11.0, 21.0, 31.0, 41.0, 51.0, 7.0, 9.0, 11.0],
        "PDK_OFFICIAL_VALID": [10.0, 20.0, 30.0, 40.0, 50.0, float("nan"), 8.0, float("nan")],
    })
    market = pd.DataFrame({
        "player_name": ["Veteran Player", "Rookie Player"],
        "cr": [12.5, 4.0],
        "role": ["G", "A"],
    })

    result = _build_opening_market_value_history(logs, market).set_index("player_name")

    assert result.loc["Veteran Player", "pdk"] == 30.0
    assert result.loc["Veteran Player", "min"] == 20.0
    assert result.loc["Veteran Player", "gp"] == 5
    assert result.loc["Veteran Player", "cr"] == 12.5
    assert result.loc["Veteran Player", "pdk_reference_source"] == "official_dunkest_pdk_mean"
    assert result.loc["Rookie Player", "pdk"] == 9.0
    assert result.loc["Rookie Player", "min"] == 20.0
    assert result.loc["Rookie Player", "gp"] == 3
    assert result.loc["Rookie Player", "role"] == "F"
    assert result.loc["Rookie Player", "pdk_reference_source"] == "nba_boxscore_proxy_mean"


def test_market_value_prior_is_empty_when_historical_game_logs_are_unavailable():
    result = _build_opening_market_value_history(
        pd.DataFrame(),
        pd.DataFrame({"player_name": ["Current Player"], "cr": [8.0], "role": ["G"]}),
    )

    assert result.empty
    assert {"player_name", "pdk", "min", "cr", "gp", "role"}.issubset(result.columns)
