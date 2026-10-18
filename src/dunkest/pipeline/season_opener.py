from __future__ import annotations

from copy import copy
from pathlib import Path
import warnings

import numpy as np
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
from dunkest.data.cache import (
    cache_has_complete_collection,
    cache_valid,
    read_parquet as read_cached_parquet,
    write_parquet,
)
from dunkest.data.dunkest.opening import fetch_opening_coach_market, fetch_opening_market_pool
from dunkest.data.dunkest.official_pdk import (
    attach_official_pdk_labels,
    official_pdk_overlay_path,
)
from dunkest.data.nba import collector as nba
from dunkest.data.dunkest.fixtures import ensure_gameweek1_fixture_mapping, parse_fixture_bool
from dunkest.data.nba.collector import require_complete_collection
from dunkest.data.nba.prior_season import fetch_prior_season_game_logs
from dunkest.features.builder import build_feature_matrix
from dunkest.models.coach import predict_coach_points
from dunkest.models.predictor import (
    MIN_OFFICIAL_PDK_TRAINING_ROWS,
    predict_players,
    train_models,
)
from dunkest.models.multiseason_training import train_multiseason_models
from dunkest.models.rookie_prior import load_college_rookie_priors
from dunkest.names import player_key
from dunkest.optimize.milp import LineupSolution
from dunkest.pipeline.forecast import build_player_forecast
from dunkest.pipeline.optimize import run_optimize
from dunkest.rules.eligibility import filter_injured, unavailable_mask
from dunkest.report.artifacts import save_pre_match_snapshot


def _build_opening_market_value_history(
    player_logs: pd.DataFrame, market: pd.DataFrame, *, min_official_games: int = 5
) -> pd.DataFrame:
    """Build stable prior-season PDK/minute priors for the CR-market fallback.

    A one-game Dunkest stats snapshot is not a season-average prior: its PDK
    and minutes can be a single gameweek's outcome even when ``gp`` is the
    season-to-date count. Aggregate the certified prior-season game logs by
    player instead, using official Dunkest PDK when at least ``min_official_games``
    are available and the NBA-scoring proxy otherwise. Current Lineups CRs are
    used only to form the price/role peer groups for players without history.
    """
    required = {"PLAYER_NAME", "MIN", "PDK"}
    if player_logs is None or player_logs.empty or not required.issubset(player_logs.columns):
        return pd.DataFrame(columns=[
            "player_name", "pdk", "min", "cr", "gp", "role", "pdk_reference_source",
        ])
    if market is None or market.empty or not {"player_name", "cr"}.issubset(market.columns):
        return pd.DataFrame(columns=[
            "player_name", "pdk", "min", "cr", "gp", "role", "pdk_reference_source",
        ])

    logs = player_logs.copy()
    logs["_key"] = logs["PLAYER_NAME"].map(player_key)
    logs["_minutes"] = pd.to_numeric(logs["MIN"], errors="coerce")
    logs["_proxy_pdk"] = pd.to_numeric(logs["PDK"], errors="coerce")
    official = pd.to_numeric(
        logs.get("PDK_OFFICIAL_VALID", pd.Series(float("nan"), index=logs.index)),
        errors="coerce",
    ).replace([float("inf"), -float("inf")], float("nan"))
    logs["_official_pdk"] = official
    logs = logs.loc[
        logs["_key"].ne("") & logs["_minutes"].gt(0)
        & (logs["_proxy_pdk"].notna() | logs["_official_pdk"].notna())
    ].copy()

    market_rows = market.copy()
    market_rows["_key"] = market_rows["player_name"].map(player_key)
    market_rows["cr"] = pd.to_numeric(market_rows["cr"], errors="coerce")
    role_column = "role" if "role" in market_rows.columns else "position"
    if role_column not in market_rows:
        market_rows["role"] = ""
    else:
        market_rows["role"] = market_rows[role_column].astype(str).str.upper().replace({"A": "F"})
    market_rows = market_rows.loc[
        market_rows["_key"].ne("") & market_rows["cr"].gt(0)
    ].drop_duplicates("_key", keep="last")
    market_lookup = market_rows.set_index("_key")

    rows: list[dict[str, object]] = []
    for key, group in logs.groupby("_key", sort=False):
        if key not in market_lookup.index:
            continue
        official_rows = group.loc[group["_official_pdk"].notna()]
        if len(official_rows) >= int(min_official_games):
            selected = official_rows
            pdk_source = "official_dunkest_pdk_mean"
            pdk_values = selected["_official_pdk"]
        else:
            selected = group.loc[group["_proxy_pdk"].notna()]
            pdk_source = "nba_boxscore_proxy_mean"
            pdk_values = selected["_proxy_pdk"]
        if selected.empty or pdk_values.empty:
            continue
        market_row = market_lookup.loc[key]
        if isinstance(market_row, pd.DataFrame):
            market_row = market_row.iloc[-1]
        pdk_mean = pd.to_numeric(pdk_values, errors="coerce").mean()
        minutes_mean = pd.to_numeric(selected["_minutes"], errors="coerce").mean()
        if not np.isfinite(pdk_mean) or pdk_mean <= 0 or not np.isfinite(minutes_mean) or minutes_mean <= 0:
            continue
        rows.append({
            "player_name": str(market_row["player_name"]),
            "pdk": float(pdk_mean),
            "min": float(minutes_mean),
            "cr": float(market_row["cr"]),
            "gp": int(len(selected)),
            "role": str(market_row.get("role", "")),
            "pdk_reference_source": pdk_source,
        })
    return pd.DataFrame(rows, columns=[
        "player_name", "pdk", "min", "cr", "gp", "role", "pdk_reference_source",
    ])


