from __future__ import annotations

from dataclasses import dataclass


FORMATIONS: list[tuple[int, int, int]] = [
    (2, 2, 1),
    (1, 2, 2),
    (2, 1, 2),
    (1, 3, 1),
    (3, 1, 1),
]


@dataclass(frozen=True)
class RosterRules:
    total_players: int = 10
    guards: int = 4
    forwards: int = 4
    centers: int = 2
    starters: int = 5
    sixth_man: int = 1
    bench: int = 4
    captains: int = 1
    starter_multiplier: float = 1.0
    sixth_man_multiplier: float = 1.0
    captain_multiplier: float = 1.5
    bench_multiplier: float = 0.5
    max_from_same_team: int = 3
    base_budget: float = 95.0


def player_contribution_multiplier(
    is_starter: bool,
    is_sixth: bool,
    is_captain: bool,
    rules: RosterRules | None = None,
) -> float:
    rules = rules or RosterRules()
    if is_starter and is_captain:
        return rules.captain_multiplier
    if is_starter:
        return rules.starter_multiplier
    if is_sixth:
        return rules.sixth_man_multiplier
    return rules.bench_multiplier
