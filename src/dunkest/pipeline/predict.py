from __future__ import annotations


import pandas as pd

from dunkest.config import Settings
from dunkest.data.cache import cache_has_complete_collection
from dunkest.data.access import (
    get_dunkest_data,
    get_injuries,
    get_player_data,
    get_plusvalenza_history,
    save_injury_snapshot,
    save_coach_market_snapshot,
    get_team_data,
)
from dunkest.models.coach import predict_coach_points
from dunkest.data.access import get_coach_data
from dunkest.pipeline.forecast import build_player_forecast
from dunkest.models.rookie_prior import load_college_rookie_priors
from dunkest.report.artifacts import save_pre_match_snapshot
from dunkest.names import player_key


def _verified_team_context(fixtures: pd.DataFrame) -> dict[str, dict]:
    """Return only score-bearing team matchups from the verified Dunkest bridge."""
    context: dict[str, dict] = {}
    if fixtures.empty:
        return context

    def _truth(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"true", "1", "yes"}

    for _, fixture in fixtures.iterrows():
        home = str(fixture.get("home_team", "")).strip().upper()
        away = str(fixture.get("away_team", "")).strip().upper()
        turn = pd.to_numeric(fixture.get("dunkest_turn"), errors="coerce")
        game_id = str(fixture.get("nba_game_id", "")).strip()
        if not home or not away or pd.isna(turn) or not game_id:
            continue
        for team, opponent, is_home, valid_column in (
            (home, away, True, "home_team_eligible"),
            (away, home, False, "away_team_eligible"),
        ):
            if not _truth(fixture.get(valid_column, fixture.get("fantasy_eligible", False))):
                continue
            if team in context:
                raise RuntimeError(
                    f"La mappatura della giornata assegna più partite valide alla squadra {team}."
                )
            context[team] = {
                "opponent": opponent, "dunkest_turn": int(turn),
                "nba_game_id": game_id, "game_datetime_utc": fixture.get("game_datetime_utc"),
                "is_home": is_home,
            }
    return context


def _attach_verified_gameweek_context(
    settings: Settings, market: pd.DataFrame, fixtures: pd.DataFrame
) -> pd.DataFrame:
    """Attach opponent/turn identity and lineup annotation for each player's turn."""
    context = _verified_team_context(fixtures)
    if not context:
        raise RuntimeError(
            f"Nessun matchup Dunkest verificato per la Giornata {settings.target_gameweek}; "
            "non genero rose con turni o avversari ipotizzati."
        )
    out = market.copy()
    team_col = "team_code" if "team_code" in out else "team"
    if team_col not in out or "player_name" not in out:
        raise RuntimeError("Il mercato Dunkest non contiene player_name e team_code per collegare le fixture.")
    out["_team_context"] = out[team_col].astype(str).str.strip().str.upper().map(context)
    out = out.loc[out["_team_context"].notna()].copy()
    if out.empty:
        raise RuntimeError(
            f"Nessun giocatore del mercato è collegato alle partite verificate della Giornata {settings.target_gameweek}."
        )
    for column in ("opponent", "dunkest_turn", "nba_game_id", "game_datetime_utc", "is_home"):
        out[column] = out["_team_context"].map(lambda item: item[column])
    out["dunkest_turn"] = pd.to_numeric(out["dunkest_turn"], errors="coerce").astype(int)

    market_path = settings.data_path / "current_lineups_market.csv"
    if market_path.is_file():
        live = pd.read_csv(market_path)
        live.columns = [str(column).strip().lower() for column in live.columns]
        if {"player_name", "role"}.issubset(live.columns):
            live = live.loc[~live["role"].astype(str).str.upper().eq("HC")].copy()
            live["_player_key"] = live["player_name"].map(player_key)
            if live["_player_key"].duplicated(keep=False).any():
                raise RuntimeError("Il mercato Lineups contiene identità giocatore duplicate dopo la normalizzazione.")
            lookup = live.set_index("_player_key")
            out["_player_key"] = out["player_name"].map(player_key)
            for turn in (1, 2, 3):
                for column in (f"lineup_group_turn{turn}", f"starter_turn{turn}", f"status_turn{turn}"):
                    if column in lookup.columns:
                        out[column] = out["_player_key"].map(lookup[column])
            out = out.drop(columns="_player_key")

    global_status = out.get("status", pd.Series("", index=out.index)).fillna("").astype(str).str.strip().str.upper()
    global_group = out.get("lineup_group", pd.Series("", index=out.index)).fillna("").astype(str).str.strip().str.upper()
    hard_out = global_status.isin({"OUT", "INJURED", "UNAVAILABLE"}) | global_group.eq("INDISPONIBILI")
    for turn in (1, 2, 3):
        mask = out["dunkest_turn"].eq(turn)
        group_col, starter_col, status_col = (
            f"lineup_group_turn{turn}", f"starter_turn{turn}", f"status_turn{turn}"
        )
        if group_col in out:
            selected = out[group_col].fillna("").astype(str).str.strip()
            use = mask & ~hard_out & selected.ne("")
            out.loc[use, "lineup_group"] = selected.loc[use]
        if status_col in out:
            selected = out[status_col].fillna("").astype(str).str.strip()
            use = mask & ~hard_out & selected.ne("")
            out.loc[use, "status"] = selected.loc[use]
        if starter_col in out:
            selected = out[starter_col]
            use = mask & ~hard_out & selected.notna() & selected.astype(str).str.strip().ne("")
            out.loc[use, "starter"] = selected.loc[use]
    out.loc[hard_out, "lineup_group"] = "INDISPONIBILI"
    out.loc[hard_out, "status"] = "OUT"
    return out.drop(columns="_team_context").reset_index(drop=True)


