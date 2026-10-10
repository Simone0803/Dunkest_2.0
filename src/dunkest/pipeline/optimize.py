from __future__ import annotations

import warnings

import pandas as pd

from dunkest.config import Settings
from dunkest.optimize.milp import LineupSolution, optimize_top_k_lineups


def run_optimize(
    settings: Settings,
    players: pd.DataFrame,
    coaches: pd.DataFrame,
) -> list[LineupSolution]:
    coach_candidates = coaches
    if not coaches.empty and "coach_projection_source" in coaches.columns:
        coach_candidates = coaches.loc[
            coaches["coach_projection_source"].astype(str).eq("verified_matchup")
        ].copy()
        if coach_candidates.empty:
            # Dunkest requires one coach in a legal roster. If the scraped
            # calendar has no verified matchup, keep the lineup optimizer
            # usable with an explicitly zeroed, unranked coach fallback.
            # This does not turn a price-only coach into a matchup recommendation.
            coach_candidates = coaches.copy()
            coach_candidates["expected_coach_pdk"] = 0.0
            for column in ("p10_coach_pdk", "p50_coach_pdk", "p90_coach_pdk"):
                if column in coach_candidates:
                    coach_candidates[column] = 0.0
            coach_candidates["matchup_projection_available"] = False
            coach_candidates["coach_projection_source"] = "no_verified_matchup_cost_fallback"
            warnings.warn(
                "Nessun coach ha un matchup Dunkest verificato. Genero rose provvisorie "
                "con contributo coach pari a 0; il coach scelto non è una raccomandazione. "
                "Aggiorna il calendario prima di usare il punteggio totale.",
                RuntimeWarning,
                stacklevel=2,
            )
    elif not coaches.empty and "matchup_projection_available" in coaches.columns:
        # A historical coach score is not a current-turn matchup prediction.
        # Only verified matchup forecasts may consume the required coach slot.
        coach_candidates = coaches.loc[
            coaches["matchup_projection_available"].fillna(False).astype(bool)
        ].copy()
    return optimize_top_k_lineups(
        players,
        coach_candidates,
        settings,
        current_roster=settings.current_roster,
        current_coach=settings.current_coach,
        k=settings.optimizer_top_k,
    )
