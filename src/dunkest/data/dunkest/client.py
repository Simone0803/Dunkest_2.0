from __future__ import annotations

from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from dunkest.config import Settings
from dunkest.data.http_client import get_json, get_text
from dunkest.rules.pdk import normalize_position

POSITION_MAP = {"1": "G", "2": "F", "3": "C", "G": "G", "F": "F", "C": "C"}


def _all_teams_params() -> list[tuple[str, str]]:
    return [("teams[]", str(i)) for i in range(1, 31)]


def _all_positions_params() -> list[tuple[str, str]]:
    return [("positions[]", str(i)) for i in range(1, 4)]


def fetch_week_rounds(settings: Settings, week_number: int) -> list[str]:
    url = f"{settings.dunkest_api_base}/stats/dunkest/week/rounds"
    data = get_json(
        url,
        params={"season_id": settings.season_id, "week_number": week_number},
        timeout=settings.http_timeout,
    )
    return [str(x) for x in data]


def fetch_stats_table(settings: Settings, **table_status: Any) -> pd.DataFrame:
    url = f"{settings.dunkest_api_base}/stats/table"
    params: list[tuple[str, str]] = []
    for key, value in table_status.items():
        if isinstance(value, list):
            for item in value:
                params.append((f"{key}[]", str(item)))
        else:
            params.append((key, str(value)))
    raw = get_json(url, params=params, timeout=settings.http_timeout)
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    if df.empty:
        return df
    df["player_name"] = (df["first_name"].astype(str) + " " + df["last_name"].astype(str)).str.strip()
    df["role"] = df["position_id"].astype(str).map(POSITION_MAP)
    df["role"] = df["role"].fillna(df["position"].apply(normalize_position))
    df["cr"] = pd.to_numeric(df["cr"], errors="coerce").fillna(0.0)
    df["pdk"] = pd.to_numeric(df.get("pdk"), errors="coerce")
    str_cols = {
        "player_name",
        "first_name",
        "last_name",
        "slug",
        "position",
        "role",
        "team_code",
        "team_name",
        "id",
        "team_id",
        "position_id",
    }
    for col in df.columns:
        if col in str_cols:
            df[col] = df[col].astype(str)
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_dunkest_gameweek_players(settings: Settings, gameweek: int) -> pd.DataFrame:
    rounds = fetch_week_rounds(settings, gameweek)
    # Dunkest's public stats table is scoped by both gameweek and round.
    # Never guess the round IDs: historical seasons and playoff calendars do
    # not guarantee a fixed number of turns, and invented rounds can return a
    # plausible but incorrect PDK/PLUS sample.
    if not rounds:
        return pd.DataFrame()
    params: dict[str, Any] = {
        "season_id": settings.season_id,
        "mode": "dunkest",
        "stats_type": "avg",
        "weeks": [gameweek],
        "rounds": rounds,
        "teams": [str(i) for i in range(1, 31)],
        "positions": ["1", "2", "3"],
        "min_cr": settings.min_cr,
        "max_cr": settings.max_cr,
        "sort_by": "pdk",
        "sort_order": "desc",
    }
    df = fetch_stats_table(settings, **params)
    if not df.empty:
        df["gameweek"] = gameweek
        # Keep the exact source scope beside the aggregate. This does not
        # claim that the API provides per-NBA-game PDK: it records which
        # Dunkest turns were included in the returned gameweek statistics.
        df["dunkest_rounds"] = ",".join(rounds)
    return df


def fetch_nba_season_players(settings: Settings) -> pd.DataFrame:
    params: dict[str, Any] = {
        "season_id": settings.season_id,
        "mode": "nba",
        "stats_type": "avg",
        "date_from": settings.nba_season_start,
        "date_to": settings.nba_season_end,
        "teams": [str(i) for i in range(1, 31)],
        "positions": ["1", "2", "3"],
        "min_cr": settings.min_cr,
        "max_cr": settings.max_cr,
        "sort_by": "pdk",
        "sort_order": "desc",
    }
    return fetch_stats_table(settings, **params)


def fetch_coach_cr_table(settings: Settings, gameweek: int) -> pd.DataFrame:
    """Coach CR from Dunkest coach stats board (entity=coach when supported)."""
    params: dict[str, Any] = {
        "season_id": settings.season_id,
        "mode": "dunkest",
        "stats_type": "avg",
        "weeks": [gameweek],
        "teams": [str(i) for i in range(1, 31)],
        "entity": "coach",
        "min_cr": 1,
        "max_cr": settings.max_cr,
    }
    df = fetch_stats_table(settings, **params)
    if df.empty or "position" in df.columns and df["position"].iloc[0] in ("G", "F", "C"):
        # API returned players — use NBA mode coach-like rows not available; build from config later
        return pd.DataFrame()
    return df


def scrape_injuries(settings: Settings) -> pd.DataFrame:
    html = get_text("https://www.dunkest.com/it/nba/infortuni", timeout=settings.http_timeout)
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict[str, str]] = []
    for table in soup.select("table.injuries__table"):
        headers = [th.get_text(strip=True) for th in table.select("th")]
        for tr in table.select("tbody tr"):
            cells = [td.get_text(strip=True) for td in tr.select("td")]
            if not cells:
                continue
            row = dict(zip(headers, cells))
            if "Giocatore" in row:
                rows.append(
                    {
                        "player_name": row.get("Giocatore", ""),
                        "status": row.get("Stato", row.get("Status", "OUT")),
                        "team": row.get("Squadra", ""),
                    }
                )
    return pd.DataFrame(rows)
