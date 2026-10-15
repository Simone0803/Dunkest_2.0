from __future__ import annotations

from copy import copy
from datetime import datetime, timezone
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from dunkest.config import Settings
from dunkest.data.cache import cache_valid, read_cache_metadata, read_parquet, write_parquet
from dunkest.data.dunkest import client as dk_module
from dunkest.data.dunkest.fixtures import get_fixture_mapping
from dunkest.data.nba import collector as nba
from dunkest.names import player_key
from dunkest.rules.coach import coach_points_from_game

PLUSVALENZA_SAMPLE_GAMEWEEKS = tuple(range(1, 92))
# A genuine NBA Dunkest gameweek should expose nearly the entire 30-team league.
# Some non-NBA competitions reuse NBA team codes for a handful of players; one
# matching code is not enough to classify a season as NBA history.
MIN_NBA_TEAMS_FOR_PLUSVALENZA = 28
logger = logging.getLogger(__name__)


def _processed(settings: Settings, name: str) -> Path:
    return settings.data_path / "processed" / name


def _plusvalenza_season_team_coverage(history: pd.DataFrame | None) -> dict[str, int]:
    """Count distinct NBA team codes per season without trusting row volume."""
    if history is None or history.empty or not {"season_id", "team_code"}.issubset(history.columns):
        return {}
    team = history["team_code"].astype("string").str.strip().str.upper()
    team = team.mask(team.isna() | team.isin(["", "NAN", "NONE", "<NA>"]), pd.NA)
    coverage = history.assign(_nba_team=team).groupby("season_id")["_nba_team"].nunique(dropna=True)
    result: dict[str, int] = {}
    for season, count in coverage.items():
        try:
            number = float(season)
            label = str(int(number)) if number.is_integer() else str(season)
        except (TypeError, ValueError):
            label = str(season)
        result[label] = int(count)
    return result


def _has_complete_plusvalenza_season(history: pd.DataFrame | None) -> bool:
    """A usable cache must contain only seasons with broad NBA-team coverage."""
    coverage = _plusvalenza_season_team_coverage(history)
    return bool(coverage) and all(
        teams >= MIN_NBA_TEAMS_FOR_PLUSVALENZA for teams in coverage.values()
    )


def _check_live_market_freshness(settings: Settings, path: Path) -> None:
    """Reject timestamped Lineups exports that are too old; warn on legacy CSVs."""
    metadata = read_cache_metadata(path)
    if metadata is None:
        warnings.warn(
            f"Lineups market {path} has no freshness metadata; regenerate it to verify its age.",
            RuntimeWarning,
            stacklevel=2,
        )
        return
    try:
        fetched_at = datetime.fromisoformat(str(metadata["fetched_at"]))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        raise RuntimeError(f"Lineups market metadata is invalid: {path}") from None
    age_hours = (datetime.now(timezone.utc) - fetched_at.astimezone(timezone.utc)).total_seconds() / 3600
    if age_hours < 0 or age_hours > settings.market_cache_max_age_hours:
        raise RuntimeError(
            f"Lineups market is stale ({age_hours:.1f}h; limit "
            f"{settings.market_cache_max_age_hours:.1f}h): {path}. Refresh the Lineups scrape."
        )


def _merge_live_market_pool(season_players: pd.DataFrame, live_market: pd.DataFrame) -> pd.DataFrame:
    """Use the current Lineups market as the candidate universe and enrich it with season stats."""
    if live_market.empty:
        return season_players.copy()
    required = {"player_name", "cr", "position", "team_code"}
    missing = sorted(required.difference(live_market.columns))
    if missing:
        raise RuntimeError(
            "Lineups market missing candidate identity fields: " + ", ".join(missing)
        )

    market = live_market.copy()
    market["_market_key"] = market["player_name"].map(player_key)
    market["cr"] = pd.to_numeric(market["cr"], errors="coerce")
    market["position"] = market["position"].fillna("").astype(str).str.upper().replace({"A": "F"})
    market["team_code"] = market["team_code"].fillna("").astype(str).str.upper().str.strip()
    invalid = (
        market["player_name"].isna()
        | market["player_name"].astype(str).str.strip().eq("")
        | market["_market_key"].eq("")
        | ~np.isfinite(market["cr"].to_numpy(dtype=float, na_value=np.nan))
        | ~market["position"].isin({"G", "F", "C"})
        | market["team_code"].isin({"", "NAN", "NONE"})
    )
    if invalid.any():
        raise RuntimeError(
            "Lineups market contains player rows with missing or invalid name, CR, role, or team."
        )
    if market["_market_key"].eq("").any() or market["_market_key"].duplicated(keep=False).any():
        raise RuntimeError(
            "Lineups market contains blank or duplicate normalized player identities."
        )
    for column in ("lineup_group", "status"):
        if column not in market:
            market[column] = pd.NA

    season = season_players.copy()
    if season.empty:
        out = market.drop(columns="_market_key").copy()
        out["role"] = out["position"]
        return out
    if "player_name" not in season:
        raise RuntimeError("NBA season player table is missing player_name.")
    season["_market_key"] = season["player_name"].map(player_key)
    valid_season_keys = season["_market_key"].ne("")
    if season.loc[valid_season_keys, "_market_key"].duplicated(keep=False).any():
        raise RuntimeError("NBA season player table contains duplicate normalized player identities.")

    market_index = market.set_index("_market_key", drop=False)
    out = season.copy()
    for column in ("cr", "position", "team_code", "lineup_group", "status"):
        market_values = out["_market_key"].map(market_index[column])
        if column not in out:
            out[column] = market_values
        else:
            out[column] = market_values.combine_first(out[column])
    out["role"] = out["position"]

    known = set(out.loc[out["_market_key"].ne(""), "_market_key"])
    candidates_without_stats = market.loc[~market["_market_key"].isin(known)].copy()
    if not candidates_without_stats.empty:
        candidates_without_stats = candidates_without_stats.drop(columns="_market_key")
        candidates_without_stats["role"] = candidates_without_stats["position"]
        out = pd.concat([out.drop(columns="_market_key"), candidates_without_stats], ignore_index=True, sort=False)
    else:
        out = out.drop(columns="_market_key")
    return out


