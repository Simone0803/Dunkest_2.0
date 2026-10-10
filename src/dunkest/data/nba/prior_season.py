from __future__ import annotations

import time

import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats, playergamelogs
from nba_api.stats.static import players

from dunkest.config import Settings
from dunkest.data.nba.collector import (
    _attach_collection_report,
    _collection_report,
    _fetch_player_log,
)
from dunkest.names import player_key
from dunkest.rules.pdk import pdk_from_boxscore_row


def fetch_prior_season_game_logs(settings: Settings) -> pd.DataFrame:
    """Game logs for feature_season (the completed NBA season before the opener)."""
    season = settings.feature_season
    name_filter: set[str] | None = None
    if settings.opening_player_names:
        name_filter = {player_key(n) for n in settings.opening_player_names}

    # The league-wide endpoint returns the completed season in one request and
    # avoids the old alphabetical 120-player truncation / hundreds of requests.
    try:
        out = playergamelogs.PlayerGameLogs(
            season_nullable=season,
            season_type_nullable="Regular Season",
            league_id_nullable="00",
            timeout=settings.http_timeout,
        ).get_data_frames()[0]
        if not out.empty:
            if name_filter:
                out = out[out["PLAYER_NAME"].map(player_key).isin(name_filter)].copy()
            out["GAME_DATE"] = pd.to_datetime(out["GAME_DATE"])
            for c in ["MIN", "PTS", "REB", "AST", "STL", "BLK", "BLKA", "TOV", "OREB", "DREB", "FGM", "FGA", "FTM", "FTA", "FG3M"]:
                if c in out.columns:
                    out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
            out["PDK"] = out.apply(
                lambda row: pdk_from_boxscore_row(
                    row, team_won=str(row.get("WL", "")).upper() == "W"
                ), axis=1
            )
            out["MATCHUP"] = out.get("MATCHUP", "")
            out["OPPONENT"] = out["MATCHUP"].astype(str).str.replace(".*@ ", "", regex=True).str.replace(" vs. ", "", regex=True)
            expected = int(out["PLAYER_NAME"].nunique()) if "PLAYER_NAME" in out else 1
            report = _collection_report(expected, expected, [])
            return _attach_collection_report(
                out, report, "prior-season player game-log", []
            )
    except Exception:
        # Keep the per-player and season-average fallback for transient NBA API
        # failures and nba_api versions without the league-wide endpoint.
        pass

    active = players.get_players()
    if name_filter:
        active = [p for p in active if player_key(p["full_name"]) in name_filter]
    expected_players = len(active)
    truncated_players = 0
    if settings.max_player_log_entries > 0:
        truncated_players = max(0, len(active) - settings.max_player_log_entries)
        active = active[: settings.max_player_log_entries]
    frames: list[pd.DataFrame] = []
    failures: list[tuple[str, str]] = []
    for i, p in enumerate(active):
        try:
            chunk = _fetch_player_log(p["id"], season)
            if chunk.empty:
                continue
            chunk["PLAYER_ID"] = p["id"]
            chunk["PLAYER_NAME"] = p["full_name"]
            frames.append(chunk)
        except Exception as exc:
            failures.append((str(p["full_name"]), str(exc)))
            continue
        if i % 20 == 0:
            time.sleep(0.35)

    if frames:
        out = pd.concat(frames, ignore_index=True)
        out["GAME_DATE"] = pd.to_datetime(out["GAME_DATE"])
        for c in ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "OREB", "DREB", "FGM", "FGA", "FTM", "FTA", "FG3M"]:
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
        out["MIN"] = out["MIN"].apply(
            lambda x: float(str(x).split(":")[0]) if isinstance(x, str) and ":" in str(x) else float(x)
        )
        out["PDK"] = out.apply(
            lambda row: pdk_from_boxscore_row(
                row, team_won=str(row.get("WL", "")).upper() == "W"
            ),
            axis=1,
        )
        out["MATCHUP"] = out.get("MATCHUP", "")
        out["OPPONENT"] = out["MATCHUP"].astype(str).str.replace(".*@ ", "", regex=True).str.replace(
            " vs. ", "", regex=True
        )
        report = _collection_report(
            expected_players, len(active), failures, truncated_players
        )
        return _attach_collection_report(
            out, report, "prior-season player game-log", failures
        )

    return fetch_prior_season_dashboard_fallback(season)


def fetch_prior_season_dashboard_fallback(season: str) -> pd.DataFrame:
    """Single-row-per-player fallback from season averages."""
    dash = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season, per_mode_detailed="PerGame", season_type_all_star="Regular Season"
    ).get_data_frames()[0]
    rows: list[dict] = []
    for _, r in dash.iterrows():
        row = {
            "PLAYER_NAME": r["PLAYER_NAME"],
            "GAME_DATE": pd.Timestamp("2025-04-01"),
            "MIN": float(r.get("MIN", 0)),
            "PTS": float(r.get("PTS", 0)),
            "REB": float(r.get("REB", 0)),
            "AST": float(r.get("AST", 0)),
            "STL": float(r.get("STL", 0)),
            "BLK": float(r.get("BLK", 0)),
            "TOV": float(r.get("TOV", 0)),
            "OREB": float(r.get("OREB", 0)),
            "DREB": float(r.get("REB", 0)) - float(r.get("OREB", 0)),
            "FGM": float(r.get("FGM", 0)),
            "FGA": float(r.get("FGA", 0)),
            "FTM": float(r.get("FTM", 0)),
            "FTA": float(r.get("FTA", 0)),
            "FG3M": float(r.get("FG3M", 0)),
            "BLKA": float(r.get("BLKA", 0)),
            "TEAM_ABBREVIATION": r.get("TEAM_ABBREVIATION", ""),
            "OPPONENT": "",
            "MATCHUP": "",
        }
        row["PDK"] = pdk_from_boxscore_row(pd.Series(row))
        rows.append(row)
    out = pd.DataFrame(rows)
    expected = int(out["PLAYER_NAME"].nunique()) if not out.empty else 0
    report = _collection_report(expected, expected, [])
    return _attach_collection_report(
        out, report, "prior-season player dashboard", []
    )
