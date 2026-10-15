from io import StringIO

import pandas as pd
from rich.console import Console

from dunkest.config import Settings
from dunkest.optimize.milp import LineupSolution
from dunkest.report.console import print_matchday_report
from dunkest.report.season_opener import print_season_opener_report
from dunkest.report.terminal import print_dataframe


def _console_output() -> tuple[Console, StringIO]:
    output = StringIO()
    return Console(file=output, force_terminal=False, width=120), output


def _predictions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_name": "Player One",
                "team": "BOS",
                "role": "G",
                "opponent": "NYK",
                "cr": 10.0,
                "prior_pdk": 18.0,
                "expected_min": 30.0,
                "expected_pdk": 20.0,
                "p10": 12.0,
                "p50": 20.0,
                "p90": 28.0,
                "projection_source": "player_history",
                "status": "Available",
                "expected_plusvalenza": 0.24,
                "official_plusvalenza": 0.18,
                "plusvalenza_cv_mae": 0.08,
            },
            {
                "player_name": "Player Two",
                "team": "NYK",
                "role": "F",
                "opponent": "BOS",
                "cr": 8.0,
                "prior_pdk": 12.0,
                "expected_min": 24.0,
                "expected_pdk": 15.0,
                "p10": 9.0,
                "p50": 15.0,
                "p90": 21.0,
                "projection_source": "player_history",
                "status": "Available",
                "expected_plusvalenza": -0.02,
                "official_plusvalenza": -0.04,
                "plusvalenza_cv_mae": 0.08,
            },
        ]
    )


def _solution() -> LineupSolution:
    players = pd.DataFrame(
        [
            {
                "player_name": f"Player {index}",
                "team": f"T{index % 5}",
                "role": ("G", "F", "C")[index % 3],
                "cr": 8.0,
                "expected_min": 24.0,
                "expected_pdk": 15.0,
                "status": "Available",
                "slot": "Captain" if index == 0 else "Bench",
            }
            for index in range(10)
        ]
    )
    return LineupSolution(
        rank=1,
        expected_team_pdk=120.0,
        expected_player_pdk=110.0,
        expected_coach_pdk=10.0,
        budget_used=90.0,
        captain="Player 0",
        coach="Coach A",
        module="2-2-1",
        num_transfers=0,
        players=players,
        p10_team=80.0,
        p50_team=120.0,
        p90_team=160.0,
        meta={
            "solver": {
                "solver": "CBC",
                "status": "Optimal",
                "solve_time_seconds": 0.012,
            }
        },
    )


def test_matchday_report_uses_readable_rich_sections():
    console, output = _console_output()
    second_solution = _solution()
    second_solution.rank = 2

    print_matchday_report(
        Settings(),
        _predictions(),
        pd.DataFrame([{
            "coach": "Coach A", "team": "BOS", "opponent": "NYK",
            "coach_cr": 8.0, "expected_coach_pdk": 12.0,
            "expected_team_pts": 116.0, "expected_opp_pts": 109.0,
            "net_roster_strength_adjustment": 4.5,
            "matchup_projection_available": True,
            "win_probability": 0.62, "expected_margin": 7.0,
        }]),
        [_solution(), second_solution],
        console=console,
    )
    rendered = output.getvalue()

    assert "DUNKEST" in rendered
    assert "ROSA 1" in rendered
    assert "ROSA 2" in rendered
    assert "Slot" in rendered
    assert "Turno" not in rendered
    assert "Depth" not in rendered
    assert "Titolare · C" in rendered
    assert "Panchina" in rendered
    assert "Coach · matchup" in rendered
    assert "Vittoria" in rendered
    assert "Migliori plusvalenze" in rendered
    assert "Miglior rapporto PDK / CR" not in rendered
    assert "Giocatori | PDK attesi" not in rendered
    assert "P10-P90" not in rendered
    assert "120.0" in rendered



def test_lineup_report_shows_one_fixed_roster_with_5_1_4_slots():
    console, output = _console_output()
    solution = _solution()
    solution.meta["dynamic_turn_mode"] = True
    solution.players.loc[0, "slot"] = "Captain"
    solution.players.loc[1:4, "slot"] = "Starter"
    solution.players.loc[5, "slot"] = "Sixth Man"
    solution.players.loc[6:9, "slot"] = "Bench"
    print_matchday_report(Settings(), _predictions(), pd.DataFrame(), [solution], console=console)
    rendered = output.getvalue()
    assert "Formazione unica giornata" in rendered
    assert "5 titolari · 1 sesto uomo · 4 panchinari" in rendered
    assert "formazioni per turno" not in rendered


def test_season_opener_report_uses_readable_rich_sections():
    console, output = _console_output()
    market = pd.DataFrame(
        [
            {"player_name": "Player One", "cr_is_official": True},
            {"player_name": "Player Two", "cr_is_official": False},
        ]
    )

    print_season_opener_report(
        Settings(),
        _predictions(),
        market,
        pd.DataFrame(),
        [_solution()],
        {"eligible_players": 2, "feature_season": "2025-26"},
        console=console,
    )
    rendered = output.getvalue()

    assert "G1 2026-27" in rendered
    assert "Coach · matchup" in rendered
    assert "Migliori plusvalenze" not in rendered
    assert "ROSA 1" in rendered
    assert rendered.count("ROSA 1") == 1
    assert "Copertura listino" not in rendered
    assert "Top PDK" not in rendered


def test_integer_column_formats_pandas_float_values_without_crashing():
    console, output = _console_output()

    print_dataframe(
        console,
        "Integer fields",
        pd.DataFrame({"rank": [1.0, float("nan")]}),
        [("rank", "Rank", "d")],
    )

    assert "1" in output.getvalue()
    assert "n/d" in output.getvalue()


def test_coach_report_does_not_rank_historical_prior_as_a_matchup_pick():
    console, output = _console_output()
    from dunkest.report.terminal import print_best_coaches

    print_best_coaches(console, pd.DataFrame([{
        "coach": "Strong prior only", "team": "BOS", "opponent": "NYK",
        "coach_cr": 10.0, "expected_coach_pdk": 20.0,
        "matchup_projection_available": False,
    }]))

    rendered = output.getvalue()
    assert "nessun consiglio coach" in rendered
    assert "Strong prior only" not in rendered


def test_coach_report_exposes_opponent_credit_gap_and_value_per_credit():
    console, output = _console_output()
    from dunkest.report.terminal import print_best_coaches

    print_best_coaches(console, pd.DataFrame([{
        "coach": "Value Coach", "team": "BOS", "opponent": "NYK",
        "coach_cr": 8.0, "opponent_coach_cr": 7.0,
        "expected_coach_pdk": 12.0, "expected_margin": 7.0,
        "win_probability": 0.62, "matchup_projection_available": True,
        "coach_projection_source": "verified_matchup",
    }]))

    rendered = output.getvalue()
    assert "PDK" in rendered
    assert "CR avv." not in rendered
    assert "Value Coach" in rendered
