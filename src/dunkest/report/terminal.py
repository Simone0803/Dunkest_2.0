from __future__ import annotations

from numbers import Real
from typing import Sequence

import pandas as pd
from rich.box import ROUNDED, SIMPLE
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table


CONSOLE = Console(highlight=False)

# Visible marker so a run can confirm it is on the cleaned report path.
REPORT_VERSION = "report-v3-clean"


def print_header(console: Console, title: str, details: str = "") -> None:
    console.print(
        Panel.fit(
            details or "",
            title=title,
            border_style="cyan",
            padding=(0, 1),
        )
    )


def _cell(value: object, number_format: str | None) -> str:
    if value is None or value is pd.NA:
        return "n/d"
    try:
        if pd.isna(value):
            return "n/d"
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return "n/d"
    if number_format == "d" and isinstance(value, Real):
        return format(value, ".0f")
    if number_format and isinstance(value, Real):
        return format(value, number_format)
    return str(value)


def print_dataframe(
    console: Console,
    title: str,
    frame: pd.DataFrame,
    columns: Sequence[tuple[str, str, str | None]],
    max_rows: int | None = None,
) -> None:
    available = [column for column in columns if column[0] in frame.columns]
    if frame.empty or not available:
        return

    console.print(f"[bold]{title}[/bold]")
    table = Table(
        box=ROUNDED,
        header_style="bold cyan",
        title_style="bold",
        show_lines=False,
        pad_edge=False,
        expand=False,
    )
    for _, label, number_format in available:
        table.add_column(label, justify="right" if number_format else "left", no_wrap=True)

    visible = frame.head(max_rows) if max_rows is not None else frame
    for _, row in visible.iterrows():
        table.add_row(*[
            _cell(row[key], number_format)
            for key, _, number_format in available
        ])
    console.print(table)
    if max_rows is not None and len(frame) > max_rows:
        console.print(f"[dim]+ {len(frame) - max_rows} non mostrati[/dim]")


def lineup_details_frame(solutions) -> pd.DataFrame:
    rows = []
    for solution in solutions:
        for _, player in solution.players.iterrows():
            rows.append(
                {
                    "rank": solution.rank,
                    "player_name": player.get("player_name"),
                    "team": player.get("team"),
                    "role": player.get("role"),
                    "dunkest_turn": player.get("dunkest_turn"),
                    "cr": player.get("cr"),
                    "expected_min": player.get("expected_min"),
                    "expected_pdk": player.get("expected_pdk"),
                    "status": player.get("status"),
                    "slot": player.get("slot"),
                }
            )
    return pd.DataFrame(rows)


def print_lineup_cards(console: Console, solutions) -> None:
    border_styles = ("cyan", "yellow", "green")
    for index, solution in enumerate(solutions, start=1):
        rank = solution.rank or index
        coach_label = solution.coach
        if not solution.meta.get("coach_matchup_available", True):
            coach_label += "†"
        summary = (
            f"[bold]{solution.expected_team_pdk:.1f} PDK[/bold]  ·  "
            f"CR {solution.budget_used:.1f}  ·  "
            f"C {solution.captain}  ·  "
            f"Coach {coach_label}"
        )

        table = Table(box=SIMPLE, header_style="bold", pad_edge=False, show_edge=False)
        for label, justify in (
            ("Giocatore", "left"),
            ("Team", "left"),
            ("R", "left"),
            ("T", "right"),
            ("CR", "right"),
            ("PDK", "right"),
        ):
            table.add_column(label, justify=justify, no_wrap=True)

        players = solution.players.copy()
        slot_order = {"Captain": 0, "Starter": 1, "Sixth Man": 2, "Bench": 3}
        if "slot" in players.columns:
            players = players.assign(
                _ord=players["slot"].map(lambda s: slot_order.get(str(s), 9))
            ).sort_values(["_ord", "role", "player_name"])

        for _, player in players.iterrows():
            name = str(player.get("player_name") or "")
            if str(player.get("slot") or "") == "Captain":
                name = f"★ {name}"
            table.add_row(
                name,
                _cell(player.get("team"), None),
                _cell(player.get("role"), None),
                _cell(player.get("dunkest_turn"), "d"),
                _cell(player.get("cr"), ".1f"),
                _cell(player.get("expected_pdk"), ".1f"),
            )

        console.print(
            Panel(
                Group(summary, table),
                title=f"ROSA {rank}",
                border_style=border_styles[(rank - 1) % len(border_styles)],
                padding=(0, 1),
            )
        )
        if not solution.meta.get("coach_matchup_available", True):
            console.print("[dim]† Coach necessario per il roster, ma matchup e PDK non verificati.[/dim]")


