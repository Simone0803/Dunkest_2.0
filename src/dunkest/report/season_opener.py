from __future__ import annotations

import pandas as pd
from rich.console import Console

from dunkest.config import Settings
from dunkest.optimize.milp import LineupSolution
from dunkest.report.console import print_top_lineups
from dunkest.report.terminal import (
    CONSOLE,
    REPORT_VERSION,
    print_best_coaches,
    print_best_plusvalenze,
)


def print_season_opener_report(
    settings: Settings,
    predictions: pd.DataFrame,
    market: pd.DataFrame,
    coach_df: pd.DataFrame,
    solutions: list[LineupSolution],
    meta: dict,
    console: Console | None = None,
) -> None:
    console = console or CONSOLE
    feature_season = meta.get("feature_season", settings.feature_season)
    console.print(
        f"[bold]G1 {settings.season}[/bold]  ·  "
        f"forma {feature_season}  ·  budget {settings.budget:.0f} CR"
        f"  ·  [dim]{REPORT_VERSION}[/dim]"
    )
    print_top_lineups(settings, solutions, console=console)
    print_best_coaches(console, coach_df)
    print_best_plusvalenze(console, predictions)
