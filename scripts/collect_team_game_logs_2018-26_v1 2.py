from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import LeagueGameLog

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "team_game_logs_2018-26_v1.parquet"
META = OUT.with_suffix(".parquet.meta.json")
SEASONS = [f"{year}-{str(year + 1)[-2:]}" for year in range(2018, 2026)]


def main() -> None:
    if OUT.exists() or META.exists():
        raise SystemExit(
            f"Refusing to overwrite versioned historical data: {OUT} or {META} already exists."
        )

    frames: list[pd.DataFrame] = []
    provenance: list[dict] = []
    for season in SEASONS:
        print(f"Downloading NBA team game logs for {season}...", flush=True)
        frame = LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
            timeout=30,
        ).get_data_frames()[0]
        if frame.empty:
            raise RuntimeError(f"NBA API returned no team games for {season}")
        required = {"GAME_ID", "GAME_DATE", "MATCHUP", "TEAM_ABBREVIATION", "PTS"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise RuntimeError(f"NBA API schema for {season} missing columns: {missing}")
        frame = frame.copy()
        frame["SEASON"] = season
        frame["GAME_DATE"] = pd.to_datetime(frame["GAME_DATE"], errors="coerce")
        frame["GAME_ID"] = frame["GAME_ID"].astype(str)
        frame["TEAM_ABBREVIATION"] = frame["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
        frame["PTS"] = pd.to_numeric(frame["PTS"], errors="coerce")
        unique_team_rows = frame.drop_duplicates(["GAME_ID", "TEAM_ABBREVIATION"])
        game_team_counts = unique_team_rows.groupby("GAME_ID")["TEAM_ABBREVIATION"].nunique()
        complete_ids = set(game_team_counts[game_team_counts == 2].index)
        frame = unique_team_rows.loc[unique_team_rows["GAME_ID"].isin(complete_ids)].copy()
        if frame.empty:
            raise RuntimeError(f"No complete games after validation for {season}")
        provenance.append({
            "season": season,
            "rows": int(len(frame)),
            "games": int(frame["GAME_ID"].nunique()),
            "teams": int(frame["TEAM_ABBREVIATION"].nunique()),
            "date_min": str(frame["GAME_DATE"].min().date()),
            "date_max": str(frame["GAME_DATE"].max().date()),
            "source": "nba_api.stats.endpoints.LeagueGameLog (team, Regular Season)",
        })
        frames.append(frame)
        time.sleep(0.8)

    combined = pd.concat(frames, ignore_index=True)
    # A game ID is unique across NBA seasons, but explicitly validate the composite key.
    if combined.duplicated(["SEASON", "GAME_ID", "TEAM_ABBREVIATION"]).any():
        raise RuntimeError("Duplicate season/game/team rows in combined historical logs")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUT, index=False)
    META.write_text(json.dumps({
        "dataset": str(OUT.relative_to(ROOT)),
        "source": "NBA Stats API via nba_api LeagueGameLog",
        "season_type": "Regular Season",
        "seasons": provenance,
        "total_rows": int(len(combined)),
        "total_games": int(combined.groupby("SEASON")["GAME_ID"].nunique().sum()),
        "retrieved_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "validation": {
            "unique_season_game_team": True,
            "only_complete_two_team_games": True,
            "player_game_aggregation_used": False,
        },
    }, indent=2) + "\n")
    print(f"Saved {len(combined):,} team-game rows to {OUT}")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
