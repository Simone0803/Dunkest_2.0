from __future__ import annotations

import warnings
from copy import copy
import logging

import pandas as pd

from dunkest.config import Settings
from dunkest.data.cache import (
    cache_has_complete_collection,
    cache_valid,
    read_cache_metadata,
    read_parquet,
)
from dunkest.data.access import get_injuries, get_player_data, get_team_data
from dunkest.data.dunkest.fixtures import get_fixture_mapping
from dunkest.data.dunkest.official_pdk import (
    attach_observed_round_pdk_labels,
    attach_official_pdk_labels,
)
from dunkest.features.builder import build_feature_matrix
from dunkest.models.predictor import train_models
from dunkest.models.multiseason_training import train_multiseason_models
from dunkest.data.nba.collector import require_complete_collection
from dunkest.names import player_key

logger = logging.getLogger(__name__)


def _merge_player_season_history(
    current_logs: pd.DataFrame, prior_logs: pd.DataFrame
) -> pd.DataFrame:
    """Combine prior and current NBA logs without silently replacing games."""
    frames = [frame.copy() for frame in (prior_logs, current_logs) if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()

    normalized: list[pd.DataFrame] = []
    for frame in frames:
        if "GAME_ID" not in frame and "Game_ID" in frame:
            frame = frame.rename(columns={"Game_ID": "GAME_ID"})
        normalized.append(frame)
    combined = pd.concat(normalized, ignore_index=True, sort=False)
    if "GAME_DATE" in combined:
        combined["GAME_DATE"] = (
            pd.to_datetime(combined["GAME_DATE"], errors="coerce", utc=True)
            .dt.tz_convert(None)
        )

    # NBA IDs are stable through team changes and are the preferred join key.
    # Legacy sources without IDs can still be merged by canonical name + game ID.
    game_id = combined.get("GAME_ID", pd.Series(pd.NA, index=combined.index)).astype("string").str.strip()
    game_id = game_id.mask(game_id.isna() | game_id.isin(["", "<NA>", "NAN", "NONE"]))
    if "PLAYER_ID" in combined:
        player_id = combined["PLAYER_ID"].astype("string").str.strip()
        player_id = player_id.mask(player_id.isna() | player_id.isin(["", "<NA>", "NAN", "NONE"]))
    else:
        player_id = pd.Series(pd.NA, index=combined.index, dtype="string")
    name = combined.get("PLAYER_NAME", pd.Series("", index=combined.index)).map(player_key)
    identity = player_id.combine_first(name.where(name.ne("")))
    usable_key = game_id.notna() & identity.notna()
    keys = pd.DataFrame({"identity": identity.loc[usable_key], "game_id": game_id.loc[usable_key]})
    if keys.duplicated(["identity", "game_id"], keep=False).any():
        duplicate_rows = combined.loc[keys.index[keys.duplicated(["identity", "game_id"], keep=False)]]
        examples = duplicate_rows[[c for c in ("PLAYER_NAME", "PLAYER_ID", "GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION") if c in duplicate_rows]].head(5)
        raise ValueError(
            "Prior/current NBA logs contain duplicate player-game identities; refusing to "
            f"drop or overwrite them. Examples: {examples.to_dict(orient='records')}"
        )

    if not usable_key.all():
        missing = combined.loc[~usable_key, [c for c in ("PLAYER_NAME", "PLAYER_ID", "GAME_ID") if c in combined]].head(5)
        raise ValueError(
            "Cannot safely merge player-game history without a player identity and game ID. "
            f"Examples: {missing.to_dict(orient='records')}"
        )
    sort_columns = [column for column in ("GAME_DATE", "PLAYER_ID", "GAME_ID") if column in combined]
    return combined.sort_values(sort_columns, kind="stable", na_position="last").reset_index(drop=True)


def _player_feature_history(
    settings: Settings,
    current_logs: pd.DataFrame,
    *,
    target_cutoff_utc: object | None = None,
) -> pd.DataFrame:
    """Load certified prior-season logs alongside current-season observations."""
    if settings.target_gameweek <= 1:
        return attach_official_pdk_labels(
            current_logs, settings.data_path, settings.feature_season
        )
    path = settings.data_path / "processed" / f"player_game_logs_{settings.feature_season}.parquet"
    prior_logs = pd.DataFrame()
    if path.exists():
        if cache_has_complete_collection(path):
            prior_logs = pd.read_parquet(path)
        else:
            logger.warning(
                "Prior-season player history exists but is not certified complete; "
                "it will not be used: %s",
                path,
            )
    current_count = len(current_logs)
    prior_count = len(prior_logs)
    if prior_count:
        prior_logs = attach_official_pdk_labels(prior_logs, settings.data_path, settings.feature_season)
    if current_count and settings.season:
        current_logs = attach_official_pdk_labels(current_logs, settings.data_path, settings.season)
        if target_cutoff_utc is not None:
            current_logs = attach_observed_round_pdk_labels(
                current_logs,
                settings.data_path,
                season_id=settings.season_id,
                target_cutoff_utc=target_cutoff_utc,
            )
            logger.info(
                "Official round PDK overlay for GW%s (cutoff %s): %s",
                settings.target_gameweek,
                target_cutoff_utc,
                current_logs.attrs.get("round_pdk_overlay", {}),
            )
    combined = _merge_player_season_history(current_logs, prior_logs)
    logger.info(
        "Player history for GW%s: prior rows found=%d, current rows found=%d, "
        "rows used=%d, rows discarded=%d, players=%d",
        settings.target_gameweek,
        prior_count,
        current_count,
        len(combined),
        prior_count + current_count - len(combined),
        combined.get("PLAYER_ID", combined.get("PLAYER_NAME", pd.Series(dtype=object))).nunique(),
    )
    return combined


def _verified_recent_nba_log_cache(settings: Settings, kind: str) -> pd.DataFrame | None:
    """Return only a recent, complete NBA API log cache suitable for refresh fallback."""
    if kind not in {"player", "team"}:
        raise ValueError(f"Unknown NBA log cache kind: {kind}")
    source = f"nba_api/{kind}gamelog"
    path = settings.data_path / "processed" / f"{kind}_game_logs_{settings.season}.parquet"
    metadata = read_cache_metadata(path) or {}
    if (
        metadata.get("source") != source
        or metadata.get("collection_complete") is not True
        or not cache_valid(path, max_age_hours=24)
    ):
        return None
    frame = read_parquet(path)
    if frame is None or frame.empty:
        return None
    canonical_columns = {
        str(column).upper(): column for column in frame.columns
    }
    aliases = {
        "GAME_ID": canonical_columns.get("GAME_ID"),
        "GAME_DATE": canonical_columns.get("GAME_DATE"),
        "PLAYER_ID" if kind == "player" else "TEAM_ID": canonical_columns.get(
            "PLAYER_ID" if kind == "player" else "TEAM_ID"
        ),
    }
    if any(column is None for column in aliases.values()):
        return None
    frame = frame.rename(columns={source_name: target for target, source_name in aliases.items()})
    required = {"GAME_ID", "GAME_DATE"}
    entity = "PLAYER_ID" if kind == "player" else "TEAM_ID"
    if not required.issubset(frame.columns) or entity not in frame.columns:
        return None
    if frame[list(required | {entity})].isna().any().any():
        return None
    if frame.duplicated([entity, "GAME_ID"]).any():
        return None
    return frame


def _current_player_logs_for_gameweek(settings: Settings) -> pd.DataFrame:
    """Refresh current-season logs, falling back only to a verified fresh cache."""
    try:
        return get_player_data(settings, force_refresh=settings.target_gameweek > 1)
    except Exception:
        if settings.target_gameweek <= 1:
            raise
        cached = _verified_recent_nba_log_cache(settings, "player")
        if cached is None:
            raise
        logger.warning(
            "Live NBA player-log refresh failed for GW%s; using verified complete cache "
            "captured within 24 hours (%d rows).",
            settings.target_gameweek,
            len(cached),
            exc_info=True,
        )
        return cached


def run_train(settings: Settings) -> tuple[dict, pd.DataFrame]:
    try:
        schedule = get_fixture_mapping(settings, settings.target_gameweek) if settings.use_schedule else pd.DataFrame()
    except Exception as exc:
        warnings.warn(f"Upcoming schedule unavailable for player features: {exc}", RuntimeWarning, stacklevel=2)
        schedule = pd.DataFrame()
    target_cutoff_utc = None
    if not schedule.empty and "game_datetime_utc" in schedule:
        kickoff = pd.to_datetime(schedule["game_datetime_utc"], errors="coerce", utc=True)
        if kickoff.notna().all():
            # The earliest verified schedule timestamp is a conservative
            # boundary for when prior-round results may be used. Dunkest's
            # exact lock timestamp is not part of the current mapping schema.
            target_cutoff_utc = kickoff.min()

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
        # Recollect the complete current season before every post-opener run so
        # newly completed games are persisted before GW2+ features are built.
        player_logs = _current_player_logs_for_gameweek(settings)
        try:
            team_logs = get_team_data(settings, force_refresh=settings.target_gameweek > 1)
        except Exception:
            if settings.target_gameweek <= 1:
                raise
            team_logs = _verified_recent_nba_log_cache(settings, "team")
            if team_logs is None:
                raise
            logger.warning(
                "Live NBA team-log refresh failed for GW%s; using verified complete cache "
                "captured within 24 hours (%d rows).",
                settings.target_gameweek,
                len(team_logs),
                exc_info=True,
            )
    player_logs = _player_feature_history(
        settings, player_logs, target_cutoff_utc=target_cutoff_utc
    )
    injuries = get_injuries(settings) if settings.use_injuries else pd.DataFrame()
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
    if settings.opening_multiseason_training:
        # Keep the same certified, absolute-PDK trainer throughout the season.
        # After GW1, append only completed current-season rows with verified
        # official Dunkest PDK labels; proxy targets and inference rows are excluded.
        models, _training_features = train_multiseason_models(
            settings, current_features=None if settings.target_gameweek == 1 else features
        )
    else:
        training_features = features
        if settings.target_gameweek > 1 and not features.empty and "GAME_DATE" in features:
            # Keep the primary in-season trainer on current-season targets while
            # allowing the returned inference features to use prior-season logs.
            season_start = pd.to_datetime(settings.nba_season_start, errors="coerce", utc=True)
            dates = pd.to_datetime(features["GAME_DATE"], errors="coerce", utc=True)
            inference = features.get("is_inference", pd.Series(False, index=features.index)).fillna(False).astype(bool)
            training_features = features.loc[~inference & dates.ge(season_start)].copy()
        models, _ = train_models(settings, training_features)
    return models, features
