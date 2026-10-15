from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"test_module_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "script_name",
    [
        "backtest_dunkest_historical_lineups_lagged_market_v6.py",
        "backtest_dunkest_historical_lineups_sequential_transfer_v3.py",
    ],
)
def test_strict_lineup_score_does_not_impute_missing_player_actuals_as_zero(script_name):
    module = load_script(script_name)
    solution = SimpleNamespace(
        players=pd.DataFrame(
            [
                {"player_name": "Player One", "slot": "Starter"},
                {"player_name": "Player Two", "slot": "Bench"},
            ]
        ),
        meta={"selected_coach_team": "BOS"},
        coach="Proxy Coach BOS",
    )

    player_score, coach_score, team_score = module.score_lineup(
        solution,
        {"player one": 20.0},
        {"BOS": 15.0},
    )

    assert np.isnan(player_score)
    assert np.isnan(coach_score)
    assert np.isnan(team_score)


@pytest.mark.parametrize(
    "script_name",
    [
        "backtest_dunkest_historical_lineups_lagged_market_v6.py",
        "backtest_dunkest_historical_lineups_sequential_transfer_v3.py",
    ],
)
def test_strict_lineup_score_returns_score_when_all_actuals_are_observed(script_name):
    module = load_script(script_name)
    solution = SimpleNamespace(
        players=pd.DataFrame(
            [
                {"player_name": "Player One", "slot": "Starter"},
                {"player_name": "Player Two", "slot": "Bench"},
            ]
        ),
        meta={"selected_coach_team": "BOS"},
        coach="Proxy Coach BOS",
    )

    player_score, coach_score, team_score = module.score_lineup(
        solution,
        {"player one": 20.0, "player two": 10.0},
        {"BOS": 15.0},
    )

    assert player_score == pytest.approx(25.0)
    assert coach_score == pytest.approx(15.0)
    assert team_score == pytest.approx(40.0)
