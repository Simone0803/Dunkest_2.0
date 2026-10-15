#!/usr/bin/env python3
"""Compare archived Dunkest player outcomes with NBA game logs.

Run from the repository root:
  ./.venv/bin/python scripts/compare_dunkest_nba_history.py

Read-only: no source data is modified.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
HISTORY_CANDIDATES = [
    DATA / "plusvalenza_history_25_through_gw91_v2.parquet",
    DATA / "plusvalenza_history_nba_25_through_gw91_v3.parquet",
]
LOG_PATH = DATA / "player_game_logs_2025-26.parquet"


def norm(value: object) -> str:
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", value.lower())


def first_existing(paths: list[Path]) -> Path | None:
    return next((p for p in paths if p.exists()), None)


def main() -> None:
    hist_path = first_existing(HISTORY_CANDIDATES)
    if hist_path is None:
        raise SystemExit("No historical Dunkest plusvalenza file found.")
    if not LOG_PATH.exists():
        raise SystemExit(f"NBA log file not found: {LOG_PATH}")

    hist = pd.read_parquet(hist_path).copy()
    nba = pd.read_parquet(LOG_PATH).copy()

    required_hist = {"player_name", "team_code", "pdk", "gameweek"}
    required_nba = {"PLAYER_NAME", "TEAM_ABBREVIATION", "GAME_DATE", "GAME_ID", "PDK"}
    if not required_hist.issubset(hist.columns):
        raise SystemExit(f"Missing Dunkest columns: {sorted(required_hist - set(hist.columns))}")
    if not required_nba.issubset(nba.columns):
        raise SystemExit(f"Missing NBA columns: {sorted(required_nba - set(nba.columns))}")

    hist["name_key"] = hist["player_name"].map(norm)
    hist["team_key"] = hist["team_code"].astype(str).str.upper().str.strip()
    hist["pdk_num"] = pd.to_numeric(hist["pdk"], errors="coerce")
    hist["gw_num"] = pd.to_numeric(hist["gameweek"], errors="coerce")
    nba["name_key"] = nba["PLAYER_NAME"].map(norm)
    nba["team_key"] = nba["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    nba["pdk_num"] = pd.to_numeric(nba["PDK"], errors="coerce")
    nba["date_parsed"] = pd.to_datetime(nba["GAME_DATE"], errors="coerce")

    nba_players = set(nba["name_key"])
    hist_players = set(hist["name_key"])
    overlap = hist_players & nba_players
    print(f"History file: {hist_path.name}")
    print(f"History rows/players/teams/gameweeks: {len(hist)}/{hist['name_key'].nunique()}/{hist['team_key'].nunique()}/{hist['gw_num'].nunique()}")
    print(f"NBA log rows/players/teams/games: {len(nba)}/{nba['name_key'].nunique()}/{nba['team_key'].nunique()}/{nba['GAME_ID'].nunique()}")
    print(f"Player-name overlap: {len(overlap)} of {len(hist_players)} historical players")

    print("\nTeams represented in Dunkest history:")
    print(hist["team_key"].value_counts(dropna=False).to_string())
    print("\nHistorical player-name match by player:")
    player_rows = []
    for name, group in hist.groupby("player_name", dropna=False):
        nk = norm(name)
        matches = nba.loc[nba["name_key"].eq(nk)]
        team_overlap = sorted(set(group["team_key"]) & set(matches["team_key"]))
        player_rows.append({
            "player": name,
            "history_rows": len(group),
            "history_teams": ",".join(sorted(group["team_key"].unique())),
            "nba_rows_same_name": len(matches),
            "nba_teams_same_name": ",".join(sorted(matches["team_key"].unique())),
            "team_match": bool(team_overlap),
        })
    player_report = pd.DataFrame(player_rows).sort_values(["team_match", "player"])
    print(player_report.to_string(index=False, max_rows=100))

    matched_hist = hist.loc[hist["name_key"].isin(overlap)].copy()
    matched_nba = nba.loc[nba["name_key"].isin(overlap)].copy()
    name_team_pairs = set(zip(matched_nba["name_key"], matched_nba["team_key"]))
    matched_hist["name_team_in_nba"] = [
        (n, t) in name_team_pairs for n, t in zip(matched_hist["name_key"], matched_hist["team_key"])
    ]
    print("\nHistorical rows whose player+team pair exists in NBA logs:")
    print(f"{int(matched_hist['name_team_in_nba'].sum())} / {len(matched_hist)}")

    # A score-value match is only a diagnostic, not proof that a row belongs to
    # a particular game: the same score can occur in multiple games.
    valid_hist = matched_hist.loc[
        matched_hist["name_team_in_nba"] & matched_hist["pdk_num"].notna()
    ]
    valid_nba = matched_nba.loc[matched_nba["pdk_num"].notna()]
    score_pairs = set(
        zip(valid_nba["name_key"], valid_nba["team_key"], valid_nba["pdk_num"].round(4))
    )
    valid_hist["score_value_found_in_nba"] = [
        (n, t, round(float(s), 4)) in score_pairs
        for n, t, s in zip(valid_hist["name_key"], valid_hist["team_key"], valid_hist["pdk_num"])
    ]
    print("\nHistorical rows with a same-player, same-team, same-score value somewhere in NBA logs:")
    print(f"{int(valid_hist['score_value_found_in_nba'].sum())} / {len(valid_hist)}")
    print("WARNING: this score-only match is not a date/game match and must not be treated as one.")

    print("\nHistorical rows by gameweek (first 20):")
    print(
        hist.groupby("gw_num").agg(
            rows=("player_name", "size"),
            players=("name_key", "nunique"),
            teams=("team_key", "nunique"),
        ).head(20).to_string()
    )
    print("\nThis diagnostic does not train a model or claim predictive performance.")


if __name__ == "__main__":
    main()
