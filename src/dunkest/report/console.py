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


def print_dvp_status(console: Console, predictions: pd.DataFrame) -> None:
    """Expose the operational matchup adjustment or its explicit fallback."""
    metadata = predictions.attrs.get("dvp_snapshot")
    if not isinstance(metadata, dict):
        return
    status = str(metadata.get("status", "unavailable"))
    capture = metadata.get("capture_attempt", {})
    if status == "applied":
        console.print(
            f"[dim]DvP applicato ai giocatori: {metadata.get('covered_rows', 0)}/"
            f"{metadata.get('player_rows', 0)} coperti · snapshot "
            f"{metadata.get('snapshot_id', 'n/d')} · cap ±"
            f"{100 * float(metadata.get('configured_max_relative_adjustment', 0.0)):.1f}%"
            " · effetto iniziale non validato OOS[/dim]"
        )
    else:
        reason = metadata.get("fallback_reason") or metadata.get("reason") or status
        console.print(f"[yellow]DvP non applicato: {reason}; PDK giocatori su baseline.[/yellow]")
    if isinstance(capture, dict) and capture.get("status") == "unavailable" and status == "applied":
        console.print(
            f"[dim]Aggiornamento DvP non riuscito; usato snapshot pre-cutoff già disponibile: "
            f"{capture.get('reason', 'errore non specificato')}[/dim]"
        )


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
    print_dvp_status(console, predictions)
    print_best_coaches(console, coach_df)
    print_best_plusvalenze(console, predictions)
