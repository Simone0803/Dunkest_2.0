from __future__ import annotations

import warnings
from copy import copy

import pandas as pd

from dunkest.config import Settings
from dunkest.data.cache import cache_has_complete_collection
from dunkest.data.access import get_injuries, get_player_data, get_team_data
from dunkest.data.dunkest.fixtures import get_fixture_mapping
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import train_models
from dunkest.data.nba.collector import require_complete_collection


def run_train(settings: Settings) -> tuple[dict, pd.DataFrame]:
    if settings.target_gameweek == 1:
        # Opening-round forecasts must be trained on the completed prior
        # season, never on synthetic current-season logs or current outcomes.
        prior = copy(settings)
        prior.season = settings.feature_season
        prior_player_path = settings.data_path / "processed" / f"player_game_logs_{settings.feature_season}.parquet"
        prior_team_path = settings.data_path / "processed" / f"team_game_logs_{settings.feature_season}.parquet"
        if prior_player_path.exists() and cache_has_complete_collection(prior_player_path):
            player_logs = pd.read_parquet(prior_player_path)
        elif settings.use_nba_api_logs:
            from dunkest.data.nba.prior_season import fetch_prior_season_game_logs

            player_logs = fetch_prior_season_game_logs(prior)
            require_complete_collection(player_logs, "prior-season player game-log")
        else:
            player_logs = pd.DataFrame()
        if prior_team_path.exists() and cache_has_complete_collection(prior_team_path):
            team_logs = pd.read_parquet(prior_team_path)
        elif settings.use_nba_api_logs:
            from dunkest.data.nba.collector import fetch_team_game_logs

            team_logs = fetch_team_game_logs(prior)
            require_complete_collection(team_logs, "prior-season team game-log")
        else:
            team_logs = pd.DataFrame()
        if player_logs.empty:
            raise ValueError(
                f"No game logs found for opening-round training. Add or collect "
                f"the prior-season cache: {prior_player_path}"
            )
    else:
        player_logs = get_player_data(settings)
        team_logs = get_team_data(settings)
    injuries = get_injuries(settings) if settings.use_injuries else pd.DataFrame()
    try:
        schedule = get_fixture_mapping(settings, settings.target_gameweek) if settings.use_schedule else pd.DataFrame()
    except Exception as exc:
        warnings.warn(f"Upcoming schedule unavailable for player features: {exc}", RuntimeWarning, stacklevel=2)
        schedule = pd.DataFrame()
    market_path = settings.data_path / "current_lineups_market.csv"
    team_overrides: dict[str, str] = {}
    if market_path.exists():
        market = pd.read_csv(market_path)
        market.columns = [str(column).strip().lower() for column in market.columns]
        if {"player_name", "team", "role"}.issubset(market.columns):
            players = market.loc[~market["role"].astype(str).str.upper().eq("HC")]
            team_overrides = dict(zip(players["player_name"], players["team"].astype(str).str.upper()))
    features = build_feature_matrix(
        settings, player_logs, team_logs, injuries,
        schedule=schedule,
        team_overrides=team_overrides,
        target_gameweek=settings.target_gameweek,
    )
    models, _ = train_models(settings, features)
    return models, features
