from __future__ import annotations

import pandas as pd
from rich.console import Console

from dunkest.config import Settings
from dunkest.optimize.milp import LineupSolution
from dunkest.report.terminal import (
    CONSOLE,
    REPORT_VERSION,
    print_best_coaches,
    print_best_plusvalenze,
    print_lineup_cards,
)


def print_top_lineups(
    settings: Settings,
    solutions: list[LineupSolution],
    console: Console | None = None,
) -> None:
    console = console or CONSOLE
    print_lineup_cards(console, solutions)


def print_matchday_report(
    settings: Settings,
    predictions: pd.DataFrame,
    coach_df: pd.DataFrame,
    solutions: list[LineupSolution],
    console: Console | None = None,
) -> None:
    console = console or CONSOLE
    console.print(
        f"[bold]DUNKEST[/bold]  ·  Giornata {settings.target_gameweek}  ·  {settings.season}  ·  "
        f"budget {settings.budget:.0f} CR  ·  malus {settings.transfer_penalty:.0f} PDK"
        f"  ·  [dim]{REPORT_VERSION}[/dim]"
    )
    print_top_lineups(settings, solutions, console=console)
    print_best_coaches(console, coach_df)
    print_best_plusvalenze(console, predictions)
