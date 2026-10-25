from __future__ import annotations

import time
import warnings

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from dunkest.config import Settings
from dunkest.names import player_key
from dunkest.rules.pdk import pdk_from_boxscore_row


def _nba_season_str(season: str) -> str:
    return season


def _minutes_to_float(value: object) -> float:
    """Convert NBA ``MM:SS`` minute strings without discarding seconds."""
    if isinstance(value, str) and ":" in value:
        minutes, seconds = value.strip().split(":", maxsplit=1)
        return float(minutes) + float(seconds) / 60.0
    return float(value)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=1.0),
    reraise=True,
)
def _fetch_player_log(player_id: int, season: str) -> pd.DataFrame:
    from nba_api.stats.endpoints import playergamelog

    return playergamelog.PlayerGameLog(
        player_id=player_id, season=season, season_type_all_star="Regular Season"
    ).get_data_frames()[0]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=1.0),
    reraise=True,
)
def _fetch_league_player_logs(season: str) -> pd.DataFrame:
    """Fetch all player-game rows for a season in one NBA Stats request."""
    from nba_api.stats.endpoints import playergamelogs

    return playergamelogs.PlayerGameLogs(
        season_nullable=season,
        season_type_nullable="Regular Season",
    ).get_data_frames()[0]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=1.0),
    reraise=True,
)
def _fetch_team_log(team_id: int, season: str) -> pd.DataFrame:
    from nba_api.stats.endpoints import teamgamelog

    return teamgamelog.TeamGameLog(
        team_id=team_id, season=season, season_type_all_star="Regular Season"
    ).get_data_frames()[0]


def _collection_report(
    expected: int, attempted: int, failures: list[tuple[str, str]], truncated: int = 0
) -> dict:
    return {
        "collection_complete": not failures and truncated == 0,
        "expected_entities": expected,
        "attempted_entities": attempted,
        "failed_entities": len(failures),
        "truncated_entities": truncated,
        "failed_entity_names": [name for name, _ in failures],
    }


def _attach_collection_report(
    frame: pd.DataFrame, report: dict, entity_type: str, failures: list[tuple[str, str]]
) -> pd.DataFrame:
    frame.attrs["collection_report"] = report
    if not report["collection_complete"]:
        examples = ", ".join(
            f"{name}: {message}" for name, message in failures[:3]
        )
        warnings.warn(
            f"NBA {entity_type} collection incomplete: "
            f"{report['failed_entities']}/{report['expected_entities']} failed, "
            f"{report['truncated_entities']} omitted by limit. {examples}",
            RuntimeWarning,
            stacklevel=2,
        )
    return frame


def require_complete_collection(frame: pd.DataFrame, entity_type: str) -> dict:
    report = frame.attrs.get("collection_report")
    if report is None or not report.get("collection_complete", False):
        raise RuntimeError(
            f"NBA {entity_type} collection is incomplete: "
            f"{report or 'collector did not provide a completeness report'}"
        )
    return report


def fetch_player_game_logs(
    settings: Settings, player_names: list[str] | set[str] | None = None
) -> pd.DataFrame:
    """Fetch season game logs in bulk and retain the requested active players.

    The league endpoint returns all player-game rows in one response. This avoids
    hundreds of sequential per-player requests and lets each post-gameweek run
    persist a complete refreshed snapshot through the cache merge in data.access.
    """
    from nba_api.stats.static import players

    season = _nba_season_str(settings.season)
    all_players = players.get_active_players()
    requested_names = [str(name).strip() for name in player_names] if player_names else []
    unmatched_requested: list[str] = []
    if requested_names:
        wanted = {player_key(name) for name in requested_names if player_key(name)}
        all_players = [p for p in all_players if player_key(p["full_name"]) in wanted]
        matched = {player_key(p["full_name"]) for p in all_players}
        unmatched_requested = [name for name in requested_names if player_key(name) not in matched]
        if isinstance(player_names, list):
            priority = {player_key(name): rank for rank, name in enumerate(requested_names)}
            all_players.sort(key=lambda p: priority.get(player_key(p["full_name"]), len(priority)))
    expected_players = len(all_players)
    truncated_players = 0
    if settings.max_player_log_entries > 0:
        truncated_players = max(0, len(all_players) - settings.max_player_log_entries)
        all_players = all_players[: settings.max_player_log_entries]
    failures: list[tuple[str, str]] = []
    try:
        out = _fetch_league_player_logs(season)
    except Exception as exc:
        failures.append(("NBA PlayerGameLogs endpoint", str(exc)))
        out = pd.DataFrame()

    if not out.empty:
        active_by_key = {player_key(p["full_name"]): p for p in all_players}
        if "PLAYER_NAME" in out:
            out["_player_key"] = out["PLAYER_NAME"].map(player_key)
            out = out.loc[out["_player_key"].isin(active_by_key)].copy()
            # Use the canonical active-roster identity and id for stable joins.
            out["PLAYER_NAME"] = out["_player_key"].map(
                lambda key: active_by_key[key]["full_name"]
            )
            out["PLAYER_ID"] = out["_player_key"].map(
                lambda key: active_by_key[key]["id"]
            )
            out = out.drop(columns="_player_key")
        else:
            failures.append(("NBA PlayerGameLogs endpoint", "PLAYER_NAME column missing"))
            out = pd.DataFrame()

    report = _collection_report(
        expected_players,
        len(all_players),
        failures,
        truncated_players,
    )
    report["unmatched_requested_players"] = unmatched_requested
    report["requested_entities"] = len(requested_names)
    report["unmatched_requested_count"] = len(unmatched_requested)
    if unmatched_requested:
        warnings.warn(
            "NBA player logs did not match these requested Dunkest names: "
            + ", ".join(unmatched_requested[:10]),
            RuntimeWarning,
            stacklevel=2,
        )
    if not out.empty:
        out["GAME_DATE"] = pd.to_datetime(out["GAME_DATE"])
        numeric_cols = [
            "MIN", "PTS", "REB", "AST", "STL", "BLK", "BLKA", "TOV",
            "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "PF",
        ]
        for c in numeric_cols:
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
        out["MIN"] = out["MIN"].apply(_minutes_to_float)
        out["PDK"] = out.apply(
            lambda row: pdk_from_boxscore_row(row, team_won=str(row.get("WL", "")).upper() == "W"),
            axis=1,
        )
        out["MATCHUP"] = out.get("MATCHUP", "")
        out["IS_HOME"] = out["MATCHUP"].astype(str).str.contains(" vs. ")
        out["OPPONENT"] = out["MATCHUP"].astype(str).str.replace(".*@ ", "", regex=True).str.replace(
            " vs. ", "", regex=True
        )
    return _attach_collection_report(out, report, "player game-log", failures)