def save_player_credit_snapshot(
    settings: Settings, market: pd.DataFrame, gameweek: int
) -> None:
    required = {"player_name", "cr"}
    if not required.issubset(market.columns):
        return
    columns = [
        column
        for column in (
            "player_name", "team_code", "role", "cr", "official_plusvalenza",
            "lineup_group", "status", "dunkest_turn",
        )
        if column in market.columns
    ]
    snapshot = market[columns].copy()
    snapshot["cr"] = pd.to_numeric(snapshot["cr"], errors="coerce")
    if "official_plusvalenza" in snapshot:
        snapshot["official_plusvalenza"] = pd.to_numeric(
            snapshot["official_plusvalenza"], errors="coerce"
        )
    snapshot = snapshot.dropna(subset=["player_name", "cr"]).drop_duplicates(
        "player_name", keep="last"
    )
    snapshot["gameweek"] = int(gameweek)
    path = _processed(
        settings, f"player_credits_{settings.season_id}_gw{gameweek}.parquet"
    )
    write_parquet(
        snapshot,
        path,
        source="dunkest_market_credit_snapshot",
        season_id=settings.season_id,
        gameweek=gameweek,
        dunkest_turn=settings.target_dunkest_turn,
    )


def add_previous_credit_change(
    settings: Settings, market: pd.DataFrame, gameweek: int
) -> pd.DataFrame:
    out = market.copy()
    out["cr_change_last_gameweek"] = float("nan")
    if gameweek <= 1 or not {"player_name", "cr"}.issubset(out.columns):
        return out
    previous_path = _processed(
        settings, f"player_credits_{settings.season_id}_gw{gameweek - 1}.parquet"
    )
    previous = read_parquet(previous_path)
    if previous is None or not {"player_name", "cr"}.issubset(previous.columns):
        return out
    previous = previous.copy()
    previous["key"] = previous["player_name"].map(player_key)
    previous_cr = pd.to_numeric(previous.drop_duplicates("key", keep="last").set_index("key")["cr"], errors="coerce")
    current_cr = pd.to_numeric(out["cr"], errors="coerce")
    out["cr_change_last_gameweek"] = out["player_name"].map(player_key).map(previous_cr)
    out["cr_change_last_gameweek"] = current_cr - out["cr_change_last_gameweek"]
    return out


def add_official_plusvalenza(
    market: pd.DataFrame, gameweek_stats: pd.DataFrame | None
) -> pd.DataFrame:
    out = market.copy()
    out["official_plusvalenza"] = float("nan")
    if (
        gameweek_stats is None
        or gameweek_stats.empty
        or not {"player_name", "plus"}.issubset(gameweek_stats.columns)
        or "player_name" not in out
    ):
        return out
    weekly = gameweek_stats[["player_name", "plus"]].copy()
    weekly["key"] = weekly["player_name"].map(player_key)
    plus_by_player = pd.to_numeric(
        weekly.drop_duplicates("key", keep="last").set_index("key")["plus"],
        errors="coerce",
    )
    out["official_plusvalenza"] = out["player_name"].map(player_key).map(plus_by_player)
    return out


NBA_TEAM_CODES = {
    "ATL", "BOS", "BKN", "BRK", "CHA", "CHO", "CHI", "CLE", "DAL", "DEN",
    "DET", "GSW", "GS", "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL",
    "MIN", "NOP", "NO", "NYK", "OKC", "ORL", "PHI", "PHX", "POR", "SAC",
    "SAS", "TOR", "UTA", "WAS", "NJN", "NOH", "NOK", "SEA",
}


