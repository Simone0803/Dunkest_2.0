from __future__ import annotations

from dunkest.rules.roster import RosterRules, player_contribution_multiplier
from dunkest.names import player_key


def expected_player_points(
    expected_pdk: float,
    is_starter: bool,
    is_sixth: bool,
    is_captain: bool,
    rules: RosterRules | None = None,
) -> float:
    mult = player_contribution_multiplier(is_starter, is_sixth, is_captain, rules)
    return expected_pdk * mult


def transfer_count(
    selected_players: list[str],
    selected_coach: str | None,
    current_players: list[str] | None,
    current_coach: str | None,
) -> int:
    current_players = current_players or []
    cur = {player_key(p) for p in current_players if player_key(p)}
    sel = {player_key(p) for p in selected_players if player_key(p)}
    player_transfers = len(sel - cur) if cur else 0
    coach_transfer = 0
    if current_coach and selected_coach:
        if player_key(current_coach) != player_key(selected_coach):
            coach_transfer = 1
    elif selected_coach and not current_coach:
        coach_transfer = 0
    return player_transfers + coach_transfer
