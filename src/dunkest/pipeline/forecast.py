"""Shared point-in-time player forecast path for live and walk-forward runs.

Callers must supply only inputs available at their forecast cutoff. This module
owns prediction, hard-out filtering and the team-strength-preserving raw frame;
it deliberately does not fetch data or invent missing historical snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from dunkest.config import Settings
from dunkest.models.predictor import predict_players
from dunkest.rules.eligibility import filter_injured


@dataclass(frozen=True)
class PlayerForecast:
    raw: pd.DataFrame
    eligible: pd.DataFrame
    degradations: tuple[str, ...]


def build_player_forecast(
    settings: Settings,
    models: dict,
    features: pd.DataFrame,
    market: pd.DataFrame,
    injuries: pd.DataFrame | None,
    *,
    market_value_history: pd.DataFrame | None = None,
    plusvalenza_history: pd.DataFrame | None = None,
    college_rookie_priors: pd.DataFrame | None = None,
    require_injury_snapshot: bool = False,
) -> PlayerForecast:
    """Build raw and eligible forecasts from explicit as-of inputs only."""
    degradations: list[str] = []
    injury_frame = injuries if injuries is not None else pd.DataFrame()
    if injury_frame.empty:
        if settings.use_injuries and require_injury_snapshot:
            raise RuntimeError("Required point-in-time injury snapshot is missing or empty.")
        if settings.use_injuries:
            degradations.append("injury_snapshot_missing_or_empty")
    if market_value_history is None or market_value_history.empty:
        degradations.append("market_value_history_unavailable")
    if plusvalenza_history is None or plusvalenza_history.empty:
        degradations.append("plusvalenza_history_unavailable")
    if college_rookie_priors is None or college_rookie_priors.empty:
        degradations.append("college_rookie_priors_unavailable")

    raw = predict_players(
        settings,
        models,
        features,
        market,
        injury_frame,
        market_value_history=market_value_history,
        plusvalenza_history=plusvalenza_history,
        college_rookie_priors=college_rookie_priors,
    )
    if not raw.empty:
        if not {"player_name", "expected_pdk"}.issubset(raw.columns):
            raise RuntimeError("Player forecaster omitted required identity or expected_pdk fields.")
        expected = pd.to_numeric(raw["expected_pdk"], errors="coerce")
        if not expected.notna().all() or not expected.map(lambda value: abs(float(value)) < float("inf")).all():
            raise RuntimeError("Player forecaster returned non-finite expected PDK values.")
    eligible = filter_injured(raw, injury_frame) if settings.use_injuries else raw.copy()
    return PlayerForecast(raw=raw, eligible=eligible, degradations=tuple(sorted(set(degradations))))
