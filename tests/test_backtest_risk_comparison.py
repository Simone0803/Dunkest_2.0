import pandas as pd

from dunkest.backtest.walk_forward import _compare_risk_objectives
from dunkest.config import Settings
from dunkest.names import player_key
from dunkest.optimize.milp import LineupSolution


def _solution():
    players = pd.DataFrame(
        {
            "player_name": [f"Player {index}" for index in range(10)],
            "slot": [
                "Captain", "Starter", "Starter", "Starter", "Starter",
                "Sixth Man", "Bench", "Bench", "Bench", "Bench",
            ],
        }
    )
    return LineupSolution(
        rank=1,
        expected_team_pdk=100.0,
        expected_player_pdk=95.0,
        expected_coach_pdk=5.0,
        budget_used=90.0,
        captain="Player 0",
        coach="Coach A",
        module="2-2-1",
        num_transfers=0,
        players=players,
        meta={"solver": {"status": "Optimal", "solve_time_seconds": 0.01}},
    )


def test_risk_comparison_sweeps_expected_value_and_configured_lambdas(monkeypatch):
    settings = Settings(
        optimizer_risk_lambda_grid=[0.05, 0.15, 0.30],
        transfer_penalty=5.0,
    )
    called = []

    def fake_optimize(_players, _coaches, trial, k):
        called.append((trial.optimizer_objective, trial.risk_lambda, k))
        return [_solution()]

    monkeypatch.setattr(
        "dunkest.backtest.walk_forward.optimize_top_k_lineups", fake_optimize
    )
    actuals = {player_key(f"Player {index}"): float(index + 10) for index in range(10)}

    rows = _compare_risk_objectives(
        pd.DataFrame(), pd.DataFrame(), settings, actuals, gameweek=12
    )

    assert called == [
        ("expected_value", settings.risk_lambda, 1),
        ("risk_adjusted", 0.05, 1),
        ("risk_adjusted", 0.15, 1),
        ("risk_adjusted", 0.30, 1),
    ]
    assert len(rows) == 4
    assert [row["risk_lambda"] for row in rows] == [None, 0.05, 0.15, 0.30]
    assert all(row["gameweek"] == 12 for row in rows)
    assert all(row["player_actuals_complete"] for row in rows)
    assert all(row["solver_status"] == "Optimal" for row in rows)


def test_risk_comparison_skips_weeks_without_realized_player_scores(monkeypatch):
    def unexpected_solve(*_args, **_kwargs):
        raise AssertionError("No outcomes should not trigger optimizer comparisons")

    monkeypatch.setattr(
        "dunkest.backtest.walk_forward.optimize_top_k_lineups", unexpected_solve
    )

    rows = _compare_risk_objectives(
        pd.DataFrame(), pd.DataFrame(), Settings(), {}, gameweek=12
    )

    assert rows == []