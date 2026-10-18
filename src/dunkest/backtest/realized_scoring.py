"""Fail-closed realized roster scoring for fixture-linked walk-forward backtests."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

import pandas as pd

from dunkest.names import player_key
from dunkest.rules.roster import player_contribution_multiplier


@dataclass(frozen=True)
class RealizedTeamScore:
    player_score_before_transfers: float
    coach_score: float
    transfer_malus: float
    team_score: float
    complete: bool
    reason: str


def score_realized_team(
    players: pd.DataFrame,
    actual_player_scores: dict[str, float],
    *,
    actual_coach_score: float,
    transfer_count: float | int,
    transfer_penalty: float,
    coach_fixture_verified: bool,
) -> RealizedTeamScore:
    """Score 10 selected players + verified coach − official transfer malus.

    Missing player outcomes, unknown carried-roster transfer counts, invalid
    penalties, or unverified coach/fixture links yield an incomplete score rather
    than a deceptively high partial total.
    """
    nan = float("nan")
    if not isinstance(players, pd.DataFrame) or not {"player_name", "slot"}.issubset(players.columns):
        return RealizedTeamScore(nan, nan, nan, nan, False, "invalid_roster_schema")
    if len(players) != 10:
        return RealizedTeamScore(nan, nan, nan, nan, False, "roster_must_have_10_players")
    keys = players["player_name"].map(player_key)
    if keys.eq("").any() or keys.duplicated().any():
        return RealizedTeamScore(nan, nan, nan, nan, False, "invalid_or_duplicate_player_identity")
    if not isinstance(actual_player_scores, Mapping):
        return RealizedTeamScore(nan, nan, nan, nan, False, "missing_player_actuals")
    normalized_actuals: dict[str, float] = {}
    for name, value in actual_player_scores.items():
        normalized = player_key(name)
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        if not normalized or not isfinite(score):
            continue
        if normalized in normalized_actuals and normalized_actuals[normalized] != score:
            return RealizedTeamScore(nan, nan, nan, nan, False, "conflicting_normalized_player_actuals")
        normalized_actuals[normalized] = score
    missing = [key for key in keys if key not in normalized_actuals]
    if missing:
        return RealizedTeamScore(nan, nan, nan, nan, False, "missing_player_actuals")
    try:
        coach_score = float(actual_coach_score)
    except (TypeError, ValueError, OverflowError):
        return RealizedTeamScore(nan, nan, nan, nan, False, "missing_or_unverified_coach_actual")
    if not coach_fixture_verified or not isfinite(coach_score):
        return RealizedTeamScore(nan, nan, nan, nan, False, "missing_or_unverified_coach_actual")
    try:
        transfers = float(transfer_count)
        penalty = float(transfer_penalty)
    except (TypeError, ValueError, OverflowError):
        return RealizedTeamScore(nan, nan, nan, nan, False, "unknown_transfer_count_or_penalty")
    if not isfinite(transfers) or transfers < 0 or not transfers.is_integer() or not isfinite(penalty) or penalty < 0:
        return RealizedTeamScore(nan, nan, nan, nan, False, "invalid_transfer_count_or_penalty")

    player_score = 0.0
    for (_, row), key in zip(players.iterrows(), keys):
        slot = str(row.get("slot", "Bench"))
        supplied_multiplier = pd.to_numeric(row.get("score_multiplier", float("nan")), errors="coerce")
        multiplier = (
            float(supplied_multiplier)
            if pd.notna(supplied_multiplier)
            else player_contribution_multiplier(
                slot in {"Starter", "Captain"}, slot == "Sixth Man", slot == "Captain"
            )
        )
        if not isfinite(multiplier) or multiplier < 0:
            return RealizedTeamScore(nan, nan, nan, nan, False, "invalid_player_score_multiplier")
        player_score += normalized_actuals[key] * multiplier
    transfer_malus = transfers * penalty
    team_score = player_score + coach_score - transfer_malus
    return RealizedTeamScore(
        player_score_before_transfers=float(player_score),
        coach_score=coach_score,
        transfer_malus=float(transfer_malus),
        team_score=float(team_score),
        complete=True,
        reason="complete_fixture_linked_score",
    )
