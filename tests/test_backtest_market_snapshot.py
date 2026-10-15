import pandas as pd
import pytest

from dunkest.backtest.walk_forward import (
    MIN_HISTORICAL_MARKET_PLAYERS,
    _historical_candidate_pool,
    _load_historical_market_snapshot,
)


def _market_snapshot(gameweek=3, rows=MIN_HISTORICAL_MARKET_PLAYERS):
    return pd.DataFrame(
        {
            "player_name": [f"Player {index}" for index in range(rows)],
            "team_code": [f"T{index % 30}" for index in range(rows)],
            "role": [("G", "F", "C")[index % 3] for index in range(rows)],
            "cr": [8.0] * rows,
            "gameweek": [gameweek] * rows,
            "lineup_group": ["PANCHINA"] * rows,
            "status": ["AVAILABLE"] * rows,
        }
    )


def test_backtest_rejects_missing_historical_market_snapshot(tmp_path):
    path = tmp_path / "player_credits_gw3.parquet"

    with pytest.raises(ValueError, match="GW3: snapshot listino mancante"):
        _load_historical_market_snapshot(path, gameweek=3)


@pytest.mark.parametrize(
    ("rows", "gameweek", "expected_message"),
    [
        (MIN_HISTORICAL_MARKET_PLAYERS - 1, 3, "incompleto o non valido"),
        (MIN_HISTORICAL_MARKET_PLAYERS, 2, "incompleto o non valido"),
    ],
)
def test_backtest_rejects_incomplete_or_wrong_gameweek_market(
    tmp_path, rows, gameweek, expected_message
):
    path = tmp_path / "player_credits_gw3.parquet"
    _market_snapshot(gameweek=gameweek, rows=rows).to_parquet(path, index=False)

    with pytest.raises(ValueError, match=expected_message):
        _load_historical_market_snapshot(path, gameweek=3)


def test_backtest_candidate_pool_preserves_archived_market_even_when_results_are_sparse(tmp_path):
    path = tmp_path / "player_credits_gw3.parquet"
    archived = _market_snapshot()
    # Outcome payloads are not trusted as the candidate universe; the frozen
    # market can include eligible players absent from the season-stat table.
    archived["actual_pdk"] = float("nan")
    archived["pdk"] = 99.0
    archived.to_parquet(path, index=False)
    snapshot = _load_historical_market_snapshot(path, gameweek=3)

    result = _historical_candidate_pool(snapshot)

    assert len(result) == MIN_HISTORICAL_MARKET_PLAYERS
    assert result["player_name"].tolist() == archived["player_name"].tolist()
    assert result["team_code"].tolist() == archived["team_code"].tolist()
    assert result["role"].tolist() == archived["role"].tolist()
    assert result["position"].tolist() == archived["role"].tolist()
    assert result["cr"].eq(8.0).all()
    assert result["lineup_group"].eq("PANCHINA").all()
    assert result["status"].eq("AVAILABLE").all()
    assert "actual_pdk" not in result
    assert "pdk" not in result


def test_backtest_candidate_pool_requires_frozen_market_identity_columns():
    with pytest.raises(ValueError, match="snapshot mercato senza colonne"):
        _historical_candidate_pool(pd.DataFrame({"player_name": ["Player"]}))
