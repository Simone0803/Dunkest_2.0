from __future__ import annotations

import warnings

import pandas as pd

from dunkest.config import Settings
from dunkest.data.cache import cache_has_complete_collection
from dunkest.data.access import (
    get_dunkest_data,
    get_future_schedule,
    get_injuries,
    get_player_data,
    get_plusvalenza_history,
    save_injury_snapshot,
    save_coach_market_snapshot,
    get_team_data,
)
from dunkest.models.coach import predict_coach_points
from dunkest.data.access import get_coach_data
from dunkest.models.predictor import predict_players
from dunkest.models.rookie_prior import load_college_rookie_priors
from dunkest.names import player_key
from dunkest.rules.eligibility import filter_injured


def run_predict(
    settings: Settings, models: dict, features: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    gw = settings.target_gameweek
    dk = get_dunkest_data(settings, gw)
    injuries = get_injuries(settings) if settings.use_injuries else pd.DataFrame()
    if settings.use_injuries and injuries.empty:
        raise RuntimeError(
            "Archivio indisponibilità vuoto: non genero rose che potrebbero includere "
            "giocatori out. Aggiorna le indisponibilità da Dunkest o registra l'out in "
            "data/injury_overrides.csv (player_name, team, status, gameweek)."
        )
    save_injury_snapshot(settings, injuries, gw)
    plusvalenza_history = get_plusvalenza_history(
        settings, season_id=settings.opening_prior_season_id
    )
    processed_path = settings.data_path / "processed"
    price_history_path = processed_path / (
        f"dunkest_players_{settings.opening_prior_season_id}_gw35.parquet"
    )
    # Older caches used an unseasoned filename. During the season opener this
    # is still the prior-season Dunkest market snapshot and contains useful
    # player-level rates for NBA players with no current-season game logs.
    if not price_history_path.exists():
        legacy_path = processed_path / "dunkest_players_gw35.parquet"
        if legacy_path.exists():
            price_history_path = legacy_path
    market_value_history = (
        pd.read_parquet(price_history_path) if price_history_path.exists() else pd.DataFrame()
    )
    rookie_priors = load_college_rookie_priors(settings.data_path / "rookie_college.csv")
    preds = predict_players(
        settings,
        models,
        features,
        dk,
        injuries,
        market_value_history=market_value_history,
        plusvalenza_history=plusvalenza_history,
        college_rookie_priors=rookie_priors,
    )
    # Retain the team forecast for coach modeling. Confirmed outs already have
    # zero availability-adjusted PDK; dropping rows here can erase a team from
    # the roster-strength comparison entirely.
    coach_strength_forecasts = preds.copy()
    preds = filter_injured(preds, injuries)
    available_keys = set(preds["player_name"].map(player_key))
    excluded = ~coach_strength_forecasts["player_name"].map(player_key).isin(available_keys)
    coach_strength_forecasts.loc[excluded, "expected_pdk"] = 0.0
    player_logs = get_player_data(settings)
    team_logs = get_team_data(settings)
    if gw == 1:
        processed_path = settings.data_path / "processed"
        prior_players = processed_path / f"player_game_logs_{settings.feature_season}.parquet"
        prior_teams = processed_path / f"team_game_logs_{settings.feature_season}.parquet"
        if prior_players.exists() and cache_has_complete_collection(prior_players):
            player_logs = pd.read_parquet(prior_players)
        else:
            player_logs = pd.DataFrame()
        if prior_teams.exists() and cache_has_complete_collection(prior_teams):
            team_logs = pd.read_parquet(prior_teams)
        else:
            team_logs = pd.DataFrame()
    try:
        upcoming_schedule = get_future_schedule(settings)
    except Exception as exc:
        warnings.warn(
            f"Calendario futuro non disponibile per i coach; uso il mapping fixture Dunkest: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        upcoming_schedule = pd.DataFrame()
    # Prefer the versioned Dunkest fixture mapping for the target gameweek so
    # coach matchups stay aligned with fantasy eligibility. Fall back to the
    # raw NBA future schedule only when the mapping is missing.
    try:
        from dunkest.data.dunkest.fixtures import get_fixture_mapping

        fixture_schedule = get_fixture_mapping(settings, gw)
        if not fixture_schedule.empty:
            upcoming_schedule = fixture_schedule
    except Exception as exc:
        warnings.warn(
            f"Mapping fixture Dunkest non disponibile per i coach: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
    coach_data = get_coach_data(settings, gw)
    save_coach_market_snapshot(settings, coach_data, gw)
    coach_df = predict_coach_points(
        coach_data,
        team_logs=team_logs if not team_logs.empty else None,
        upcoming_schedule=upcoming_schedule if not upcoming_schedule.empty else None,
        player_logs=player_logs if not player_logs.empty else None,
        player_forecasts=coach_strength_forecasts,
        gameweek=gw,
        use_model=settings.use_coach_model,
    )
    if not coach_df.empty:
        coach_df = coach_df.groupby("team", as_index=False).first()
    return preds, coach_df