def run_predict(
    settings: Settings, models: dict, features: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    gw = settings.target_gameweek
    dk = get_dunkest_data(settings, gw)
    from dunkest.data.dunkest.fixtures import get_fixture_mapping

    fixture_schedule = get_fixture_mapping(settings, gw)
    if fixture_schedule.empty:
        raise RuntimeError(
            f"Manca la mappatura verificata delle partite Dunkest per la Giornata {gw}. "
            "Aggiorna Lineups e acquisisci il calendario della giornata prima di generare rose."
        )
    dk = _attach_verified_gameweek_context(settings, dk, fixture_schedule)
    # Refresh the dedicated official Dunkest injury page after the gameweek
    # market/fixture capture; do not infer availability from partial Lineups UI.
    injuries = get_injuries(settings, force_refresh=True) if settings.use_injuries else pd.DataFrame()
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
    forecast = build_player_forecast(
        settings,
        models,
        features,
        dk,
        injuries,
        market_value_history=market_value_history,
        plusvalenza_history=plusvalenza_history,
        college_rookie_priors=rookie_priors,
        require_injury_snapshot=settings.use_injuries,
    )
    preds = forecast.raw.copy()
    # Override historical last-opponent fields with the verified upcoming matchup.
    if not preds.empty and {"team", "player_name"}.issubset(preds.columns):
        team_context = _verified_team_context(fixture_schedule)
        preds["_team_context"] = preds["team"].astype(str).str.strip().str.upper().map(team_context)
        preds = preds.loc[preds["_team_context"].notna()].copy()
        for column in ("opponent", "dunkest_turn", "nba_game_id", "game_datetime_utc", "is_home"):
            preds[column] = preds["_team_context"].map(lambda item: item[column])
        preds = preds.drop(columns="_team_context")
    # Retain the team forecast for coach modeling. Confirmed outs already have
    # zero availability-adjusted PDK; dropping rows here can erase a team from
    # the roster-strength comparison entirely.
    coach_strength_forecasts = preds.copy()
    preds = forecast.eligible.copy()
    preds.attrs["forecast_degradations"] = list(forecast.degradations)
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
    # The verified Dunkest mapping is mandatory for a valid gameweek forecast;
    # do not spend a network call on a raw NBA schedule that cannot establish
    # fantasy eligibility or turn identity.
    upcoming_schedule = fixture_schedule
    coach_data = get_coach_data(settings, gw)
    save_coach_market_snapshot(settings, coach_data, gw)
    # Freeze sanitized point-in-time inputs separately from mutable processed
    # caches. Never persist realized/current-week target columns as market data.
    market_columns = [
        column for column in (
            "player_name", "team_code", "team", "cr", "role", "position", "prior_pdk", "opponent",
            "dunkest_turn", "nba_game_id", "game_datetime_utc", "is_home", "gameweek",
            "lineup_group", "status", "starter", "lineup_group_turn1", "lineup_group_turn2",
            "lineup_group_turn3", "starter_turn1", "starter_turn2", "starter_turn3",
            "status_turn1", "status_turn2", "status_turn3",
        ) if column in dk.columns
    ]
    snapshot_path = save_pre_match_snapshot(
        settings, gw,
        {
            "player_market.parquet": dk[market_columns].copy(),
            "fixture_mapping.parquet": fixture_schedule.copy(),
            "injuries.parquet": injuries.copy(),
            "coach_market.parquet": coach_data.copy(),
            "market_value_history.parquet": market_value_history.copy(),
            "plusvalenza_history.parquet": plusvalenza_history.copy(),
            "rookie_priors.parquet": rookie_priors.copy(),
        },
        source="dunkest_live_forecast_inputs",
        metadata={
            "fixture_mapping_verified": bool(
                not fixture_schedule.empty
                and fixture_schedule.get("mapping_verified", pd.Series(False, index=fixture_schedule.index)).fillna(False).all()
            ),
            "injury_snapshot_rows": int(len(injuries)),
        },
    )
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