def print_best_coaches(
    console: Console, coaches: pd.DataFrame, max_rows: int = 6
) -> None:
    if coaches.empty:
        console.print("[bold]Coach · matchup[/bold]")
        console.print("[dim]nessun consiglio coach: nessun matchup verificato[/dim]")
        return
    view = coaches.copy()
    if "coach_projection_source" in view:
        view = view.loc[view["coach_projection_source"].astype(str).eq("verified_matchup")].copy()
    elif "matchup_projection_available" in view:
        view = view.loc[view["matchup_projection_available"].fillna(False).astype(bool)].copy()
    if view.empty:
        console.print("[bold]Coach · matchup[/bold]")
        console.print("[dim]nessun consiglio coach: nessun matchup verificato[/dim]")
        return
    total_candidates = len(coaches)
    view["coach_rank_score"] = pd.to_numeric(
        view.get("expected_coach_pdk"), errors="coerce"
    )
    view = view.dropna(subset=["coach_rank_score"]).sort_values(
        "coach_rank_score", ascending=False
    )
    if view.empty:
        console.print("[bold]Coach · matchup[/bold]")
        console.print("[dim]nessun consiglio coach: nessun matchup verificato[/dim]")
        return
    view["matchup_label"] = view.get(
        "opponent", pd.Series("", index=view.index)
    ).fillna("").astype(str).str.strip()
    view.loc[view["matchup_label"].eq(""), "matchup_label"] = "storico"
    print_dataframe(
        console,
        "Coach · matchup",
        view,
        [
            ("coach", "Coach", None),
            ("team", "Team", None),
            ("matchup_label", "Matchup", None),
            ("win_probability", "Vittoria", ".0%"),
            ("expected_margin", "Δ punti", "+.1f"),
            ("coach_cr", "CR", ".1f"),
            ("expected_coach_pdk", "PDK", ".1f"),
        ],
        max_rows=max_rows,
    )
    if total_candidates > len(view):
        console.print(
            f"[dim]Matchup verificato: {len(view)}/{total_candidates} coach; "
            "gli altri non entrano nell’ottimizzazione[/dim]"
        )


def print_best_plusvalenze(
    console: Console, predictions: pd.DataFrame, max_rows: int = 8
) -> None:
    if predictions.empty:
        return
    view = predictions.copy()
    expected = pd.to_numeric(
        view.get("expected_plusvalenza", pd.Series(float("nan"), index=view.index)),
        errors="coerce",
    )
    if not expected.notna().any():
        return
    view["plusvalenza_rank"] = expected
    view = view.dropna(subset=["plusvalenza_rank"]).sort_values(
        "plusvalenza_rank", ascending=False
    )
    if not bool(view["plusvalenza_rank"].gt(0.05).any()):
        return
    print_dataframe(
        console,
        "Migliori plusvalenze",
        view,
        [
            ("player_name", "Giocatore", None),
            ("team", "Team", None),
            ("cr", "CR", ".1f"),
            ("plusvalenza_rank", "PLUS", "+.2f"),
        ],
        max_rows=max_rows,
    )
