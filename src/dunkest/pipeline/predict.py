from __future__ import annotations


import pandas as pd

from dunkest.config import Settings
from dunkest.data.cache import (
    cache_has_complete_collection,
    cache_valid,
    read_cache_metadata,
    read_parquet,
)
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
    seen_game_ids: set[str] = set()
    if fixtures.empty:
        return context

    def _truth(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"true", "1", "yes"}

    for _, fixture in fixtures.iterrows():
        if not _truth(fixture.get("mapping_verified", False)):
            continue
        raw_home = fixture.get("home_team")
        raw_away = fixture.get("away_team")
        raw_game_id = fixture.get("nba_game_id")
        home = "" if pd.isna(raw_home) else str(raw_home).strip().upper()
        away = "" if pd.isna(raw_away) else str(raw_away).strip().upper()
        turn = pd.to_numeric(fixture.get("dunkest_turn"), errors="coerce")
        game_id = "" if pd.isna(raw_game_id) else str(raw_game_id).strip()
        if not _truth(fixture.get("home_team_eligible", fixture.get("fantasy_eligible", False))) and not _truth(
            fixture.get("away_team_eligible", fixture.get("fantasy_eligible", False))
        ):
            continue
        if not game_id or game_id.casefold() in {"nan", "none", "<na>"}:
            raise RuntimeError("Una fixture verificata ed eleggibile non contiene nba_game_id.")
        if not home or not away or home == away or pd.isna(turn):
            raise RuntimeError(f"Fixture NBA {game_id} verificata ma incompleta o non valida.")
        if game_id in seen_game_ids:
            raise RuntimeError(f"nba_game_id {game_id} è associato a più fixture.")
        seen_game_ids.add(game_id)
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
            raw_dunkest_match_id = fixture.get("dunkest_match_id")
            has_dunkest_match_id = (
                not pd.isna(raw_dunkest_match_id)
                and str(raw_dunkest_match_id).strip().casefold() not in {"", "<na>", "nan", "none"}
            )
            context[team] = {
                "opponent": opponent, "dunkest_turn": int(turn),
                "nba_game_id": game_id, "game_datetime_utc": fixture.get("game_datetime_utc"),
                "is_home": is_home,
                "dunkest_match_id": str(raw_dunkest_match_id).strip() if has_dunkest_match_id else None,
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
    for column in (
        "opponent", "dunkest_turn", "nba_game_id", "game_datetime_utc",
        "is_home", "dunkest_match_id",
    ):
        out[column] = out["_team_context"].map(lambda item: item.get(column))
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
    if "status" not in out.columns:
        out["status"] = pd.Series(
            index=out.index,
            dtype="object",
        )
    else:
        out["status"] = out["status"].astype("object")
    out.loc[hard_out, "status"] = "OUT"
    return out.drop(columns="_team_context").reset_index(drop=True)


def _attach_prediction_fixture_context(
    predictions: pd.DataFrame, fixtures: pd.DataFrame
) -> pd.DataFrame:
    """Retain verified matchup identifiers through forecasting and optimization."""
    out = predictions.copy()
    if out.empty or not {"team", "player_name"}.issubset(out.columns):
        return out
    context = _verified_team_context(fixtures)
    out["_team_context"] = out["team"].astype(str).str.strip().str.upper().map(context)
    out = out.loc[out["_team_context"].notna()].copy()
    for column in (
        "opponent", "dunkest_turn", "nba_game_id", "game_datetime_utc",
        "is_home", "dunkest_match_id",
    ):
        out[column] = out["_team_context"].map(lambda item: item.get(column))
    return out.drop(columns="_team_context").reset_index(drop=True)


def _attach_candidate_fixture_context(
    predictions: pd.DataFrame, fixtures: pd.DataFrame
) -> pd.DataFrame:
    """Keep every forecast candidate, marking unverified fixture links explicitly."""
    out = predictions.copy()
    if out.empty or not {"team", "player_name"}.issubset(out.columns):
        return out
    context = _verified_team_context(fixtures)
    teams = out["team"].astype(str).str.strip().str.upper()
    linked = teams.map(context)
    out["fixture_verified"] = linked.notna()
    for column in (
        "opponent", "dunkest_turn", "nba_game_id", "game_datetime_utc",
        "is_home", "dunkest_match_id",
    ):
        out[column] = linked.map(lambda item: item.get(column) if isinstance(item, dict) else pd.NA)
    out["fixture_outcome_status"] = out["fixture_verified"].map(
        {True: "verified", False: "unverified_or_missing"}
    )
    return out.reset_index(drop=True)


def run_predict(
    settings: Settings, models: dict, features: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    gw = settings.target_gameweek
    dk = get_dunkest_data(settings, gw)
    from dunkest.data.dunkest.fixtures import (
        certify_official_gameweek_cutoffs,
        fetch_official_dunkest_gameweek_calendar,
        get_fixture_mapping,
    )

    fixture_schedule = get_fixture_mapping(settings, gw)
    if fixture_schedule.empty:
        raise RuntimeError(
            f"Manca la mappatura verificata delle partite Dunkest per la Giornata {gw}. "
            "Aggiorna Lineups e acquisisci il calendario della giornata prima di generare rose."
        )
    cutoff_source_metadata: dict = {}
    cutoff_evidence: dict = {
        "status": "uncertified",
        "gameweek": int(gw),
        "cutoff_kind": "unknown",
        "reason": "official_cutoff_source_not_acquired",
    }
    try:
        official_calendar, cutoff_source_metadata = fetch_official_dunkest_gameweek_calendar(gw)
        cutoff_evidence = certify_official_gameweek_cutoffs(
            fixture_schedule, official_calendar, cutoff_source_metadata, gameweek=gw
        )
        cutoff_evidence["cutoff_kind"] = "official_rule_derived"
        cutoff_evidence["cutoff_semantics"] = cutoff_source_metadata.get("cutoff_semantics")
        cutoff_evidence["source"] = cutoff_source_metadata.get("source")
        cutoff_evidence["evidence_payloads"] = cutoff_source_metadata.get("evidence_payloads")
    except Exception as exc:
        # Prediction can continue for diagnosis, but an unavailable or invalid
        # official cutoff source must remain explicitly uncertified.
        cutoff_evidence["reason"] = (
            f"official_cutoff_source_unavailable_or_invalid:{type(exc).__name__}:{str(exc)[:300]}"
        )
    from dunkest.data.dunkest.defense_vs_position import (
        apply_dvp_pdk_adjustment,
        capture_optional_snapshot,
        load_eligible_snapshot_for_cutoff,
    )

    if settings.use_dvp_matchup:
        dvp_capture = capture_optional_snapshot(settings)
    else:
        dvp_capture = {"status": "disabled", "reason": "use_dvp_matchup=false"}
    try:
        cutoff_for_dvp = (
            cutoff_evidence.get("cutoff_utc")
            if cutoff_evidence.get("status") == "certified" else None
        )
        dvp_frame, dvp_snapshot = load_eligible_snapshot_for_cutoff(
            settings, cutoff_utc=cutoff_for_dvp
        )
    except Exception as exc:
        dvp_frame = None
        dvp_snapshot = {
            "status": "unavailable",
            "reason": f"snapshot_selection_error:{type(exc).__name__}:{str(exc)[:300]}",
        }
    dvp_snapshot["capture_attempt"] = dvp_capture
    dk = _attach_verified_gameweek_context(settings, dk, fixture_schedule)
    # Refresh the dedicated official Dunkest injury page after the gameweek
    # market/fixture capture; do not infer availability from partial Lineups UI.
    # Reuse a fresh, same-gameweek official injuries snapshot when already
    # captured; get_injuries still refreshes on cache miss or stale scope.
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
    candidate_forecasts = _attach_candidate_fixture_context(forecast.raw, fixture_schedule)
    turn_cutoffs = cutoff_evidence.get("turn_cutoffs_utc", {})
    official_fixture_links = cutoff_evidence.get("fixture_links", [])
    official_match_ids = {
        link["nba_game_id"]: link["dunkest_match_id"]
        for link in official_fixture_links
    }
    if official_match_ids:
        candidate_forecasts["dunkest_match_id"] = candidate_forecasts["nba_game_id"].astype("string").map(
            official_match_ids
        )
    if turn_cutoffs:
        candidate_forecasts["dunkest_turn_cutoff_utc"] = candidate_forecasts["dunkest_turn"].map(
            lambda value: turn_cutoffs.get(str(int(value))) if pd.notna(value) else pd.NA
        )
    else:
        candidate_forecasts["dunkest_turn_cutoff_utc"] = pd.NaT
    lineups_metadata = read_cache_metadata(settings.data_path / "current_lineups_market.csv") or {}
    injury_metadata = read_cache_metadata(
        settings.data_path / "processed" / f"injuries_{settings.season_id}_gw{gw}.parquet"
    ) or {}
    candidate_forecasts["lineups_availability_observed_at_utc"] = lineups_metadata.get("fetched_at")
    candidate_forecasts["injury_availability_observed_at_utc"] = injury_metadata.get("fetched_at")
    preds = _attach_prediction_fixture_context(forecast.raw, fixture_schedule)
    # Retain the team forecast for coach modeling. Confirmed outs already have
    # zero availability-adjusted PDK; dropping rows here can erase a team from
    # the roster-strength comparison entirely.
    coach_strength_forecasts = preds.copy()
    preds = _attach_prediction_fixture_context(forecast.eligible, fixture_schedule)
    try:
        candidate_forecasts, candidate_dvp_meta = apply_dvp_pdk_adjustment(
            candidate_forecasts, dvp_frame, settings, snapshot_metadata=dvp_snapshot
        )
        preds, operational_dvp_meta = apply_dvp_pdk_adjustment(
            preds, dvp_frame, settings, snapshot_metadata=dvp_snapshot
        )
        dvp_snapshot = {**dvp_snapshot, **operational_dvp_meta}
        dvp_snapshot["candidate_rows"] = candidate_dvp_meta.get("player_rows", 0)
        dvp_snapshot["candidate_covered_rows"] = candidate_dvp_meta.get("covered_rows", 0)
    except Exception as exc:
        import warnings

        warnings.warn(
            f"DvP adjustment failed; using baseline player PDK: {type(exc).__name__}: {exc}",
            RuntimeWarning,
        )
        fallback_meta = {
            **dvp_snapshot,
            "status": "unavailable",
            "reason": f"adjustment_error:{type(exc).__name__}:{str(exc)[:300]}",
        }
        candidate_forecasts, _ = apply_dvp_pdk_adjustment(
            candidate_forecasts, None, settings, snapshot_metadata=fallback_meta
        )
        preds, dvp_snapshot = apply_dvp_pdk_adjustment(
            preds, None, settings, snapshot_metadata=fallback_meta
        )
    preds.attrs["candidate_forecasts"] = candidate_forecasts
    runtime_feature_snapshot = forecast.raw.attrs.get("runtime_feature_snapshot")
    preds.attrs["runtime_feature_snapshot"] = (
        runtime_feature_snapshot.copy()
        if isinstance(runtime_feature_snapshot, pd.DataFrame)
        else pd.DataFrame()
    )
    preds.attrs["minutes_shadow_feature_columns"] = list(
        forecast.raw.attrs.get("minutes_shadow_feature_columns", [])
    )
    preds.attrs["forecast_timestamp_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
    preds.attrs["dunkest_cutoff_evidence"] = cutoff_evidence
    preds.attrs["dunkest_lock_utc"] = cutoff_evidence.get("cutoff_utc")
    preds.attrs["dunkest_lock_source"] = (
        "official_rule_derived:first_match_start_minus_1_minute"
        if cutoff_evidence.get("status") == "certified" else ""
    )
    preds.attrs["dunkest_lock_source_sha256"] = cutoff_evidence.get("evidence_sha256", "")
    preds.attrs["dunkest_lock_verified"] = cutoff_evidence.get("status") == "certified"
    forecast_degradations = list(forecast.degradations)
    if dvp_snapshot.get("status") not in {"applied", "disabled"}:
        forecast_degradations.append(
            f"dvp_fallback:{dvp_snapshot.get('fallback_reason') or dvp_snapshot.get('reason') or dvp_snapshot.get('status')}"
        )
    preds.attrs["forecast_degradations"] = sorted(set(forecast_degradations))
    preds.attrs["dvp_snapshot"] = dvp_snapshot
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
    # Combine historical team logs with current-season logs for coach forecasts.
    if gw > 1:
        processed_path = settings.data_path / "processed"
        prior_teams = (
            processed_path
            / f"team_game_logs_{settings.feature_season}.parquet"
        )

        if (
            prior_teams.exists()
            and cache_has_complete_collection(prior_teams)
        ):
            historical_team_logs = pd.read_parquet(prior_teams)

            if not historical_team_logs.empty:
                # Normalize game-ID column names before combining seasons.
                if (
                    "GAME_ID" in historical_team_logs
                    and "Game_ID" not in historical_team_logs
                ):
                    historical_team_logs = historical_team_logs.rename(
                        columns={"GAME_ID": "Game_ID"}
                    )

                if (
                    team_logs is not None
                    and "GAME_ID" in team_logs
                    and "Game_ID" not in team_logs
                ):
                    team_logs = team_logs.rename(
                        columns={"GAME_ID": "Game_ID"}
                    )

                if team_logs is None or team_logs.empty:
                    team_logs = historical_team_logs
                else:
                    team_logs = pd.concat(
                        [historical_team_logs, team_logs],
                        ignore_index=True,
                        sort=False,
                    )

                if {
                    "Game_ID", "TEAM_ABBREVIATION"
                }.issubset(team_logs.columns):
                    team_logs["Game_ID"] = team_logs["Game_ID"].astype(str)
                    team_logs = team_logs.drop_duplicates(
                        ["Game_ID", "TEAM_ABBREVIATION"],
                        keep="last",
                    )

    # The verified Dunkest mapping is mandatory for a valid gameweek forecast;
    # do not spend a network call on a raw NBA schedule that cannot establish
    # fantasy eligibility or turn identity.
    upcoming_schedule = fixture_schedule
    coach_snapshot_path = settings.data_path / "processed" / (
        f"coach_market_{settings.season_id}_gw{gw}.parquet"
    )
    coach_metadata = read_cache_metadata(coach_snapshot_path) or {}
    coach_market_snapshot = None
    if (
        coach_metadata.get("source") == "dunkest_pregame_coach_market_snapshot"
        and str(coach_metadata.get("season_id")) == str(settings.season_id)
        and int(coach_metadata.get("gameweek", -1)) == int(gw)
        and cache_valid(coach_snapshot_path, max_age_hours=settings.market_cache_max_age_hours)
    ):
        candidate = read_parquet(coach_snapshot_path)
        if (
            candidate is not None
            and len(candidate) >= 20
            and {"coach", "team", "coach_cr"}.issubset(candidate.columns)
            and candidate["team"].astype(str).str.upper().nunique() == len(candidate)
        ):
            coach_market_snapshot = candidate
    coach_data = get_coach_data(settings, gw, coach_market=coach_market_snapshot)
    if coach_market_snapshot is None:
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
    pre_match_tables = {
        "player_market.parquet": dk[market_columns].copy(),
        "fixture_mapping.parquet": fixture_schedule.copy(),
        "injuries.parquet": injuries.copy(),
        "coach_market.parquet": coach_data.copy(),
        "market_value_history.parquet": market_value_history.copy(),
        "plusvalenza_history.parquet": plusvalenza_history.copy(),
        "rookie_priors.parquet": rookie_priors.copy(),
    }
    snapshot_path = save_pre_match_snapshot(
        settings, gw,
        pre_match_tables,
        source="dunkest_live_forecast_inputs",
        metadata={
            "fixture_mapping_verified": bool(
                not fixture_schedule.empty
                and fixture_schedule.get("mapping_verified", pd.Series(False, index=fixture_schedule.index)).fillna(False).all()
            ),
            "injury_snapshot_rows": int(len(injuries)),
            "dvp_snapshot": dvp_snapshot,
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