def get_plusvalenza_history(
    settings: Settings,
    season_id: str | None = None,
    force_refresh: bool = False,
    through_gameweek: int | None = None,
) -> pd.DataFrame:
    """Download official NBA PDK/PLUS outcomes from multiple Dunkest seasons.

    Dunkest season IDs are shared across competitions and are not consecutive
    NBA years. Candidate seasons are therefore verified using NBA team codes
    in the official statistics response before they enter the training set.
    """
    active_season = str(season_id or settings.season_id)
    through_gameweek = settings.target_gameweek - 1 if through_gameweek is None else int(through_gameweek)
    if through_gameweek < 0:
        raise ValueError("through_gameweek must be nonnegative")
    try:
        active_number = int(active_season)
    except ValueError as exc:
        raise ValueError(f"Dunkest season id must be numeric, got {active_season!r}") from exc
    latest_candidate = active_number if through_gameweek > 0 else active_number - 1
    active_cutoff = min(through_gameweek, max(PLUSVALENZA_SAMPLE_GAMEWEEKS))
    anchor = _processed(
        settings,
        f"plusvalenza_history_multiseason_{active_season}_pre_gw{through_gameweek}_{settings.capital_gain_history_seasons}y_nba_v4.parquet",
    )
    if not force_refresh and cache_valid(anchor):
        cached = read_parquet(anchor)
        # Older cache builds could accept non-NBA competitions that happened to
        # contain one or two NBA team codes. Rebuild those archives instead of
        # repeatedly training on them or silently accepting incomplete seasons.
        if cached is not None and _has_complete_plusvalenza_season(cached):
            return cached

    columns = ["player_name", "team_code", "role", "cr", "pdk", "plus", "min", "starter", "gameweek", "season_id"]
    selected_seasons: list[str] = []
    first_weeks: dict[str, pd.DataFrame] = {}
    for candidate in range(latest_candidate, 0, -1):
        prior_settings = copy(settings)
        prior_settings.season_id = str(candidate)
        try:
            first_week = dk_module.fetch_dunkest_gameweek_players(prior_settings, 1)
        except Exception as exc:
            logger.debug("Dunkest season %s unavailable during NBA history discovery: %s", candidate, exc)
            continue
        if first_week.empty or not {"player_name", "team_code", "cr", "pdk", "plus"}.issubset(first_week.columns):
            continue
        nba_week = first_week.loc[first_week["team_code"].astype(str).str.upper().isin(NBA_TEAM_CODES)].copy()
        team_coverage = nba_week["team_code"].astype(str).str.upper().nunique()
        if team_coverage < MIN_NBA_TEAMS_FOR_PLUSVALENZA:
            logger.debug(
                "Skipping Dunkest season %s during NBA history discovery: first-week "
                "NBA-team coverage is %s/%s, below the required %s.",
                candidate, team_coverage, 30, MIN_NBA_TEAMS_FOR_PLUSVALENZA,
            )
            continue
        selected_seasons.append(str(candidate))
        first_weeks[str(candidate)] = nba_week
        if len(selected_seasons) >= settings.capital_gain_history_seasons:
            break

    samples: list[pd.DataFrame] = []
    for historical_season in selected_seasons:
        cutoff = (
            active_cutoff
            if historical_season == active_season and through_gameweek > 0
            else max(PLUSVALENZA_SAMPLE_GAMEWEEKS)
        )
        season_path = _processed(settings, f"plusvalenza_history_nba_{historical_season}_through_gw{cutoff}_v4.parquet")
        cached_season = None if force_refresh or not cache_valid(season_path) else read_parquet(season_path)
        if cached_season is not None and not cached_season.empty and _has_complete_plusvalenza_season(cached_season):
            samples.append(cached_season)
            continue
        prior_settings = copy(settings)
        prior_settings.season_id = historical_season
        season_samples: list[pd.DataFrame] = []
        consecutive_misses = 0
        for gameweek in range(1, cutoff + 1):
            if gameweek == 1:
                weekly = first_weeks[historical_season]
            else:
                try:
                    weekly = dk_module.fetch_dunkest_gameweek_players(prior_settings, gameweek)
                except Exception as exc:
                    if gameweek in (2, 46, 91):
                        logger.warning("Dunkest PLUS history unavailable for NBA season %s GW%s: %s", historical_season, gameweek, exc)
                    consecutive_misses += 1
                    if consecutive_misses >= 3:
                        logger.warning(
                            "Truncating Dunkest PLUS history for season %s at GW%s after "
                            "three consecutive unavailable/invalid rounds; collected %s rounds of %s requested.",
                            historical_season, gameweek, len(season_samples), cutoff,
                        )
                        break
                    continue
                if weekly.empty or not {"player_name", "team_code", "cr", "pdk", "plus"}.issubset(weekly.columns):
                    consecutive_misses += 1
                    if consecutive_misses >= 3:
                        logger.warning(
                            "Truncating Dunkest PLUS history for season %s at GW%s after "
                            "three consecutive unavailable/invalid rounds; collected %s rounds of %s requested.",
                            historical_season, gameweek, len(season_samples), cutoff,
                        )
                        break
                    continue
                weekly = weekly.loc[weekly["team_code"].astype(str).str.upper().isin(NBA_TEAM_CODES)].copy()
                if weekly.empty:
                    consecutive_misses += 1
                    if consecutive_misses >= 3:
                        logger.warning(
                            "Truncating Dunkest PLUS history for season %s at GW%s after "
                            "three consecutive unavailable/invalid rounds; collected %s rounds of %s requested.",
                            historical_season, gameweek, len(season_samples), cutoff,
                        )
                        break
                    continue
            consecutive_misses = 0
            weekly = weekly.copy()
            weekly["gameweek"] = gameweek
            weekly["season_id"] = historical_season
            season_samples.append(weekly[[column for column in columns if column in weekly.columns]])
        if season_samples:
            season_history = pd.concat(season_samples, ignore_index=True)
            season_history = season_history.drop_duplicates(["player_name", "gameweek"], keep="last")
            if not _has_complete_plusvalenza_season(season_history):
                logger.warning(
                    "Skipping Dunkest season %s: fetched history has insufficient NBA-team coverage (%s).",
                    historical_season, _plusvalenza_season_team_coverage(season_history),
                )
                continue
            write_parquet(
                season_history, season_path, source="dunkest_official_nba_plusvalenza_all_gameweeks_v4",
                season_id=historical_season, through_gameweek=cutoff,
                gameweeks=int(season_history["gameweek"].nunique()),
            )
            samples.append(season_history)
    if not samples:
        logger.warning("No Dunkest NBA PLUS history found for IDs below %s", latest_candidate + 1)
        return pd.DataFrame(columns=columns)

    history = pd.concat(samples, ignore_index=True)
    history = history.drop_duplicates(["player_name", "season_id", "gameweek"], keep="last")
    for column in ("cr", "pdk", "plus", "min", "starter", "gameweek", "season_id"):
        if column in history:
            history[column] = pd.to_numeric(history[column], errors="coerce")
    history = history.dropna(subset=["player_name", "team_code", "cr", "pdk", "plus", "gameweek", "season_id"])
    history = history.loc[history["team_code"].astype(str).str.upper().isin(NBA_TEAM_CODES)]
    if not history.empty:
        write_parquet(
            history, anchor, source="dunkest_official_multiseason_nba_plusvalenza_v4",
            season_ids=selected_seasons, through_gameweek=through_gameweek,
            sample_gameweeks="all_available",
        )
        logger.info(
            "Loaded Dunkest official NBA PLUS history: %s rows from seasons %s (%s gameweeks)",
            len(history), selected_seasons, history.groupby("season_id")["gameweek"].nunique().to_dict(),
        )
    return history


