from __future__ import annotations

from copy import copy
from pathlib import Path
import warnings

import pandas as pd

from dunkest.config import Settings, settings_for_season_opener
from dunkest.data.access import (
    get_coach_data,
    get_injuries,
    get_plusvalenza_history,
    save_player_credit_snapshot,
    save_injury_snapshot,
    save_coach_market_snapshot,
)
from dunkest.data.cache import cache_has_complete_collection, write_parquet
from dunkest.data.dunkest.opening import fetch_opening_coach_market, fetch_opening_market_pool
from dunkest.data.nba import collector as nba
from dunkest.data.dunkest.fixtures import ensure_gameweek1_fixture_mapping
from dunkest.data.nba.collector import require_complete_collection
from dunkest.data.nba.prior_season import fetch_prior_season_game_logs
from dunkest.features.builder import build_feature_matrix
from dunkest.models.coach import predict_coach_points
from dunkest.models.predictor import predict_players, train_models
from dunkest.models.rookie_prior import load_college_rookie_priors
from dunkest.names import player_key
from dunkest.optimize.milp import LineupSolution
from dunkest.pipeline.optimize import run_optimize
from dunkest.rules.eligibility import filter_injured


def _verified_gameweek_teams(fixtures: pd.DataFrame) -> set[str]:
    """Return only teams whose score-bearing side was explicitly verified."""
    verified: set[str] = set()
    if fixtures is None or fixtures.empty:
        return verified
    for _, fixture in fixtures.iterrows():
        for team_column, eligible_column in (
            ("home_team", "home_team_eligible"),
            ("away_team", "away_team_eligible"),
        ):
            value = fixture.get(eligible_column, fixture.get("fantasy_eligible", False))
            if pd.notna(value) and bool(value):
                team = str(fixture.get(team_column, "")).strip().upper()
                if team:
                    verified.add(team)
    return verified


def _require_complete_score_bearing_teams(
    fixtures: pd.DataFrame, market_teams: set[str]
) -> set[str]:
    verified = _verified_gameweek_teams(fixtures)
    missing = sorted(market_teams - verified)
    if not market_teams or missing:
        raise RuntimeError(
            "Calendario Dunkest G1 non verificato: matchup valido acquisito per "
            f"{len(market_teams.intersection(verified))}/{len(market_teams)} squadre. "
            f"Stati mancanti/non validi: {', '.join(missing[:12]) or 'listino squadre assente'}. "
            "Non genero rose con fixture o coach non verificati. Riesegui lo scraping "
            "Lineups; se Dunkest indica squadre a riposo, acquisisci anche quella sezione."
        )
    return verified