def _load_opening_credit_history(settings: Settings) -> pd.DataFrame:
    """Load prior-season Dunkest player rates, including the legacy cache name.

    Prefer the season-qualified artifact. The legacy artifact is accepted only
    when it contains the fields required for rate/minute priors; it is never
    used as a current-season market or target source.
    """
    processed = settings.data_path / "processed"
    candidates = [
        processed / f"dunkest_players_{settings.opening_prior_season_id}_gw35.parquet",
        processed / "dunkest_players_gw35.parquet",
    ]
    required = {"player_name", "pdk", "min", "cr"}
    for path in candidates:
        if not path.is_file():
            continue
        try:
            history = pd.read_parquet(path)
        except Exception as exc:
            warnings.warn(
                f"Storico prezzi Dunkest non leggibile ({path.name}): {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        if history.empty or not required.issubset(history.columns):
            warnings.warn(
                f"Storico prezzi Dunkest ignorato ({path.name}): archivio vuoto "
                f"o colonne mancanti ({', '.join(sorted(required - set(history.columns)))}).",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        valid_rates = (
            pd.to_numeric(history["pdk"], errors="coerce").gt(0)
            & pd.to_numeric(history["min"], errors="coerce").gt(0)
            & pd.to_numeric(history["cr"], errors="coerce").gt(0)
        )
        if not valid_rates.any():
            warnings.warn(
                f"Storico prezzi Dunkest ignorato ({path.name}): nessuna riga con PDK, "
                "minuti e crediti positivi.",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        if path.name == "dunkest_players_gw35.parquet":
            warnings.warn(
                "Uso lo snapshot storico Dunkest legacy dunkest_players_gw35.parquet "
                "come prior della stagione precedente: manca il file con nome versionato.",
                RuntimeWarning,
                stacklevel=2,
            )
        return history.copy()
    warnings.warn(
        "Storico prezzi Dunkest della stagione precedente non disponibile: le previsioni "
        "proseguiranno senza prior di mercato.",
        RuntimeWarning,
        stacklevel=2,
    )
    return pd.DataFrame()


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
            value = parse_fixture_bool(
                fixture.get(eligible_column, fixture.get("fantasy_eligible", False))
            )
            if value is True:
                team = str(fixture.get(team_column, "")).strip().upper()
                if team:
                    verified.add(team)
    return verified


def _require_complete_score_bearing_teams(
    fixtures: pd.DataFrame, market_teams: set[str]
) -> set[str]:
    """Require an explicit eligible/ineligible state for every market team.

    Teams explicitly marked ineligible (for example, at rest) are validly
    accounted for but are not returned as score-bearing teams. Unknown status
    is different from an explicit rest status and still blocks the run.
    """
    verified = _verified_gameweek_teams(fixtures)
    observed: set[str] = set()
    if fixtures is not None and not fixtures.empty:
        for _, fixture in fixtures.iterrows():
            for team_column, eligible_column in (
                ("home_team", "home_team_eligible"),
                ("away_team", "away_team_eligible"),
            ):
                value = parse_fixture_bool(
                    fixture.get(eligible_column, fixture.get("fantasy_eligible", None))
                )
                team = str(fixture.get(team_column, "")).strip().upper()
                if team and value is not None:
                    observed.add(team)
    missing = sorted(market_teams - observed)
    if not market_teams or missing:
        raise RuntimeError(
            "Calendario Dunkest G1 non verificato: stato eleggibilità esplicito per "
            f"{len(market_teams.intersection(observed))}/{len(market_teams)} squadre. "
            f"Stati mancanti/non validi: {', '.join(missing[:12]) or 'listino squadre assente'}. "
            "Non genero rose con fixture o coach non verificati. Riesegui lo scraping "
            "Lineups e verifica gli stati delle squadre."
        )
    return verified


def _verified_matchups_by_team(fixtures: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Build a one-to-one team → verified score-bearing matchup index."""
    matchups: dict[str, dict[str, object]] = {}
    if fixtures is None or fixtures.empty:
        return matchups
    for _, fixture in fixtures.iterrows():
        if parse_fixture_bool(fixture.get("mapping_verified", False)) is not True:
            continue
        if parse_fixture_bool(fixture.get("fantasy_eligible", False)) is not True:
            continue
        turn_value = pd.to_numeric(fixture.get("dunkest_turn"), errors="coerce")
        if pd.isna(turn_value):
            continue
        for team_column, eligible_column, opponent_column in (
            ("home_team", "home_team_eligible", "away_team"),
            ("away_team", "away_team_eligible", "home_team"),
        ):
            eligible = parse_fixture_bool(fixture.get(eligible_column, False))
            if eligible is not True:
                continue
            team = str(fixture.get(team_column, "")).strip().upper()
            opponent = str(fixture.get(opponent_column, "")).strip().upper()
            if not team or not opponent:
                continue
            matchup = {
                "opponent": opponent,
                "dunkest_turn": int(turn_value),
                "nba_game_id": str(fixture.get("nba_game_id", "")),
            }
            if team in matchups and matchups[team] != matchup:
                raise RuntimeError(
                    f"Calendario Dunkest ambiguo per {team}: più matchup validi nella stessa giornata."
                )
            matchups[team] = matchup
    return matchups


def _attach_verified_player_matchups(
    predictions: pd.DataFrame, fixtures: pd.DataFrame
) -> pd.DataFrame:
    """Validate every predicted player against the official fixture bridge."""
    if predictions.empty:
        return predictions.copy()
    required = {"team", "player_name"}
    if not required.issubset(predictions.columns):
        raise RuntimeError("Predizioni giocatori prive di team/player_name: impossibile verificare i matchup.")
    matchups = _verified_matchups_by_team(fixtures)
    out = predictions.copy()
    team_keys = out["team"].astype(str).str.strip().str.upper()
    expected_turn = team_keys.map(lambda team: matchups.get(team, {}).get("dunkest_turn"))
    expected_opponent = team_keys.map(lambda team: matchups.get(team, {}).get("opponent"))
    expected_game_id = team_keys.map(lambda team: matchups.get(team, {}).get("nba_game_id"))
    unmapped = expected_turn.isna()
    if unmapped.any():
        missing = sorted(team_keys.loc[unmapped].unique())
        raise RuntimeError("Giocatori senza matchup Dunkest verificato: " + ", ".join(missing[:12]))
    if "dunkest_turn" in out:
        observed_turn = pd.to_numeric(out["dunkest_turn"], errors="coerce")
        mismatch = observed_turn.notna() & observed_turn.ne(expected_turn.astype(int))
        if mismatch.any():
            examples = out.loc[mismatch, ["player_name", "team", "dunkest_turn"]].head(8)
            raise RuntimeError("Turno giocatori incoerente con il calendario verificato:\n" + examples.to_string(index=False))
    if "opponent" in out:
        observed_opponent = out["opponent"].fillna("").astype(str).str.strip().str.upper()
        mismatch = observed_opponent.ne("") & observed_opponent.ne(expected_opponent)
        if mismatch.any():
            examples = out.loc[mismatch, ["player_name", "team", "opponent"]].head(8)
            raise RuntimeError("Avversario giocatori incoerente con il calendario verificato:\n" + examples.to_string(index=False))
    out["opponent"] = expected_opponent.to_numpy()
    out["dunkest_turn"] = expected_turn.astype(int).to_numpy()
    out["nba_game_id"] = expected_game_id.to_numpy()
    out["fixture_source"] = "verified_dunkest_lineups"
    return out


def _require_finite_player_forecasts(predictions: pd.DataFrame) -> pd.DataFrame:
    """Reject missing player score forecasts before they reach coaches or the solver."""
    if predictions.empty or not {"player_name", "expected_pdk"}.issubset(predictions.columns):
        raise RuntimeError("Previsioni giocatori assenti o prive di expected_pdk.")
    out = predictions.copy()
    expected = pd.to_numeric(out["expected_pdk"], errors="coerce")
    invalid = ~np.isfinite(expected.to_numpy(dtype=float, na_value=np.nan))
    if invalid.any():
        names = out.loc[invalid, "player_name"].astype(str).head(8).tolist()
        raise RuntimeError(
            "Forecast PDK giocatore mancanti o non finiti: "
            + ", ".join(names)
            + ". Interrompo la generazione invece di assegnare punteggi zero."
        )
    out["expected_pdk"] = expected.astype(float)
    return out


def _filter_coaches_to_target_turn(
    coaches: pd.DataFrame,
    fixtures: pd.DataFrame,
    target_turn: int | None,
) -> pd.DataFrame:
    """Keep coaches with a verified opponent, and for a turn-specific run that turn only."""
    if coaches.empty:
        return coaches.copy()
    if "team" not in coaches:
        raise RuntimeError("Listino coach privo della squadra NBA: impossibile verificare i matchup.")
    matchups = _verified_matchups_by_team(fixtures)
    out = coaches.copy()
    team_keys = out["team"].astype(str).str.strip().str.upper()
    expected_turn = team_keys.map(lambda team: matchups.get(team, {}).get("dunkest_turn"))
    expected_opponent = team_keys.map(lambda team: matchups.get(team, {}).get("opponent"))
    valid = expected_turn.notna()
    if "dunkest_turn" in out:
        observed_turn = pd.to_numeric(out["dunkest_turn"], errors="coerce")
        mismatch = valid & observed_turn.notna() & observed_turn.ne(expected_turn)
        if mismatch.any():
            examples = out.loc[mismatch, ["coach", "team", "dunkest_turn"]].head(8)
            raise RuntimeError("Turno coach incoerente con il calendario verificato:\n" + examples.to_string(index=False))
    if "opponent" in out:
        observed_opponent = out["opponent"].fillna("").astype(str).str.strip().str.upper()
        mismatch = valid & observed_opponent.ne("") & observed_opponent.ne(expected_opponent)
        if mismatch.any():
            examples = out.loc[mismatch, ["coach", "team", "opponent"]].head(8)
            raise RuntimeError("Avversario coach incoerente con il calendario verificato:\n" + examples.to_string(index=False))
    out = out.loc[valid].copy()
    team_keys = out["team"].astype(str).str.strip().str.upper()
    out["opponent"] = team_keys.map(lambda team: matchups[team]["opponent"])
    out["dunkest_turn"] = team_keys.map(lambda team: int(matchups[team]["dunkest_turn"])).astype(int)
    out["nba_game_id"] = team_keys.map(lambda team: matchups[team]["nba_game_id"])
    if target_turn is not None:
        out = out.loc[out["dunkest_turn"].eq(int(target_turn))].copy()
        if out.empty:
            raise RuntimeError(
                f"Nessun coach con matchup verificato nel Turno {target_turn}; non seleziono allenatori di altri turni."
            )
    return out.reset_index(drop=True)


def get_opening_market(
    settings: Settings,
    credits_file: Path | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    proxy_tag = "_proxy" if settings.opening_use_pdk_cr_proxy else ""
    path = settings.data_path / "processed" / (
        f"opening_market_{settings.season_id}_{settings.opening_prior_season_id}_gw1{proxy_tag}.parquet"
    )
    if (
        not force_refresh
        and credits_file is None
        and cache_valid(path, max_age_hours=settings.market_cache_max_age_hours)
    ):
        cached = read_cached_parquet(path)
        if cached is not None and not cached.empty:
            return cached
    df = fetch_opening_market_pool(
        settings,
        credits_file=credits_file,
        use_pdk_cr_proxy=settings.opening_use_pdk_cr_proxy,
        pdk_cr_scale=settings.opening_pdk_cr_scale,
    )
    write_parquet(df, path, source="opening_market", gameweek=1)
    return df


def _select_turn_specific_lineup_annotations(market: pd.DataFrame) -> pd.DataFrame:
    """Use the lineup annotation from each player's verified Dunkest turn."""
    out = market.copy()
    if "dunkest_turn" not in out:
        return out
    turns = pd.to_numeric(out["dunkest_turn"], errors="coerce")
    current_status = out.get("status", pd.Series("", index=out.index)).fillna("").astype(str).str.upper()
    current_group = out.get("lineup_group", pd.Series("", index=out.index)).fillna("").astype(str).str.upper()
    hard_out = current_status.isin({"OUT", "INJURED", "UNAVAILABLE"}) | current_group.eq("INDISPONIBILI")
    for turn in (1, 2, 3):
        mask = turns.eq(turn)
        group_col = f"lineup_group_turn{turn}"
        starter_col = f"starter_turn{turn}"
        status_col = f"status_turn{turn}"
        if group_col in out:
            selected_group = out[group_col].fillna("").astype(str).str.strip().str.upper()
            out.loc[mask & ~hard_out, "lineup_group"] = selected_group.loc[mask & ~hard_out]
        if starter_col in out:
            if "starter" not in out:
                out["starter"] = pd.Series(pd.NA, index=out.index, dtype="object")
            else:
                out["starter"] = out["starter"].astype("object")
            out.loc[mask & ~hard_out, "starter"] = out.loc[mask & ~hard_out, starter_col].astype("object")
        if status_col in out:
            selected_status = out[status_col].fillna("").astype(str).str.strip().str.upper()
            out.loc[mask & ~hard_out, "status"] = selected_status.loc[mask & ~hard_out]
    out.loc[hard_out, "lineup_group"] = "INDISPONIBILI"
    out.loc[hard_out, "status"] = "OUT"
    if "starter" in out:
        out.loc[hard_out, "starter"] = False
    return out


def _model_artifact_metadata(models: dict) -> dict:
    """Keep training provenance in the season-opener manifest without serializing estimators."""
    metadata = {name: None for name in models if not name.startswith("_")}
    for key in (
        "_feature_cols",
        "_training_target",
        "_training_target_source",
        "_training_rows",
        "_training_rows_before_target_filter",
        "_official_labels_available_before_filter",
        "_training_date_min_utc",
        "_training_date_max_utc",
        "_training_seasons",
        "_training_dataset",
        "_training_minute_labels_dataset",
        "_training_minute_labels_matched_rows",
        "_training_label_certification",
        "_sample_weighted_training",
        "_sample_weight_mean",
        "_residual_std",
        "_residual_q10",
        "_residual_q50",
        "_residual_q90",
        "_residual_quantiles_by_prediction_band",
        "_rookie_policy",
        "_prediction_is_absolute",
        "_weights",
        "_projection_weights",
        "_calibration_samples",
        "_interval_diagnostics",
        "_interval_diagnostic_scope",
    ):
        if key in models:
            metadata[key] = models[key]
    return metadata


def run_season_opener(
    settings: Settings,
    credits_file: Path | None = None,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[LineupSolution], dict]:
    settings = settings_for_season_opener(settings, budget=settings.budget)
    # A season-opener is one optimization for the full Dunkest Gameweek 1.
    # The scraper may read one Turno, but that must not filter the coach pool.
    settings.target_dunkest_turn = None

    market = get_opening_market(settings, credits_file=credits_file, force_refresh=force_refresh)
    if market.empty:
        raise RuntimeError(
            "Dunkest non ha ancora restituito il listone della stagione target. "
            "Riprova quando la sezione Lineup/Statistiche espone i CR 2026/27 "
            "oppure passa un CSV con player_name, cr, team e role."
        )
    # Validate the official Giornata-1 bridge before loading/training models or
    # refreshing historical data. A stale/incomplete Lineups capture should fail
    # fast, without spending minutes on work that cannot produce a safe lineup.
    future_schedule = ensure_gameweek1_fixture_mapping(settings)
    market_teams = (
        set(market["team_code"].dropna().astype(str).str.strip().str.upper())
        if "team_code" in market else set()
    )
    verified_teams = _require_complete_score_bearing_teams(future_schedule, market_teams)
    n_games = int(future_schedule["nba_game_id"].nunique()) if "nba_game_id" in future_schedule else len(future_schedule)
    print(f"Fixture G1: {n_games} partite, {len(future_schedule)} righe mapping; matchup validi per {len(verified_teams)} squadre")

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

    official_pdk_overlay = official_pdk_overlay_path(
        settings.data_path, settings.feature_season
    )
    player_logs = attach_official_pdk_labels(
        player_logs, settings.data_path, settings.feature_season
    )
    official_pdk_overlay_label_rows = int(pd.to_numeric(
        player_logs.get("PDK_OFFICIAL_VALID", pd.Series(dtype=float)), errors="coerce"
    ).notna().sum())

    # Use official historical Dunkest PDK when available; otherwise derive the
    # season mean from full 2025/26 NBA box scores with Dunkest's scoring rules.
    if not player_logs.empty and {"PLAYER_NAME", "PDK"}.issubset(player_logs.columns):
        # Keep a proxy mean for players without enough valid official games.
        prior_means = player_logs.groupby("PLAYER_NAME")["PDK"].mean().rename("PDK").to_frame()
        official = pd.to_numeric(
            player_logs.get("PDK_OFFICIAL_VALID", pd.Series(index=player_logs.index, dtype=float)),
            errors="coerce",
        ).replace([float("inf"), -float("inf")], float("nan"))
        official_count = int(official.notna().sum())
        if official_count >= MIN_OFFICIAL_PDK_TRAINING_ROWS:
            official_frame = player_logs[["PLAYER_NAME"]].copy()
            official_frame["official_pdk"] = official
            official_stats = official_frame.groupby("PLAYER_NAME")["official_pdk"].agg(
                ["mean", "count"]
            )
            reliable_official = official_stats.loc[official_stats["count"] >= 5, "mean"]
            prior_means.loc[reliable_official.index, "PDK"] = reliable_official
        prior_means = prior_means.reset_index()
        prior_means["key"] = prior_means["PLAYER_NAME"].map(player_key)
        prior_map = prior_means.drop_duplicates("key").set_index("key")["PDK"]
        market["key"] = market["player_name"].map(player_key)
        market["prior_pdk"] = pd.to_numeric(market["prior_pdk"], errors="coerce").fillna(
            market["key"].map(prior_map)
        )
        market = market.drop(columns="key")

    # Refresh the injury page on every season-opener run. The visible Lineups
    # snapshot is not a complete league-wide injury source.
    injuries = get_injuries(settings, force_refresh=True) if settings.use_injuries else pd.DataFrame()
    official_out_count = int(unavailable_mask(injuries).sum()) if not injuries.empty else 0
    if settings.use_injuries:
        # get_opening_market already applies the official injury filter. Count
        # matches against the unfiltered scraped market when available; otherwise
        # the diagnostic would misleadingly report zero OUT matches because
        # those players have already been removed before this point.
        market_for_injury_match = market.copy()
        if "team" not in market_for_injury_match and "team_code" in market_for_injury_match:
            market_for_injury_match = market_for_injury_match.rename(columns={"team_code": "team"})
        raw_market_path = settings.data_path / "current_lineups_market.csv"
        if raw_market_path.is_file():
            try:
                raw_market = pd.read_csv(raw_market_path)
                if {"player_name", "team"}.issubset(raw_market.columns):
                    market_for_injury_match = raw_market
            except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
                warnings.warn(
                    f"Listino grezzo non leggibile per la diagnostica infortuni; "
                    f"uso il listino filtrato disponibile: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        market_after_official_out = filter_injured(market_for_injury_match, injuries)
        matched_out_count = len(market_for_injury_match) - len(market_after_official_out)
        unmatched_out_count = max(official_out_count - matched_out_count, 0)
        print(
            f"Infortuni ufficiali aggiornati: {len(injuries)} record; "
            f"{official_out_count} OUT, {matched_out_count} associati al listino, "
            f"{unmatched_out_count} non associati."
        )
        capture_path = settings.data_path / "lineups_gw1_capture.json"
        if not capture_path.is_file():
            raise RuntimeError(
                "Manca una cattura Lineups completa dei Turni 1, 2 e 3. "
                "Riesegui senza --no-lineups-scrape: la Giornata 1 richiede "
                "un controllo disponibilità per ogni turno."
            )
        import json
        from datetime import datetime, timezone
        try:
            capture = json.loads(capture_path.read_text(encoding="utf-8"))
            captured_turns = sorted({int(turn) for turn in capture.get("turns_captured", [])})
            capture_scope = str(capture.get("capture_scope", "")).strip()
            captured_at = datetime.fromisoformat(str(capture["captured_at"]))
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=timezone.utc)
            capture_age_hours = (datetime.now(timezone.utc) - captured_at.astimezone(timezone.utc)).total_seconds() / 3600
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Manifest disponibilità Lineups G1 non valido; ripeti lo scraping dei tre turni.") from exc

        # New captures visit every fixture in one pass and identify their scope
        # explicitly. Validate the adjacent market metadata before accepting
        # that format; legacy manifests still need turns_captured=[1, 2, 3].
        full_week_capture_valid = False
        if capture_scope == "full_gameweek_all_turns":
            market_path = Path(credits_file) if credits_file is not None else settings.data_path / "current_lineups_market.csv"
            market_metadata_path = market_path.with_suffix(market_path.suffix + ".meta.json")
            try:
                market_metadata = json.loads(market_metadata_path.read_text(encoding="utf-8"))
                fixture_total = int(market_metadata.get("fixtures_total", 0))
                fixture_scanned = int(market_metadata.get("fixtures_scanned", -1))
                market_fetched_at = datetime.fromisoformat(str(market_metadata["fetched_at"]))
                if market_fetched_at.tzinfo is None:
                    market_fetched_at = market_fetched_at.replace(tzinfo=timezone.utc)
                market_age_hours = (
                    datetime.now(timezone.utc) - market_fetched_at.astimezone(timezone.utc)
                ).total_seconds() / 3600
                full_week_capture_valid = (
                    market_metadata.get("capture_scope") == "full_gameweek_all_turns"
                    and market_metadata.get("all_fixtures_covered") is True
                    and fixture_total > 0
                    and fixture_scanned == fixture_total
                    and not market_metadata.get("lineup_fixtures_unverified", [])
                    and -1 <= market_age_hours <= 24
                )
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                full_week_capture_valid = False

        turns_covered = captured_turns == [1, 2, 3] or full_week_capture_valid
        if not turns_covered or capture_age_hours < -1 or capture_age_hours > 24:
            raise RuntimeError(
                "La cattura delle disponibilità Lineups non copre i tre turni oppure il mercato "
                "non certifica tutte le fixture; oppure i dati hanno più di 24 ore. "
                "Riesegui lo scraping completo della Giornata 1."
            )
    if settings.use_injuries and injuries.empty:
        raise RuntimeError(
            "Archivio indisponibilità vuoto: interrompo season-opener per evitare "
            "rose con giocatori out. Verifica lo scraping Lineups e gli override in "
            "data/injury_overrides.csv."
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
    market = _select_turn_specific_lineup_annotations(market)
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
    if settings.opening_multiseason_training:
        models, _training_features = train_multiseason_models(settings)
    else:
        models, _ = train_models(settings, features)
    credit_history = _build_opening_market_value_history(player_logs, market)
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

    forecast = build_player_forecast(
        settings,
        models,
        features,
        market,
        injuries,
        market_value_history=credit_history,
        plusvalenza_history=plusvalenza_history,
        college_rookie_priors=rookie_priors,
        require_injury_snapshot=settings.use_injuries,
    )
    preds = _require_finite_player_forecasts(forecast.raw)
    # Preserve hard-outs as zero-value team members for coach-strength
    # estimates; filtering them first can make a whole franchise disappear.
    coach_strength_forecasts = preds.copy()
    predicted_count = len(preds)
    preds = forecast.eligible.copy()
    preds.attrs["forecast_degradations"] = list(forecast.degradations)
    preds = _attach_verified_player_matchups(preds, future_schedule)
    available_keys = set(preds["player_name"].map(player_key))
    excluded = ~coach_strength_forecasts["player_name"].map(player_key).isin(available_keys)
    coach_strength_forecasts.loc[excluded, "expected_pdk"] = 0.0
    extra_excluded_after_prediction = predicted_count - len(preds)
    print(
        f"OUT ufficiali associati al listino: {matched_out_count if settings.use_injuries else 0}; "
        f"ulteriori esclusioni esplicite dopo le previsioni: {extra_excluded_after_prediction}. "
        "Gli OUT già hanno P(play)=0 e non sono eleggibili all'ottimizzazione."
    )

    mkt = market.drop_duplicates("player_name").copy()
    mkt["key"] = mkt["player_name"].map(player_key)
    prior_map = mkt.set_index("key")["prior_pdk"]
    preds["prior_pdk"] = preds["player_name"].map(player_key).map(prior_map)

    coach_market = fetch_opening_coach_market(credits_file)
    coach_data = get_coach_data(
        settings,
        1,
        force_refresh=force_refresh or not coach_market.empty,
        coach_market=coach_market if not coach_market.empty else None,
    )
    if coach_data.empty:
        raise RuntimeError(
            "Dati coach assenti: nessuna proiezione matchup può essere calcolata. "
            "Aggiorna il listino e le fixture prima di ottimizzare."
        )
    coach_df = predict_coach_points(
        coach_data,
        team_logs=team_logs if not team_logs.empty else None,
        upcoming_schedule=future_schedule,
        player_logs=player_logs,
        player_forecasts=coach_strength_forecasts,
        gameweek=1,
        use_model=settings.use_coach_model,
    )
    if coach_df.empty or "expected_coach_pdk" not in coach_df:
        raise RuntimeError(
            "Proiezioni coach non disponibili per la Giornata 1; interrompo "
            "l'ottimizzazione invece di sostituirle con punteggi artificiali."
        )
    save_coach_market_snapshot(
        settings, coach_data if not coach_data.empty else coach_df, 1
    )
    prematch_market_columns = [
        column for column in (
            "player_name", "team_code", "team", "cr", "role", "position", "prior_pdk", "opponent",
            "dunkest_turn", "nba_game_id", "game_datetime_utc", "is_home", "gameweek",
            "lineup_group", "status", "starter", "lineup_group_turn1", "lineup_group_turn2",
            "lineup_group_turn3", "starter_turn1", "starter_turn2", "starter_turn3",
            "status_turn1", "status_turn2", "status_turn3",
        ) if column in market.columns
    ]
    save_pre_match_snapshot(
        settings, 1,
        {
            "player_market.parquet": market[prematch_market_columns].copy(),
            "fixture_mapping.parquet": future_schedule.copy(),
            "injuries.parquet": injuries.copy(),
            "coach_market.parquet": coach_data.copy(),
            "market_value_history.parquet": credit_history.copy(),
            "plusvalenza_history.parquet": plusvalenza_history.copy(),
            "rookie_priors.parquet": rookie_priors.copy(),
        },
        source="dunkest_season_opener_forecast_inputs",
        metadata={
            "fixture_mapping_verified": bool(
                not future_schedule.empty
                and future_schedule.get("mapping_verified", pd.Series(False, index=future_schedule.index)).fillna(False).all()
            ),
            "injury_snapshot_rows": int(len(injuries)),
        },
    )
    if not coach_df.empty:
        coach_df = coach_df.groupby("team", as_index=False).first()
    coach_df = _filter_coaches_to_target_turn(coach_df, future_schedule, None)
    print(
        f"Matchup verificati: {len(preds)} giocatori; "
        f"{len(coach_df)} coach eleggibili per l'intera Giornata 1 "
        "(Turni 1, 2 e 3)."
    )

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
        "model_artifact_metadata": _model_artifact_metadata(models),
        "official_pdk_overlay_source": (
            str(official_pdk_overlay) if official_pdk_overlay is not None else None
        ),
        "official_pdk_overlay_label_rows": official_pdk_overlay_label_rows,
        "eligible_players": len(preds),
        "projection_weights": models.get("_projection_weights", {}),
        "projection_calibration_samples": models.get("_calibration_samples", 0),
        "credit_proxy_reference_rows": len(credit_history),
        "credit_proxy_reference_source": (
            "prior_season_game_logs_official_pdk_mean_with_proxy_fallback"
            if not credit_history.empty else "unavailable_no_market_value_prior"
        ),
        "credit_proxy_reference_official_players": int(
            credit_history.get("pdk_reference_source", pd.Series(dtype=str))
            .eq("official_dunkest_pdk_mean").sum()
        ),
        "credit_proxy_reference_proxy_players": int(
            credit_history.get("pdk_reference_source", pd.Series(dtype=str))
            .eq("nba_boxscore_proxy_mean").sum()
        ),
        "plusvalenza_reference_rows": len(plusvalenza_history),
        "plusvalenza_reference_gameweeks": sorted(
            pd.to_numeric(plusvalenza_history.get("gameweek"), errors="coerce")
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        ) if "gameweek" in plusvalenza_history else [],
        "plusvalenza_reference_season_coverage": {
            str(int(season)): {
                "rows": int(len(group)),
                "teams": int(group["team_code"].astype(str).str.upper().nunique()),
                "gameweeks": int(pd.to_numeric(group["gameweek"], errors="coerce").nunique()),
                "players": int(group["player_name"].map(player_key).nunique()),
            }
            for season, group in plusvalenza_history.groupby("season_id")
        } if {"season_id", "team_code", "gameweek", "player_name"}.issubset(plusvalenza_history.columns) else {},
        "plusvalenza_reference_incomplete_seasons": [
            str(int(season)) if str(season).replace(".0", "").isdigit() else str(season)
            for season, group in plusvalenza_history.groupby("season_id")
            if group["team_code"].astype(str).str.upper().nunique() < 28
        ] if {"season_id", "team_code"}.issubset(plusvalenza_history.columns) else [],
        "plusvalenza_reference_min_teams_required": 28,
        "plusvalenza_model_excluded_incomplete_seasons": [
            str(int(season)) if str(season).replace(".0", "").isdigit() else str(season)
            for season, group in plusvalenza_history.groupby("season_id")
            if group["team_code"].astype(str).str.upper().nunique() < 28
        ] if {"season_id", "team_code"}.issubset(plusvalenza_history.columns) else [],
        "plusvalenza_model_training_rows": int(pd.to_numeric(
            preds.get("plusvalenza_training_rows", pd.Series(dtype=float)), errors="coerce"
        ).max()) if not preds.empty else 0,
        "plusvalenza_model_validation_rows": int(pd.to_numeric(
            preds.get("plusvalenza_validation_rows", pd.Series(dtype=float)), errors="coerce"
        ).max()) if not preds.empty else 0,
        "plusvalenza_model_cv_mae": float(pd.to_numeric(
            preds.get("plusvalenza_cv_mae", pd.Series(dtype=float)), errors="coerce"
        ).max()) if not preds.empty and pd.to_numeric(
            preds.get("plusvalenza_cv_mae", pd.Series(dtype=float)), errors="coerce"
        ).notna().any() else None,
        "plusvalenza_model_baseline_mae": float(pd.to_numeric(
            preds.get("plusvalenza_baseline_mae", pd.Series(dtype=float)), errors="coerce"
        ).max()) if not preds.empty and pd.to_numeric(
            preds.get("plusvalenza_baseline_mae", pd.Series(dtype=float)), errors="coerce"
        ).notna().any() else None,
        "official_cr_count": int(market.get("cr_is_official", pd.Series(dtype=bool)).sum())
        if "cr_is_official" in market.columns
        else 0,
        "feature_season": settings.feature_season,
        "budget": settings.budget,
    }
    return preds, coach_df, market, solutions, meta