def get_dunkest_data(
    settings: Settings,
    gameweek: int | None = None,
    force_refresh: bool = False,
    use_live_market: bool = True,
) -> pd.DataFrame:
    gw = gameweek or settings.target_gameweek
    path = _processed(settings, f"dunkest_players_{settings.season_id}_gw{gw}.parquet")
    live_market_path = settings.data_path / "current_lineups_market.csv"
    has_live_market = use_live_market and live_market_path.exists()
    if has_live_market:
        _check_live_market_freshness(settings, live_market_path)
    if not force_refresh and not has_live_market and cache_valid(
        path, max_age_hours=settings.market_cache_max_age_hours
    ):
        df = read_parquet(path)
        if df is not None and {
            "official_plusvalenza", "actual_pdk", "gameweek_stats_available", "prior_pdk"
        }.issubset(df.columns):
            df = add_previous_credit_change(settings, df, gw)
            if use_live_market:
                save_player_credit_snapshot(settings, df, gw)
            return df
    df = dk_module.fetch_nba_season_players(settings)
    live = pd.DataFrame()
    if has_live_market:
        live = pd.read_csv(live_market_path)
        live.columns = [str(column).strip().lower() for column in live.columns]
        live = live[live.get("role", pd.Series(index=live.index, dtype=str)).astype(str).str.upper() != "HC"].copy()
        if not {"role", "team"}.issubset(live.columns):
            raise RuntimeError("Lineups market is missing player role or team columns.")
        live["cr"] = pd.to_numeric(live.get("cr"), errors="coerce")
        live_role = live["role"]
        live["position"] = live_role.astype(str).str.upper().replace({"A": "F", "HC": "F"})
        live["pdk"] = float("nan")
        live["team_code"] = live.get("team", "").astype(str).str.upper()
        live_columns = [
            column for column in
            ("player_name", "cr", "position", "pdk", "team_code", "lineup_group", "status")
            if column in live.columns
        ]
        df = _merge_live_market_pool(df, live[live_columns])
    # Capture the season-to-date prior before attaching this game's outcomes.
    # `predict_players` consumes prior_pdk ahead of pdk, so current-week PDK
    # must remain in actual_pdk and never overwrite the forecast input.
    df["prior_pdk"] = pd.to_numeric(
        df.get("pdk", pd.Series(float("nan"), index=df.index)), errors="coerce"
    )
    cr_updates = df[["player_name", "cr"]].copy()
    cr_updates["key"] = cr_updates["player_name"].map(player_key)
    current_week_stats = pd.DataFrame()
    for gw_i in range(max(1, gw - 5), gw + 1):
        gw_slice = dk_module.fetch_dunkest_gameweek_players(settings, gw_i)
        if gw_slice.empty:
            continue
        if gw_i == gw:
            current_week_stats = gw_slice
        if {"player_name", "cr"}.issubset(gw_slice.columns):
            weekly = gw_slice[["player_name", "cr"]].copy()
            weekly["key"] = weekly["player_name"].map(player_key)
            weekly["cr"] = pd.to_numeric(weekly["cr"], errors="coerce")
            weekly = weekly.loc[weekly["cr"].ge(settings.min_cr)].drop_duplicates("key", keep="last")
            updates = weekly.set_index("key")["cr"]
            cr_updates["cr"] = cr_updates["key"].map(updates).fillna(cr_updates["cr"])
    df = add_official_plusvalenza(df, current_week_stats)
    df = df.merge(
        cr_updates.drop(columns="key").rename(columns={"cr": "cr_latest"}),
        on="player_name",
        how="left",
        suffixes=("", "_dup"),
    )
    df["cr"] = df["cr_latest"].fillna(df["cr"])
    df = df.drop(columns=[c for c in df.columns if c.endswith("_dup") or c == "cr_latest"])
    if has_live_market:
        live_prices = live[["player_name", "cr"]].copy()
        live_prices["_market_key"] = live_prices["player_name"].map(player_key)
        price_lookup = live_prices.drop_duplicates("_market_key", keep="last").set_index("_market_key")["cr"]
        df["_market_key"] = df["player_name"].map(player_key)
        df["cr"] = df["_market_key"].map(price_lookup).combine_first(df["cr"])
        df = df.drop(columns="_market_key")
    if settings.impute_missing_cr:
        missing = df["cr"] < settings.min_cr
        df.loc[missing, "cr"] = (
            (df.loc[missing, "pdk"].astype(float) / 3.5)
            .clip(settings.min_cr, settings.max_cr)
            .fillna(settings.min_cr)
        )
    df = df[df["cr"] >= settings.min_cr].copy()
    gw_df = current_week_stats
    df["gameweek_stats_available"] = not gw_df.empty
    df["actual_pdk"] = float("nan")
    if not gw_df.empty:
        gw_copy = gw_df[["player_name", "pdk"]].copy()
        gw_copy["key"] = gw_copy["player_name"].map(player_key)
        gw_pdk = gw_copy.drop_duplicates("key", keep="last").set_index("key")["pdk"]
        df["key"] = df["player_name"].map(player_key)
        df["pdk_gw"] = df["key"].map(gw_pdk)
        # Absence from the API result table is not proof of a zero score: it
        # can also reflect incomplete coverage or an unresolved identity.
        # Keep the actual missing so backtests cannot silently score it as 0.
        df["actual_pdk"] = df["pdk_gw"]
        df = df.drop(columns=["key", "pdk_gw"], errors="ignore")
    df["gameweek"] = gw
    df = add_previous_credit_change(settings, df, gw)
    if use_live_market:
        save_player_credit_snapshot(settings, df, gw)
    write_parquet(df, path, source="dunkest_api/stats/table", season_id=settings.season_id, gameweek=gw)
    return df