def fetch_team_game_logs(settings: Settings) -> pd.DataFrame:
    from nba_api.stats.static import teams

    season = _nba_season_str(settings.season)
    frames: list[pd.DataFrame] = []
    all_teams = teams.get_teams()
    failures: list[tuple[str, str]] = []
    for t in all_teams:
        try:
            df = _fetch_team_log(t["id"], season)
            df["TEAM_ID"] = t["id"]
            df["TEAM_ABBREVIATION"] = t["abbreviation"]
            frames.append(df)
        except Exception as exc:
            failures.append((str(t["abbreviation"]), str(exc)))
            continue
        time.sleep(0.25)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not out.empty:
        out["GAME_DATE"] = pd.to_datetime(out["GAME_DATE"])
    report = _collection_report(len(all_teams), len(all_teams), failures)
    return _attach_collection_report(out, report, "team game-log", failures)


def fetch_schedule(settings: Settings) -> pd.DataFrame:
    from nba_api.stats.endpoints import leaguegamefinder

    season = _nba_season_str(settings.season)
    finder = leaguegamefinder.LeagueGameFinder(
        season_nullable=season,
        season_type_nullable="Regular Season",
        league_id_nullable="00",
    )
    df = finder.get_data_frames()[0]
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"])
    home = df[df["MATCHUP"].str.contains(" vs. ")].copy()
    home["HOME_TEAM"] = home["TEAM_ABBREVIATION"]
    home["AWAY_TEAM"] = home["MATCHUP"].str.split(" vs. ").str[-1]
    return home[
        ["GAME_ID", "GAME_DATE", "HOME_TEAM", "AWAY_TEAM", "PTS", "PLUS_MINUS"]
    ].drop_duplicates(subset=["GAME_ID", "HOME_TEAM"])


def fetch_future_schedule(settings: Settings) -> pd.DataFrame:
    from nba_api.stats.endpoints import scheduleleaguev2

    endpoint = scheduleleaguev2.ScheduleLeagueV2(
        season=settings.season, timeout=settings.http_timeout
    )
    games = endpoint.season_games.get_data_frame()
    columns = [
        "GAME_ID", "GAME_DATE", "HOME_TEAM", "AWAY_TEAM", "PTS",
        "PLUS_MINUS", "GAME_STATUS", "NBA_WEEK_NUMBER",
    ]
    if games.empty:
        return pd.DataFrame(columns=columns)

    home_score = pd.to_numeric(games["homeTeam_score"], errors="coerce")
    away_score = pd.to_numeric(games["awayTeam_score"], errors="coerce")
    is_final = pd.to_numeric(games["gameStatus"], errors="coerce").eq(3)
    schedule = pd.DataFrame(
        {
            "GAME_ID": games["gameId"].astype(str),
            "GAME_DATE": pd.to_datetime(games["gameDate"], errors="coerce"),
            "HOME_TEAM": games["homeTeam_teamTricode"].astype(str).str.upper(),
            "AWAY_TEAM": games["awayTeam_teamTricode"].astype(str).str.upper(),
            "PTS": home_score.where(is_final),
            "PLUS_MINUS": (home_score - away_score).where(is_final),
            "GAME_STATUS": games["gameStatus"],
            "NBA_WEEK_NUMBER": pd.to_numeric(games["weekNumber"], errors="coerce"),
        },
        columns=columns,
    ).dropna(subset=["GAME_DATE", "HOME_TEAM", "AWAY_TEAM"])
    return schedule.loc[schedule["NBA_WEEK_NUMBER"].gt(0)].reset_index(drop=True)
