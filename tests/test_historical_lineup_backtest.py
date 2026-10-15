import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backtest_dunkest_historical_lineups_lagged_market_v5",
    ROOT / "scripts" / "backtest_dunkest_historical_lineups_lagged_market_v5.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_latest_prior_candidates_carries_forward_last_known_credit_without_future_rows():
    rows = pd.DataFrame([
        {"season_id": "9", "player_key": "playera", "player_name": "Player A", "round_index": 1, "cr": 10.0, "target_pdk_round_total": 12.0},
        {"season_id": "9", "player_key": "playerb", "player_name": "Player B", "round_index": 2, "cr": 8.0, "target_pdk_round_total": 9.0},
        {"season_id": "9", "player_key": "playera", "player_name": "Player A", "round_index": 3, "cr": 11.0, "target_pdk_round_total": 18.0},
        {"season_id": "9", "player_key": "playerc", "player_name": "Player C", "round_index": 4, "cr": 20.0, "target_pdk_round_total": 50.0},
    ])

    candidates = module.latest_prior_candidates(rows, target_round=4).set_index("player_key")

    assert set(candidates.index) == {"playera", "playerb"}
    assert candidates.loc["playera", "round_index"] == 3
    assert candidates.loc["playera", "cr"] == 11.0
    assert candidates.loc["playera", "credit_age_rounds"] == 1
    assert candidates.loc["playera", "prior_round_present"] == 1
    assert candidates.loc["playerb", "round_index"] == 2
    assert candidates.loc["playerb", "cr"] == 8.0
    assert candidates.loc["playerb", "credit_age_rounds"] == 2
    assert candidates.loc["playerb", "prior_round_present"] == 0
    assert (candidates["round_index"] < 4).all()
