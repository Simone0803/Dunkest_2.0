from __future__ import annotations

import math

import numpy as np


def coach_coefficient(cr_diff: float, coach_is_higher: bool, score_positive: bool) -> float:
    """Dunkest coach coefficient from credit difference between coaches."""
    d = abs(cr_diff)
    if d < 1:
        mult_high, mult_low = 1.00, 1.00
    elif d < 2:
        mult_high, mult_low = 0.95, 1.05
    elif d < 4:
        mult_high, mult_low = 0.91, 1.14
    elif d < 6:
        mult_high, mult_low = 0.87, 1.23
    elif d < 8:
        mult_high, mult_low = 0.83, 1.32
    elif d < 12:
        mult_high, mult_low = 0.79, 1.41
    elif d < 16:
        mult_high, mult_low = 0.75, 1.50
    else:
        mult_high, mult_low = 0.70, 1.60
    mult = mult_high if coach_is_higher else mult_low
    return mult if score_positive else 1.0 / mult


def _margin_bucket(margin: int, win: bool) -> float:
    m = abs(margin)
    if win:
        if m <= 5:
            return 15
        if m <= 10:
            return 18
        if m <= 15:
            return 20
        if m <= 20:
            return 23
        if m <= 25:
            return 25
        if m <= 30:
            return 28
        if m <= 35:
            return 30
        if m <= 40:
            return 33
        return 35
    if m <= 5:
        return -7
    if m <= 10:
        return -10
    if m <= 15:
        return -13
    if m <= 20:
        return -15
    if m <= 25:
        return -18
    if m <= 30:
        return -20
    if m <= 35:
        return -23
    if m <= 40:
        return -25
    return -30


def coach_points_from_game(
    team_pts: float,
    opp_pts: float,
    coach_cr: float,
    opponent_coach_cr: float,
    overtime: bool = False,
) -> float:
    return float(coach_points_from_outcomes(
        team_pts, opp_pts, coach_cr, opponent_coach_cr, overtime
    ))


def coach_points_from_outcomes(
    team_pts: float | np.ndarray,
    opp_pts: float | np.ndarray,
    coach_cr: float,
    opponent_coach_cr: float,
    overtime: bool | np.ndarray = False,
) -> float | np.ndarray:
    """Vectorized official Dunkest coach score for one or many game outcomes."""
    coach_credit = float(coach_cr)
    opponent_credit = float(opponent_coach_cr)
    if not math.isfinite(coach_credit) or not math.isfinite(opponent_credit):
        raise ValueError("Coach credits must be finite to calculate coach points.")
    team = np.asarray(team_pts, dtype=float)
    opponent = np.asarray(opp_pts, dtype=float)
    valid_outcome = (
        np.isfinite(team)
        & np.isfinite(opponent)
        & (team >= 0.0)
        & (opponent >= 0.0)
        & (team != opponent)
    )
    margin = np.trunc(team - opponent)
    absolute_margin = np.abs(margin)
    won = margin > 0
    winning = np.select(
        [absolute_margin <= 5, absolute_margin <= 10, absolute_margin <= 15,
         absolute_margin <= 20, absolute_margin <= 25, absolute_margin <= 30,
         absolute_margin <= 35, absolute_margin <= 40],
        [15, 18, 20, 23, 25, 28, 30, 33], default=35,
    )
    losing = np.select(
        [absolute_margin <= 5, absolute_margin <= 10, absolute_margin <= 15,
         absolute_margin <= 20, absolute_margin <= 25, absolute_margin <= 30,
         absolute_margin <= 35, absolute_margin <= 40],
        [-7, -10, -13, -15, -18, -20, -23, -25], default=-30,
    )
    base = np.where(won, winning, losing).astype(float)
    ot = np.asarray(overtime, dtype=bool)
    base = np.where(ot, np.where(won, 18.0, -10.0), base)
    base += np.where(team >= 120, 5.0, 0.0)
    base += np.where(opponent <= 95, 5.0, 0.0)
    base -= np.where(team <= 95, 3.0, 0.0)
    base -= np.where(opponent >= 120, 3.0, 0.0)

    difference = coach_credit - opponent_credit
    higher = difference >= 0.0
    positive = coach_coefficient(abs(difference), higher, True)
    negative = coach_coefficient(abs(difference), higher, False)
    result = base * np.where(base >= 0.0, positive, negative)
    result = np.where(valid_outcome, result, np.nan)
    return float(result) if result.ndim == 0 else result
