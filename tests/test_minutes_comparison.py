import pandas as pd
import pytest

from dunkest.evaluation.minutes_comparison import (
    minutes_metrics,
    pair_minutes_forecasts,
    paired_game_bootstrap_delta,
)


def _forecasts():
    return pd.DataFrame(
        [
            {
                "player_id": "p2", "nba_game_id": "g2",
                "game_date": "2026-10-21T00:00:00Z",
                "forecast_at_utc": "2026-10-19T12:00:00Z",
                "feature_max_at_utc": "2026-10-19T11:00:00Z",
                "train_max_date": "2026-10-18T00:00:00Z",
                "minutes_hybrid": 20.0, "minutes_hgb": 22.0,
            },
            {
                "player_id": "p1", "nba_game_id": "g1",
                "game_date": "2026-10-20T00:00:00Z",
                "forecast_at_utc": "2026-10-19T12:00:00Z",
                "feature_max_at_utc": "2026-10-19T11:00:00Z",
                "train_max_date": "2026-10-18T00:00:00Z",
                "minutes_hybrid": 10.0, "minutes_hgb": 12.0,
            },
        ]
    )


def test_pairing_uses_identical_player_game_rows_and_sorts_chronologically():
    outcomes = pd.DataFrame(
        [
            {"player_id": "p1", "nba_game_id": "g1", "minutes_actual": 11.0},
            {"player_id": "other", "nba_game_id": "g1", "minutes_actual": 9.0},
            {"player_id": "p2", "nba_game_id": "g2", "minutes_actual": 21.0},
        ]
    )
    paired = pair_minutes_forecasts(_forecasts(), outcomes, keys=("player_id", "nba_game_id"))
    assert paired[["player_id", "nba_game_id"]].values.tolist() == [["p1", "g1"], ["p2", "g2"]]
    assert paired["minutes_actual"].tolist() == [11.0, 21.0]


@pytest.mark.parametrize(
    ("column", "bad_value", "message"),
    [
        ("feature_max_at_utc", "2026-10-19T13:00:00Z", "post-forecast"),
        ("forecast_at_utc", "2026-10-20T00:00:00Z", "not earlier"),
        ("train_max_date", "2026-10-19T12:00:00Z", "training data"),
    ],
)
def test_temporal_leakage_is_rejected(column, bad_value, message):
    forecasts = _forecasts()
    forecasts.loc[1, column] = bad_value
    outcomes = pd.DataFrame([{"player_id": "p2", "nba_game_id": "g2", "minutes_actual": 21.0}])
    with pytest.raises(ValueError, match=message):
        pair_minutes_forecasts(forecasts, outcomes, keys=("player_id", "nba_game_id"))


def test_duplicate_player_game_keys_fail_closed():
    forecasts = pd.concat([_forecasts(), _forecasts().iloc[[0]]], ignore_index=True)
    outcomes = pd.DataFrame([{"player_id": "p2", "nba_game_id": "g2", "minutes_actual": 21.0}])
    with pytest.raises(ValueError, match="duplicate forecast"):
        pair_minutes_forecasts(forecasts, outcomes, keys=("player_id", "nba_game_id"))


def test_minutes_metrics_and_game_cluster_bootstrap_are_paired_and_reproducible():
    assert minutes_metrics([10.0, 20.0], [12.0, 19.0]) == {
        "n": 2, "mae": 1.5, "rmse": 1.5811388300841898, "bias": 0.5,
    }
    frame = pd.DataFrame(
        [
            {"nba_game_id": "g1", "minutes_actual": 10.0, "minutes_hybrid": 9.0, "minutes_hgb": 11.0},
            {"nba_game_id": "g1", "minutes_actual": 20.0, "minutes_hybrid": 19.0, "minutes_hgb": 21.0},
            {"nba_game_id": "g2", "minutes_actual": 30.0, "minutes_hybrid": 29.0, "minutes_hgb": 31.0},
        ]
    )
    first = paired_game_bootstrap_delta(frame, n_bootstrap=100, seed=7)
    second = paired_game_bootstrap_delta(frame, n_bootstrap=100, seed=7)
    assert first == second
    assert first["mae"] == [0.0, 0.0]
    assert first["bias"] == [2.0, 2.0]