def save_injury_snapshot(
    settings: Settings, injuries: pd.DataFrame, gameweek: int
) -> None:
    """Archive the availability report used to make a pregame forecast."""
    if injuries.empty or "player_name" not in injuries.columns:
        return
    snapshot = injuries.copy()
    snapshot["gameweek"] = int(gameweek)
    if "observed_at_utc" not in snapshot:
        snapshot["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
    path = _processed(
        settings, f"injuries_{settings.season_id}_gw{gameweek}.parquet"
    )
    dedupe_columns = ["player_name", "team"] if "team" in snapshot.columns else ["player_name"]
    write_parquet(
        snapshot.drop_duplicates(dedupe_columns, keep="last"),
        path,
        source="dunkest_official_injuries_page_snapshot",
        source_url="https://www.dunkest.com/it/nba/infortuni",
        season_id=settings.season_id,
        gameweek=gameweek,
        dunkest_turn=settings.target_dunkest_turn,
    )


def save_coach_market_snapshot(
    settings: Settings, coaches: pd.DataFrame, gameweek: int
) -> None:
    """Archive the coach prices and scheduled matchups used by a forecast."""
    required = {"coach", "team", "coach_cr"}
    if coaches.empty or not required.issubset(coaches.columns):
        return
    columns = [
        column for column in (
            "coach", "team", "coach_cr", "opponent", "opponent_coach",
            "opponent_coach_cr", "date", "giornata", "nba_game_id",
            "dunkest_gameweek", "dunkest_turn", "fixture_source",
        ) if column in coaches.columns
    ]
    snapshot = coaches[columns].copy()
    snapshot["team"] = snapshot["team"].astype(str).str.upper().str.strip()
    snapshot["coach_cr"] = pd.to_numeric(snapshot["coach_cr"], errors="coerce")
    if "opponent_coach_cr" in snapshot:
        snapshot["opponent_coach_cr"] = pd.to_numeric(
            snapshot["opponent_coach_cr"], errors="coerce"
        )
    snapshot = snapshot.dropna(subset=["coach", "team", "coach_cr"])
    snapshot["gameweek"] = int(gameweek)
    path = _processed(
        settings, f"coach_market_{settings.season_id}_gw{gameweek}.parquet"
    )
    write_parquet(
        snapshot.drop_duplicates("team", keep="last"),
        path,
        source="dunkest_pregame_coach_market_snapshot",
        season_id=settings.season_id,
        gameweek=gameweek,
    )


def get_injuries(settings: Settings, force_refresh: bool = False) -> pd.DataFrame:
    """Get availability from Dunkest's dedicated injury page, scoped to this gameweek.

    Lineups remains a source for prices/roster data, but its browser scrape is no
    longer used as the injury-status feed. A cached report is reusable only for
    the same season and gameweek; otherwise the official injury page is fetched.
    """
    import warnings

    path = _processed(settings, "injuries.parquet")
    target_gameweek = int(settings.target_gameweek)
    metadata = read_cache_metadata(path) or {}
    cached = read_parquet(path) if path.is_file() else None
    cache_matches_scope = (
        str(metadata.get("source", "")).startswith("dunkest_official_injuries_page")
        and str(metadata.get("season_id", settings.season_id)) == str(settings.season_id)
        and pd.to_numeric(metadata.get("gameweek"), errors="coerce") == target_gameweek
    )
    if (
        not force_refresh
        and cache_matches_scope
        and cache_valid(path, max_age_hours=6)
        and cached is not None
        and not cached.empty
    ):
        df = cached.copy()
    else:
        try:
            df = dk_module.scrape_injuries(settings)
        except Exception as exc:
            if not force_refresh and cache_matches_scope and cached is not None and not cached.empty:
                warnings.warn(
                    f"Pagina infortuni Dunkest non raggiungibile; riuso lo snapshot "
                    f"della stessa giornata ({exc}).",
                    RuntimeWarning,
                    stacklevel=2,
                )
                df = cached.copy()
            else:
                raise RuntimeError(
                    "Impossibile acquisire lo stato infortuni dalla pagina ufficiale "
                    "Dunkest per la giornata richiesta; non uso lo scraping Lineups come fallback."
                ) from exc

        required = {"player_name", "team", "status"}
        if not required.issubset(df.columns) or df.empty:
            if not force_refresh and cache_matches_scope and cached is not None and not cached.empty:
                warnings.warn(
                    "La pagina infortuni Dunkest ha restituito una lista vuota/invalida; "
                    "riuso lo snapshot valido della stessa giornata.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                df = cached.copy()
            else:
                raise RuntimeError(
                    "La pagina infortuni Dunkest non ha restituito righe valide per la "
                    "giornata richiesta; non considero automaticamente sani tutti i giocatori."
                )
        else:
            df = df.copy()
            df["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
            write_parquet(
                df,
                path,
                source="dunkest_official_injuries_page",
                source_url="https://fantasy.dunkest.com/1/injuries",
                season_id=settings.season_id,
                gameweek=target_gameweek,
            )

    # Explicit user-confirmed overrides are retained, but the browser Lineups
    # availability files are deliberately not merged into the health feed.
    override_path = settings.data_path / "injury_overrides.csv"
    if override_path.is_file():
        overrides = pd.read_csv(override_path)
        overrides.columns = [str(column).strip().lower() for column in overrides.columns]
        required_overrides = {"player_name", "team", "status", "gameweek"}
        if required_overrides.issubset(overrides.columns):
            overrides = overrides.loc[
                pd.to_numeric(overrides["gameweek"], errors="coerce").eq(target_gameweek)
            ].copy()
            if not overrides.empty:
                # Apply explicit overrides to matching official rows instead of
                # appending a duplicate that would erase injury type/severity
                # during keep-last deduplication. Preserve the official reason,
                # description and estimated return alongside the overridden status.
                df = df.copy()
                df["_injury_name_key"] = df["player_name"].map(
                    lambda value: str(value or "").strip().casefold()
                )
                df["_injury_team_key"] = df["team"].astype(str).str.strip().str.upper()
                for _, override in overrides.iterrows():
                    name_key = str(override.get("player_name") or "").strip().casefold()
                    team_key = str(override.get("team") or "").strip().upper()
                    match = df["_injury_name_key"].eq(name_key) & df["_injury_team_key"].eq(team_key)
                    if match.any():
                        idx = df.index[match][-1]
                        df.loc[idx, "status"] = str(override.get("status") or "").strip().upper()
                        df.loc[idx, "source"] = "user_confirmed_override"
                        df.loc[idx, "override_gameweek"] = target_gameweek
                    else:
                        extra = {column: pd.NA for column in df.columns if not column.startswith("_")}
                        extra.update({
                            "player_name": str(override.get("player_name") or "").strip(),
                            "team": team_key,
                            "status": str(override.get("status") or "").strip().upper(),
                            "injury_type": "USER_OVERRIDE",
                            "injury_severity": "OVERRIDE",
                            "expected_return_days": pd.NA,
                            "season_ending": False,
                            "source": "user_confirmed_override",
                            "override_gameweek": target_gameweek,
                        })
                        df = pd.concat([df, pd.DataFrame([extra])], ignore_index=True, sort=False)
                df = df.drop(columns=["_injury_name_key", "_injury_team_key"], errors="ignore")

    df["player_name"] = df["player_name"].astype(str).str.strip()
    df["team"] = df["team"].astype(str).str.strip().str.upper()
    df["status"] = df["status"].astype(str).str.strip().str.upper()
    df = df.loc[df["player_name"].ne("") & df["player_name"].ne("NAN")]
    dedupe_columns = ["player_name", "team"] if "team" in df.columns else ["player_name"]
    return df.drop_duplicates(dedupe_columns, keep="last").reset_index(drop=True)


def get_player_data(settings: Settings, force_refresh: bool = False) -> pd.DataFrame:
    path = _processed(settings, f"player_game_logs_{settings.season}.parquet")
    if not force_refresh and cache_valid(path, max_age_hours=24):
        metadata = read_cache_metadata(path) or {}
        cache_source = metadata.get("source")
        verified_collection = metadata.get("collection_complete") is True
        df = None
        if (
            cache_source != "nba_api/playergamelog" or verified_collection
        ):
            df = read_parquet(path)
        if df is not None:
            synthetic = (
                df.get("data_source", pd.Series("", index=df.index))
                .astype(str)
                .eq("synthetic_dunkest_market")
                .any()
                or df.get("OPPONENT", pd.Series("", index=df.index))
                .astype(str)
                .eq("OPP")
                .any()
            )
            if synthetic and not settings.allow_synthetic_logs:
                if not settings.use_nba_api_logs:
                    raise RuntimeError(
                        f"La cache {path} contiene log sintetici. Raccogli log NBA reali; "
                        "per usare esplicitamente il fallback imposta allow_synthetic_logs: true."
                    )
                # Ignore the synthetic cache and try to replace it with real logs.
            else:
                if synthetic:
                    import warnings

                    warnings.warn(
                        f"Uso cache di log sintetici: {path}. Previsioni non basate su risultati NBA reali.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                return df
    dk = dk_module.fetch_nba_season_players(settings)
    if not dk.empty:
        priority_column = "cr" if "cr" in dk.columns else "pdk"
        ordered = dk.assign(_priority=pd.to_numeric(dk[priority_column], errors="coerce"))
        names = ordered.sort_values("_priority", ascending=False, na_position="last")["player_name"].astype(str).tolist()
    else:
        names = None
    df = pd.DataFrame()
    collection_error: Exception | None = None
    if settings.use_nba_api_logs:
        try:
            df = nba.fetch_player_game_logs(settings, player_names=names)
            report = df.attrs.get("collection_report")
            if report is None or not report.get("collection_complete", False):
                collection_error = RuntimeError(
                    "NBA player game-log collection is incomplete: "
                    f"{report or 'collector did not provide a completeness report'}"
                )
                df = pd.DataFrame()
        except Exception as exc:
            collection_error = exc
            df = pd.DataFrame()
    if df.empty and dk.empty and collection_error is not None:
        raise RuntimeError(f"NBA player game-log collection failed: {collection_error}") from collection_error
    if df.empty and not dk.empty:
        if not settings.allow_synthetic_logs:
            raise RuntimeError(
                "Log NBA reali completi non disponibili; il fallback sintetico è disattivato. "
                "Riprova con una cache player_game_logs valida oppure abilita "
                "allow_synthetic_logs solo se accetti previsioni basate su dati simulati. "
                f"Errore raccolta: {collection_error}"
            ) from collection_error
        from dunkest.data.nba.fallback_logs import synthetic_logs_from_dunkest

        import warnings

        warnings.warn(
            "NBA game logs unavailable; using synthetic logs. Predictions and backtests "
            "are based on synthetic history.", RuntimeWarning, stacklevel=2
        )
        fallback = dk
        if settings.max_player_log_entries > 0:
            order_column = "cr" if "cr" in dk.columns else "pdk"
            fallback = dk.assign(_priority=pd.to_numeric(dk[order_column], errors="coerce"))
            fallback = fallback.sort_values("_priority", ascending=False, na_position="last").head(
                settings.max_player_log_entries
            ).drop(columns="_priority")
        df = synthetic_logs_from_dunkest(fallback)
        df["data_source"] = "synthetic_dunkest_market"
        write_parquet(df, path, source="synthetic_dunkest_market", season=settings.season)
        return df
    if not df.empty:
        df["data_source"] = "nba_api/playergamelog"
    report = df.attrs.get("collection_report", {})
    write_parquet(
        df,
        path,
        source="nba_api/playergamelog",
        season=settings.season,
        **report,
    )
    return df


def get_team_data(settings: Settings, force_refresh: bool = False) -> pd.DataFrame:
    path = _processed(settings, f"team_game_logs_{settings.season}.parquet")
    if not force_refresh and cache_valid(path, max_age_hours=24):
        metadata = read_cache_metadata(path) or {}
        cache_source = metadata.get("source")
        verified_collection = metadata.get("collection_complete") is True
        df = None
        if (
            cache_source != "nba_api/teamgamelog" or verified_collection
        ):
            df = read_parquet(path)
        if df is not None:
            return df
    if not settings.use_nba_api_logs:
        write_parquet(pd.DataFrame(), path, source="skipped")
        return pd.DataFrame()
    df = nba.fetch_team_game_logs(settings)
    report = df.attrs.get("collection_report")
    if report is None or not report.get("collection_complete", False):
        raise RuntimeError(
            "NBA team game-log collection is incomplete: "
            f"{report or 'collector did not provide a completeness report'}"
        )
    write_parquet(df, path, source="nba_api/teamgamelog", **report)
    return df


def get_schedule(settings: Settings, force_refresh: bool = False) -> pd.DataFrame:
    path = _processed(settings, f"schedule_{settings.season}.parquet")
    if not force_refresh and cache_valid(path, max_age_hours=24):
        df = read_parquet(path)
        if df is not None:
            return df
    if not settings.use_nba_api_logs:
        write_parquet(pd.DataFrame(), path, source="skipped")
        return pd.DataFrame()
    df = nba.fetch_schedule(settings)
    write_parquet(df, path, source="nba_api/leaguegamefinder")
    return df


def get_future_schedule(settings: Settings, force_refresh: bool = False) -> pd.DataFrame:
    # v2 keeps the NBA week label semantically explicit and avoids loading a
    # cached frame whose WEEK_NUMBER column may have been confused with GW.
    path = _processed(settings, f"future_regular_schedule_{settings.season}_v2.parquet")
    if not force_refresh and cache_valid(path, max_age_hours=24):
        df = read_parquet(path)
        if df is not None and "NBA_WEEK_NUMBER" in df:
            return df
    df = nba.fetch_future_schedule(settings)
    write_parquet(df, path, source="nba_api/scheduleleaguev2", season=settings.season)
    return df


def _historical_coach_scores(
    settings: Settings, coaches: dict[str, tuple[str, float]]
) -> dict[str, float]:
    """Estimate coach PDK from completed prior-season team results for G1."""
    prior = copy(settings)
    prior.season = settings.feature_season
    try:
        games = nba.fetch_schedule(prior)
    except Exception:
        return {}
    required = {"HOME_TEAM", "AWAY_TEAM", "PTS", "PLUS_MINUS"}
    if games.empty or not required.issubset(games.columns):
        return {}

    scores: dict[str, list[float]] = {}
    for _, game in games.iterrows():
        home = str(game["HOME_TEAM"]).strip().upper()
        away = str(game["AWAY_TEAM"]).strip().upper()
        if home not in coaches or away not in coaches:
            continue
        home_pts = pd.to_numeric(game["PTS"], errors="coerce")
        margin = pd.to_numeric(game["PLUS_MINUS"], errors="coerce")
        if pd.isna(home_pts) or pd.isna(margin):
            continue
        away_pts = float(home_pts) - float(margin)
        for team, opponent, points, opponent_points in (
            (home, away, float(home_pts), away_pts),
            (away, home, away_pts, float(home_pts)),
        ):
            coach_cr = coaches[team][1]
            opponent_cr = coaches[opponent][1]
            score = coach_points_from_game(points, opponent_points, coach_cr, opponent_cr)
            scores.setdefault(team, []).append(score)
    return {team: sum(values) / len(values) for team, values in scores.items() if values}


def get_coach_data(
    settings: Settings,
    gameweek: int | None = None,
    force_refresh: bool = False,
    coach_market: pd.DataFrame | None = None,
) -> pd.DataFrame:
    gw = gameweek or settings.target_gameweek
    # Bump the cache key after changing gameweek-specific schedule selection;
    # otherwise an older cache can keep returning an opponent from another GW.
    path = _processed(settings, f"coaches_{settings.season_id}_gw{gw}_v3.parquet")
    market_path = settings.data_path / "current_lineups_market.csv"
    has_live_market = coach_market is None and market_path.exists()
    if has_live_market:
        _check_live_market_freshness(settings, market_path)
    if not force_refresh and coach_market is None and not has_live_market and cache_valid(
        path, max_age_hours=settings.market_cache_max_age_hours
    ):
        df = read_parquet(path)
        if df is not None and not df.empty:
            return df

    coach_map: dict[str, str] = {}
    exact_coaches: dict[str, tuple[str, float]] = {}
    if coach_market is None:
        if market_path.exists():
            live = pd.read_csv(market_path)
            live.columns = [str(column).strip().lower() for column in live.columns]
            if {"player_name", "cr", "team", "role"}.issubset(live.columns):
                live = live[live["role"].astype(str).str.upper().eq("HC")]
                for _, item in live.iterrows():
                    cr = pd.to_numeric(item["cr"], errors="coerce")
                    if pd.notna(cr) and float(cr) >= settings.min_cr:
                        exact_coaches[str(item["team"]).upper()] = (str(item["player_name"]), float(cr))
        if not exact_coaches:
            coach_map_path = settings.root / "config" / "nba_coaches_2026.yaml"
            with coach_map_path.open(encoding="utf-8") as f:
                coach_map = yaml.safe_load(f) or {}

    # A Dunkest coach matchup is never inferred from NBA_WEEK_NUMBER. The
    # versioned bridge is the sole source of Giornata/Turno/eligibility.
    schedule = get_fixture_mapping(settings, gw)
    schedule = schedule.loc[schedule["fantasy_eligible"].eq(True)].copy()
    schedule = schedule.rename(
        columns={"game_datetime_utc": "GAME_DATE", "home_team": "HOME_TEAM", "away_team": "AWAY_TEAM", "nba_game_id": "NBA_GAME_ID"}
    )
    schedule["GAME_DATE"] = pd.to_datetime(schedule.get("GAME_DATE"), errors="coerce", utc=True)
    if schedule.empty:
        schedule = pd.DataFrame(columns=["GAME_DATE", "HOME_TEAM", "AWAY_TEAM", "NBA_GAME_ID"])

    if coach_market is not None and not coach_market.empty:
        required = {"coach", "team", "coach_cr"}
        if not required.issubset(coach_market.columns):
            raise ValueError("Il listino coach deve contenere coach, team e coach_cr.")
        for _, row in coach_market.iterrows():
            team = str(row["team"]).strip().upper()
            name = str(row["coach"]).strip()
            cr = pd.to_numeric(row["coach_cr"], errors="coerce")
            if team and name and pd.notna(cr) and float(cr) >= settings.min_cr:
                exact_coaches[team] = (name, float(cr))

    rows: list[dict] = []
    recent = schedule.sort_values("GAME_DATE").tail(60)
    for _, game in recent.iterrows():
        def is_true(value: object) -> bool:
            return str(value).strip().casefold() in {"true", "1", "yes"}

        home_valid = is_true(game.get("home_team_eligible", game.get("fantasy_eligible", False)))
        away_valid = is_true(game.get("away_team_eligible", game.get("fantasy_eligible", False)))
        sides = []
        if home_valid:
            sides.append((game["HOME_TEAM"], game["AWAY_TEAM"]))
        if away_valid:
            sides.append((game["AWAY_TEAM"], game["HOME_TEAM"]))
        for team, opp in sides:
            team, opp = str(team).upper(), str(opp).upper()
            coach = exact_coaches.get(team, (coach_map.get(team, ""), float("nan")))
            opp_coach = exact_coaches.get(opp, (coach_map.get(opp, ""), float("nan")))
            rows.append(
                {
                    "giornata": gw,
                    "dunkest_gameweek": gw,
                    "dunkest_turn": game.get("dunkest_turn"),
                    "nba_game_id": game.get("NBA_GAME_ID"),
                    "fixture_source": game.get("source"),
                    "date": pd.Timestamp(game["GAME_DATE"]).date().isoformat(),
                    "coach": coach[0],
                    "team": team,
                    "opponent": opp,
                    "coach_cr": coach[1],
                    "opponent_coach": opp_coach[0],
                    "opponent_coach_cr": opp_coach[1],
                }
            )
    df = pd.DataFrame(
        rows,
        columns=[
            "giornata", "date", "coach", "team", "opponent", "coach_cr",
            "opponent_coach", "opponent_coach_cr", "dunkest_turn", "nba_game_id", "fixture_source",
        ],
    )
    if not df.empty:
        # A team can contribute only through its explicitly black Dunkest game.
        df = df.drop_duplicates(subset=["team"], keep="first")
    cr_table = dk_module.fetch_coach_cr_table(settings, gw) if coach_market is None else pd.DataFrame()
    if not cr_table.empty and "team_code" in cr_table.columns:
        cr_by_team = cr_table.groupby("team_code")["cr"].median()
        df["coach_cr"] = df["team"].map(cr_by_team).fillna(df["coach_cr"])

    # Missing coach quotes are excluded rather than fabricated from player prices.
    df = df.dropna(subset=["coach_cr", "opponent_coach_cr"])
    df = df[(df["coach"] != "") & (df["opponent_coach"] != "")]
    if exact_coaches:
        # A partial Dunkest fixture bridge (for example, only Turno 1) must
        # not silently remove the other franchises from the coach market.
        # Keep their official name/CR and use their prior-season coach score
        # until a fixture is mapped; `predict_coach_points` recognizes these
        # as fallback rows and does not invent a matchup projection.
        covered = set(df.get("team", pd.Series(dtype=str)).astype(str).str.upper())
        missing_teams = sorted(set(exact_coaches) - covered)
        if missing_teams:
            prior_scores = _historical_coach_scores(settings, exact_coaches)
            fallback = pd.DataFrame(
                [
                    {
                        "giornata": gw,
                        "dunkest_gameweek": gw,
                        "dunkest_turn": pd.NA,
                        "nba_game_id": pd.NA,
                        "fixture_source": "prior_season_fallback_no_fixture_mapping",
                        "date": "",
                        "coach": exact_coaches[team][0],
                        "team": team,
                        "opponent": "",
                        "coach_cr": exact_coaches[team][1],
                        "opponent_coach": "",
                        "opponent_coach_cr": float("nan"),
                        "prior_coach_pdk": prior_scores.get(team, float("nan")),
                    }
                    for team in missing_teams
                ]
            )
            df = pd.concat([df, fallback], ignore_index=True, sort=False)
    write_parquet(df, path, source="coach_lineup_market+schedule", gameweek=gw)
    return df
