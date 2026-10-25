from __future__ import annotations

import pandas as pd

from dunkest.config import Settings
from dunkest.optimize.milp import LineupSolution, optimize_top_k_lineups

REQUIRED_LINEUP_COUNT = 3


def run_optimize(
    settings: Settings,
    players: pd.DataFrame,
    coaches: pd.DataFrame,
) -> list[LineupSolution]:
    if settings.optimizer_top_k != REQUIRED_LINEUP_COUNT:
        raise RuntimeError(
            f"La pipeline Dunkest richiede esattamente {REQUIRED_LINEUP_COUNT} rose; "
            f"optimizer_top_k è configurato a {settings.optimizer_top_k}. "
            f"Imposta optimizer_top_k: {REQUIRED_LINEUP_COUNT}."
        )
    coach_candidates = coaches
    if not coaches.empty:
        if "coach_projection_source" in coaches.columns:
            # The season opener can project a verified fixture with neutral
            # scoring baselines when current-season team logs do not exist yet.
            # That is a real matchup projection and must not be confused with
            # prior-only or unverified coach rows.
            # Only score forecasts built from actual prior team results and a
            # verified Dunkest matchup are eligible. Neutral 112-112 fallbacks
            # are not score evidence and must never drive coach selection.
            verified_sources = {"verified_matchup"}
            verified = coaches["coach_projection_source"].astype(str).isin(verified_sources)
            if "matchup_projection_available" in coaches.columns:
                verified &= coaches["matchup_projection_available"].fillna(False).astype(bool)
            coach_candidates = coaches.loc[verified].copy()
        elif "matchup_projection_available" in coaches.columns:
            # A historical coach score is not a current-turn matchup prediction.
            coach_candidates = coaches.loc[
                coaches["matchup_projection_available"].fillna(False).astype(bool)
            ].copy()
        if coach_candidates.empty:
            raise RuntimeError(
                "Nessun coach ha una proiezione basata su un matchup Dunkest verificato. "
                "Interrompo l'ottimizzazione invece di assegnare un contributo coach "
                "artificiale pari a zero. Aggiorna fixture e proiezioni coach."
            )
    # Shadow minutes are archived for evaluation only and must never become
    # an optimizer input. The caller's frame remains untouched for reporting.
    operational_players = players.drop(
        columns=["expected_min_model_shadow"], errors="ignore"
    )
    solutions = optimize_top_k_lineups(
        operational_players,
        coach_candidates,
        settings,
        current_roster=settings.current_roster,
        current_coach=settings.current_coach,
        k=REQUIRED_LINEUP_COUNT,
    )
    if len(solutions) != REQUIRED_LINEUP_COUNT:
        raise RuntimeError(
            f"Il solver ha prodotto {len(solutions)} di {REQUIRED_LINEUP_COUNT} rose distinte valide. "
            "Non pubblico un risultato parziale: verifica la copertura del mercato e la diversificazione."
        )

    # Persist the actual matchup and scoring inputs behind the selected coach.
    # This is explanatory metadata; coach and players were optimized jointly
    # under the same CR budget and team constraints by the MILP.
    for solution in solutions:
        # Test doubles or alternate optimizer adapters may not expose lineup metadata.
        if not hasattr(solution, "coach") or not hasattr(solution, "meta"):
            continue
        match = coach_candidates.loc[
            coach_candidates["coach"].astype(str).eq(str(solution.coach))
        ]
        if len(match) != 1:
            continue
        row = match.iloc[0]
        def optional_value(column: str):
            value = row.get(column)
            if value is None or pd.isna(value):
                return None
            if column in {"win_probability", "win_probability_before_roster_adjustment"}:
                return float(value)
            if column == "dunkest_turn":
                return int(value)
            if column in {"coach_cr", "opponent_coach_cr", "expected_coach_pdk", "p10_coach_pdk",
                          "p50_coach_pdk", "p90_coach_pdk", "expected_team_pts", "expected_opp_pts",
                          "expected_margin"}:
                return float(value)
            return str(value)
        solution.meta["coach_matchup"] = {
            "coach_team": optional_value("team"),
            "coach_opponent": optional_value("opponent"),
            "coach_dunkest_turn": optional_value("dunkest_turn"),
            "coach_nba_game_id": optional_value("nba_game_id"),
            "coach_cr": optional_value("coach_cr"),
            "opponent_coach": optional_value("opponent_coach"),
            "opponent_coach_cr": optional_value("opponent_coach_cr"),
            "expected_coach_pdk": optional_value("expected_coach_pdk"),
            "p10_coach_pdk": optional_value("p10_coach_pdk"),
            "p50_coach_pdk": optional_value("p50_coach_pdk"),
            "p90_coach_pdk": optional_value("p90_coach_pdk"),
            "expected_team_pts": optional_value("expected_team_pts"),
            "expected_opp_pts": optional_value("expected_opp_pts"),
            "expected_margin": optional_value("expected_margin"),
            "win_probability": optional_value("win_probability"),
            "win_probability_before_roster_adjustment": optional_value("win_probability_before_roster_adjustment"),
            "coach_projection_source": optional_value("coach_projection_source"),
            "matchup_projection_available": bool(row.get("matchup_projection_available", False)),
            "coach_opportunity_cost_pdk": solution.meta.get("coach_opportunity_cost_pdk"),
            "budget_shadow_price": solution.meta.get("budget_shadow_price")
                if solution.meta.get("budget_shadow_price_available") else None,
        }
    return solutions