def get_opening_market(
    settings: Settings,
    credits_file: Path | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    proxy_tag = "_proxy" if settings.opening_use_pdk_cr_proxy else ""
    path = settings.data_path / "processed" / (
        f"opening_market_{settings.season_id}_{settings.opening_prior_season_id}_gw1{proxy_tag}.parquet"
    )
    if not force_refresh and credits_file is None and path.exists():
        return pd.read_parquet(path)
    df = fetch_opening_market_pool(
        settings,
        credits_file=credits_file,
        use_pdk_cr_proxy=settings.opening_use_pdk_cr_proxy,
        pdk_cr_scale=settings.opening_pdk_cr_scale,
    )
    write_parquet(df, path, source="opening_market", gameweek=1)
    return df


def run_season_opener(
    settings: Settings,
    credits_file: Path | None = None,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[LineupSolution], dict]:
    settings = settings_for_season_opener(settings, budget=settings.budget)

    market = get_opening_market(settings, credits_file=credits_file, force_refresh=force_refresh)
    if market.empty:
        raise RuntimeError(
            "Dunkest non ha ancora restituito il listone della stagione target. "
            "Riprova quando la sezione Lineup/Statistiche espone i CR 2026/27 "
            "oppure passa un CSV con player_name, cr, team e role."
        )
    settings.opening_player_names = market["player_name"].tolist()

    log_path = settings.data_path / "processed" / f"player_game_logs_{settings.feature_season}.parquet"
    if not force_refresh and log_path.exists() and cache_has_complete_collection(log_path):
        player_logs = pd.read_parquet(log_path)
    else:
        player_logs = fetch_prior_season_game_logs(settings)
        report = require_complete_collection(player_logs, "prior-season player game-log")
        write_parquet(
            player_logs,
            log_path,
            source="nba_api_prior_season",
            season=settings.feature_season,
            **report,
        )

    # Use official historical Dunkest PDK when available; otherwise derive the
    # season mean from full 2025/26 NBA box scores with Dunkest's scoring rules.
    if not player_logs.empty and {"PLAYER_NAME", "PDK"}.issubset(player_logs.columns):
        prior_means = player_logs.groupby("PLAYER_NAME", as_index=False)["PDK"].mean()
        prior_means["key"] = prior_means["PLAYER_NAME"].map(player_key)
        prior_map = prior_means.drop_duplicates("key").set_index("key")["PDK"]
        market["key"] = market["player_name"].map(player_key)
        market["prior_pdk"] = pd.to_numeric(market["prior_pdk"], errors="coerce").fillna(
            market["key"].map(prior_map)
        )
        market = market.drop(columns="key")

    injuries = get_injuries(settings) if settings.use_injuries else pd.DataFrame()
    if settings.use_injuries and injuries.empty:
        raise RuntimeError(
            "Archivio indisponibilità vuoto: interrompo season-opener per evitare "
            "rose con giocatori out. Aggiorna Lineups o registra gli indisponibili "
            "in data/injury_overrides.csv."
        )
    save_injury_snapshot(settings, injuries, 1)
    team_logs = pd.DataFrame()
    team_path = settings.data_path / "processed" / f"team_game_logs_{settings.feature_season}.parquet"
    if team_path.exists() and cache_has_complete_collection(team_path):
        team_logs = pd.read_parquet(team_path)
    else:
        prior_settings = copy(settings)
        prior_settings.season = settings.feature_season
        try:
            team_logs = nba.fetch_team_game_logs(prior_settings)
            report = require_complete_collection(team_logs, "prior-season team game-log")
            if not team_logs.empty:
                write_parquet(
                    team_logs,
                    team_path,
                    source="nba_api_prior_season/teamgamelog",
                    season=settings.feature_season,
                    **report,
                )
        except Exception as exc:
            team_logs = pd.DataFrame()
            warnings.warn(
                f"Statistiche difensive prior-season non disponibili; matchup difensivo neutro: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
    future_schedule = ensure_gameweek1_fixture_mapping(settings)
    market_teams = (
        set(market["team_code"].dropna().astype(str).str.strip().str.upper())
        if "team_code" in market else set()
    )
    # A lineup built with unknown fixture validity can rank players and
    # coaches against games that do not count. Do not present such a result
    # as an optimal roster. A valid future rest-team capture can be added to
    # this readiness check when that section is archived explicitly.
    verified_teams = _require_complete_score_bearing_teams(future_schedule, market_teams)
    n_games = int(future_schedule["nba_game_id"].nunique()) if "nba_game_id" in future_schedule else len(future_schedule)
    print(f"Fixture G1: {n_games} partite, {len(future_schedule)} righe mapping; matchup validi per {len(verified_teams)} squadre")
    # Keep the whole Giornata player pool. The team-specific valid Turno is
    # attached only from confirmed black/gray fixture sides; an NBA fixture or
    # the selected Lineups tab alone must never invent a Dunkest Turno.
    market["dunkest_turn"] = pd.Series(pd.NA, index=market.index, dtype="Int64")
    if not future_schedule.empty and "dunkest_turn" in future_schedule:
        team_turn: dict[str, int] = {}
        for _, fixture in future_schedule.iterrows():
            turn = pd.to_numeric(fixture.get("dunkest_turn"), errors="coerce")
            if pd.isna(turn):
                continue
            for team_col, valid_col in (
                ("home_team", "home_team_eligible"),
                ("away_team", "away_team_eligible"),
            ):
                valid = fixture.get(valid_col, False)
                if pd.notna(valid) and bool(valid):
                    team_turn[str(fixture.get(team_col, "")).strip().upper()] = int(turn)
        if "team_code" in market:
            turns = market["team_code"].astype(str).str.strip().str.upper().map(team_turn)
            market["dunkest_turn"] = pd.to_numeric(turns, errors="coerce").astype("Int64")
    save_player_credit_snapshot(settings, market, 1)
    team_overrides = (
        dict(zip(market["player_name"], market["team_code"].astype(str)))
        if {"player_name", "team_code"}.issubset(market.columns)
        else None
    )
    features = build_feature_matrix(
        settings,
        player_logs,
        team_logs=team_logs if not team_logs.empty else None,
        injuries=injuries,
        schedule=future_schedule,
        team_overrides=team_overrides,
        target_gameweek=1,
    )
    models, _ = train_models(settings, features)
    credit_history_path = settings.data_path / "processed" / (
        f"dunkest_players_{settings.opening_prior_season_id}_gw35.parquet"
    )
    credit_history = (
        pd.read_parquet(credit_history_path) if credit_history_path.exists() else pd.DataFrame()
    )
    rookie_priors = load_college_rookie_priors(settings.data_path / "rookie_college.csv")
    try:
        plusvalenza_history = get_plusvalenza_history(
            settings,
            season_id=settings.season_id,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        warnings.warn(
            f"Storico plusvalenze Dunkest non disponibile; stima attesa disattivata: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        plusvalenza_history = pd.DataFrame()

    preds = predict_players(
        settings,
        models,
        features,
        market,
        injuries,
        market_value_history=credit_history,
        plusvalenza_history=plusvalenza_history,
        college_rookie_priors=rookie_priors,
    )
    # Preserve hard-outs as zero-value team members for coach-strength
    # estimates; filtering them first can make a whole franchise disappear.
    coach_strength_forecasts = preds.copy()
    predicted_count = len(preds)
    preds = filter_injured(preds, injuries)
    available_keys = set(preds["player_name"].map(player_key))
    excluded = ~coach_strength_forecasts["player_name"].map(player_key).isin(available_keys)
    coach_strength_forecasts.loc[excluded, "expected_pdk"] = 0.0
    excluded_unavailable = predicted_count - len(preds)
    print(f"Indisponibili esclusi dalle rose: {excluded_unavailable} giocatori")

    mkt = market.drop_duplicates("player_name").copy()
    mkt["key"] = mkt["player_name"].map(player_key)
    prior_map = mkt.set_index("key")["prior_pdk"]
    preds["prior_pdk"] = preds["player_name"].map(player_key).map(prior_map)
    preds["expected_pdk"] = preds["expected_pdk"].fillna(0.0)

    coach_market = fetch_opening_coach_market(credits_file)
    coach_data = get_coach_data(
        settings,
        1,
        force_refresh=force_refresh or not coach_market.empty,
        coach_market=coach_market if not coach_market.empty else None,
    )
    if coach_data.empty and not coach_market.empty:
        coach_df = coach_market[["coach", "team", "coach_cr"]].drop_duplicates("team").copy()
    else:
        coach_df = predict_coach_points(
            coach_data,
            team_logs=team_logs if not team_logs.empty else None,
            upcoming_schedule=future_schedule,
            player_logs=player_logs,
            player_forecasts=coach_strength_forecasts,
            gameweek=1,
            use_model=settings.use_coach_model,
        )
    if coach_df.empty and not coach_market.empty:
        # A missing/partial fixture bridge must not erase the mandatory coach
        # slot or abort roster generation. Keep the complete official coach
        # market, label every projection as unverified, and assign zero points
        # until a score-bearing matchup is actually observed.
        coach_df = coach_market[["coach", "team", "coach_cr"]].drop_duplicates("team").copy()
        coach_df["opponent"] = ""
        coach_df["expected_coach_pdk"] = 0.0
        coach_df["p10_coach_pdk"] = 0.0
        coach_df["p50_coach_pdk"] = 0.0
        coach_df["p90_coach_pdk"] = 0.0
        coach_df["matchup_projection_available"] = False
        coach_df["coach_projection_source"] = "no_verified_matchup"
        warnings.warn(
            "Dati matchup coach assenti: mantengo il listino coach completo con "
            "contributo provvisorio 0 per non bloccare la rosa. Nessun coach è "
            "raccomandato finché il calendario valido non è verificato.",
            RuntimeWarning,
            stacklevel=2,
        )
    if coach_df.empty:
        raise RuntimeError(
            "Listino allenatori assente: nessun coach è stato letto dal CSV Lineups "
            "né dal catalogo Dunkest incluso. Aggiorna il listino coach prima di ottimizzare."
        )
    if "expected_coach_pdk" not in coach_df:
        coach_df["expected_coach_pdk"] = 0.0
        coach_df["p10_coach_pdk"] = 0.0
        coach_df["p50_coach_pdk"] = 0.0
        coach_df["p90_coach_pdk"] = 0.0
        coach_df["matchup_projection_available"] = False
        coach_df["coach_projection_source"] = "no_verified_matchup"
    save_coach_market_snapshot(
        settings, coach_data if not coach_data.empty else coach_df, 1
    )
    if not coach_df.empty:
        coach_df = coach_df.groupby("team", as_index=False).first()

    solutions = run_optimize(settings, preds, coach_df)
    if not solutions:
        raise RuntimeError(
            "Non è stata trovata alcuna rosa valida. "
            "Controlla che il listino Lineups contenga tutti i giocatori eleggibili, "
            "le quotazioni CR e le posizioni corrette."
        )
    for i, sol in enumerate(solutions, start=1):
        sol.rank = i

    meta = {
        "eligible_players": len(preds),
        "projection_weights": models.get("_projection_weights", {}),
        "projection_calibration_samples": models.get("_calibration_samples", 0),
        "credit_proxy_reference_rows": len(credit_history),
        "plusvalenza_reference_rows": len(plusvalenza_history),
        "plusvalenza_reference_gameweeks": sorted(
            pd.to_numeric(plusvalenza_history.get("gameweek"), errors="coerce")
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        ) if "gameweek" in plusvalenza_history else [],
        "official_cr_count": int(market.get("cr_is_official", pd.Series(dtype=bool)).sum())
        if "cr_is_official" in market.columns
        else 0,
        "feature_season": settings.feature_season,
        "budget": settings.budget,
    }
    return preds, coach_df, market, solutions, meta
