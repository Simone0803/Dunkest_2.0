from __future__ import annotations

import argparse
import io
import time
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from nba_api.stats.endpoints import drafthistory, playergamelogs

from dunkest.names import player_key
from dunkest.rules.pdk import pdk_from_boxscore_row


TORVIK_PLAYER_COLUMNS = [
    "player_name", "team", "conf", "games", "min_pct", "o_rtg", "usage", "e_fg",
    "ts_pct", "orb_pct", "drb_pct", "ast_pct", "to_pct", "ftm", "fta", "ft_pct",
    "two_pm", "two_pa", "two_p_pct", "three_pm", "three_pa", "three_p_pct",
    "blk_pct", "stl_pct", "ftr", "class", "height", "number", "porpag", "adj_oe",
    "pfr", "year", "player_id", "hometown", "rec_rank", "ast_to", "rim_made",
    "rim_attempts", "mid_made", "mid_attempts", "rim_pct", "mid_pct", "dunks_made",
    "dunks_attempts", "dunks_pct", "pick", "drtg", "adrtg", "dporpag", "stops",
    "bpm", "obpm", "dbpm", "gbpm", "minutes", "ogbpm", "dgbpm", "oreb", "dreb",
    "treb", "ast", "stl", "blk", "pts", "role", "threat", "recruit_date",
]

OUTPUT_COLUMNS = [
    "player_name", "draft_year", "college_season", "position", "age", "draft_pick",
    "conference_strength", "pace", "games", "starts", "minutes_per_game",
    "points_per_game", "rebounds_per_game", "offensive_rebounds_per_game",
    "assists_per_game", "steals_per_game", "blocks_per_game", "turnovers_per_game",
    "field_goals_made_per_game", "field_goals_attempted_per_game",
    "free_throws_made_per_game", "free_throws_attempted_per_game",
    "three_pointers_made_per_game", "usage", "offensive_rating", "defensive_rating",
    "nba_pdk_per_min", "college_team", "college_conference", "college_player_id",
    "nba_rookie_games", "nba_rookie_minutes", "college_data_source", "nba_data_source",
    "data_retrieved_on",
]


def _cache_path(cache_dir: Path, stem: str, year: int, suffix: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{stem}_{year}.{suffix}"


def _fetch_torvik_players(year: int, cache_dir: Path, client: httpx.Client) -> pd.DataFrame:
    path = _cache_path(cache_dir, "torvik_players", year, "csv")
    if path.exists():
        raw = pd.read_csv(path, header=None)
    else:
        response = client.get(
            "https://barttorvik.com/getadvstats.php",
            params={"year": year, "csv": 1},
        )
        response.raise_for_status()
        raw = pd.read_csv(io.BytesIO(response.content), header=None)
        raw.to_csv(path, index=False, header=False)
    if raw.shape[1] != len(TORVIK_PLAYER_COLUMNS):
        raise RuntimeError(
            f"Formato Torvik inatteso per {year}: {raw.shape[1]} colonne, "
            f"attese {len(TORVIK_PLAYER_COLUMNS)}. Nessun dato finale scritto."
        )
    raw.columns = TORVIK_PLAYER_COLUMNS
    return raw


def _fetch_torvik_teams(year: int, cache_dir: Path, client: httpx.Client) -> pd.DataFrame:
    path = _cache_path(cache_dir, "torvik_teams", year, "csv")
    if not path.exists():
        response = client.get(f"https://barttorvik.com/{year}_team_results.csv")
        response.raise_for_status()
        path.write_bytes(response.content)

    # Older Torvik exports omit the rank value in each row and, in a few years,
    # have a malformed final header. Align by observed row width instead of
    # letting pandas silently shift every team field one column to the left.
    raw_rows = list(pd.read_csv(path, header=None, dtype=str).itertuples(index=False, name=None))
    headers = [str(value) for value in raw_rows[0]]
    if headers and headers[-1].strip().casefold() == "fun rk, adjt":
        headers[-1:] = ["Fun Rk", "adjt"]
    body = raw_rows[1:]
    widths = {len(row) for row in body if row}
    if len(widths) != 1:
        raise RuntimeError(f"Righe Torvik squadra di larghezza incoerente per {year}: {widths}")
    row_width = next(iter(widths))
    if len(headers) == row_width + 1 and headers[0].strip().casefold() == "rank":
        headers = headers[1:]
    if len(headers) != row_width:
        raise RuntimeError(f"Intestazione Torvik squadra incompatibile per {year}: {len(headers)} vs {row_width}")
    frame = pd.DataFrame(body, columns=headers)
    return frame


def _fetch_draft(year: int, cache_dir: Path) -> pd.DataFrame:
    path = _cache_path(cache_dir, "nba_draft", year, "csv")
    if path.exists():
        return pd.read_csv(path)
    frame = drafthistory.DraftHistory(season_year_nullable=year, timeout=35).get_data_frames()[0]
    frame.to_csv(path, index=False)
    time.sleep(0.5)
    return frame


def _fetch_nba_rookie_logs(draft_year: int, cache_dir: Path) -> pd.DataFrame:
    path = _cache_path(cache_dir, "nba_rookie_logs", draft_year, "parquet")
    if path.exists():
        return pd.read_parquet(path)
    season = f"{draft_year}-{(draft_year + 1) % 100:02d}"
    frame = playergamelogs.PlayerGameLogs(
        season_nullable=season,
        season_type_nullable="Regular Season",
        league_id_nullable="00",
        timeout=45,
    ).get_data_frames()[0]
    frame.to_parquet(path, index=False)
    time.sleep(0.75)
    return frame


def _team_context(players: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    context = teams.copy()
    context["_team_key"] = context["team"].map(player_key)
    context["_team_sos"] = pd.to_numeric(context.get("sos"), errors="coerce")
    context["_team_pace"] = pd.to_numeric(context.get("adjt"), errors="coerce")
    context["_team_oe"] = pd.to_numeric(context.get("adjoe"), errors="coerce")
    context["_team_de"] = pd.to_numeric(context.get("adjde"), errors="coerce")
    context = context.drop_duplicates("_team_key", keep="last").set_index("_team_key")
    player_rows = players.copy()
    player_rows["_team_key"] = player_rows["team"].map(player_key)
    for column, target in (
        ("_team_sos", "conference_strength"), ("_team_pace", "pace"),
        ("_team_oe", "team_offensive_rating"), ("_team_de", "team_defensive_rating"),
    ):
        player_rows[target] = player_rows["_team_key"].map(context[column])
    return player_rows


def _position(role: object) -> str:
    label = str(role or "").strip().upper()
    if any(token in label for token in ("PG", "SG", "GUARD", "COMBO G", "SCORING G", "POINT")):
        return "G"
    if any(token in label for token in ("CENTER", "BIG", "ROLL C")) or label == "C":
        return "C"
    if any(token in label for token in ("WING", "FORWARD", "STRETCH", "F")):
        return "F"
    if label.endswith(" C"):
        return "C"
    if label.endswith(" G"):
        return "G"
    return "F"


def _college_rows_for_class(draft: pd.DataFrame, college: pd.DataFrame, draft_year: int) -> pd.DataFrame:
    picks = draft.copy()
    picks["ORGANIZATION_TYPE"] = picks["ORGANIZATION_TYPE"].fillna("").astype(str)
    picks = picks[picks["ORGANIZATION_TYPE"].str.contains("college|university", case=False)]
    picks["_player_key"] = picks["PLAYER_NAME"].map(player_key)

    stats = college.copy()
    stats["_player_key"] = stats["player_name"].map(player_key)
    stats["games"] = pd.to_numeric(stats["games"], errors="coerce").fillna(0)
    stats = stats[stats["games"].gt(0)]
    stat_by_name = {key: group for key, group in stats.groupby("_player_key")}

    out: list[dict] = []
    for _, pick in picks.iterrows():
        group = stat_by_name.get(pick["_player_key"])
        if group is None:
            continue
        # A small number of college transfers have multiple rows in Torvik.
        # Combine their counting stats with games-played weights.
        row = group.sort_values("games").iloc[-1].copy()
        games = float(group["games"].sum())

        def weighted(column: str) -> float:
            values = pd.to_numeric(group[column], errors="coerce")
            weights = pd.to_numeric(group["games"], errors="coerce")
            good = values.notna() & weights.gt(0)
            return float(np.average(values[good], weights=weights[good])) if good.any() else np.nan

        for col in ["minutes", "usage", "o_rtg", "drtg", "oreb", "dreb", "treb", "ast", "stl", "blk", "pts"]:
            row[col] = weighted(col)
        for col in ["ftm", "fta", "two_pm", "two_pa", "three_pm", "three_pa"]:
            row[col] = pd.to_numeric(group[col], errors="coerce").fillna(0).sum()
        row["games"] = games
        row["ast_to"] = weighted("ast_to")
        row["conference_strength"] = weighted("conference_strength")
        row["pace"] = weighted("pace")

        birth_date = pd.to_datetime(row.get("recruit_date"), errors="coerce")
        age = ((pd.Timestamp(date(draft_year, 6, 1)) - birth_date).days / 365.25) if pd.notna(birth_date) else np.nan
        mpg = pd.to_numeric(row.get("minutes"), errors="coerce")
        ppg = pd.to_numeric(row.get("pts"), errors="coerce")
        if pd.isna(mpg) or mpg <= 0 or pd.isna(ppg):
            # Do not create a nominally matched row without a usable college
            # rate. It cannot train the calibration or score the current class.
            continue
        gp = max(float(row["games"]), 1.0)
        ast = pd.to_numeric(row.get("ast"), errors="coerce")
        ratio = pd.to_numeric(row.get("ast_to"), errors="coerce")
        to_per_game = ast / ratio if pd.notna(ast) and pd.notna(ratio) and ratio > 0 else np.nan
        row_team = str(row.get("team", ""))
        row_conf = str(row.get("conf", ""))
        out.append(
            {
                "player_name": str(pick["PLAYER_NAME"]),
                "draft_year": draft_year,
                "college_season": f"{draft_year - 1}-{draft_year % 100:02d}",
                "position": _position(row.get("role")),
                "age": age,
                "draft_pick": pd.to_numeric(pick["OVERALL_PICK"], errors="coerce"),
                "conference_strength": row.get("conference_strength"),
                "pace": row.get("pace"),
                "games": games,
                "starts": np.nan,
                "minutes_per_game": mpg,
                "points_per_game": ppg,
                "rebounds_per_game": pd.to_numeric(row.get("treb"), errors="coerce"),
                "offensive_rebounds_per_game": pd.to_numeric(row.get("oreb"), errors="coerce"),
                "assists_per_game": ast,
                "steals_per_game": pd.to_numeric(row.get("stl"), errors="coerce"),
                "blocks_per_game": pd.to_numeric(row.get("blk"), errors="coerce"),
                "turnovers_per_game": to_per_game,
                "field_goals_made_per_game": (float(row["two_pm"]) + float(row["three_pm"])) / gp,
                "field_goals_attempted_per_game": (float(row["two_pa"]) + float(row["three_pa"])) / gp,
                "free_throws_made_per_game": float(row["ftm"]) / gp,
                "free_throws_attempted_per_game": float(row["fta"]) / gp,
                "three_pointers_made_per_game": float(row["three_pm"]) / gp,
                "usage": pd.to_numeric(row.get("usage"), errors="coerce"),
                "offensive_rating": pd.to_numeric(row.get("o_rtg"), errors="coerce"),
                "defensive_rating": pd.to_numeric(row.get("drtg"), errors="coerce"),
                "nba_pdk_per_min": np.nan,
                "college_team": row_team,
                "college_conference": row_conf,
                "college_player_id": row.get("player_id"),
                "nba_rookie_games": np.nan,
                "nba_rookie_minutes": np.nan,
                "college_data_source": f"Bart Torvik {draft_year - 1} player/team season data",
                "nba_data_source": "NBA Stats player game logs",
            }
        )
    return pd.DataFrame(out)


def _rookie_outcomes(draft: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    by_id = draft.copy()
    by_id["PERSON_ID"] = pd.to_numeric(by_id["PERSON_ID"], errors="coerce")
    logs = logs.copy()
    logs["PLAYER_ID"] = pd.to_numeric(logs["PLAYER_ID"], errors="coerce")
    logs["MIN"] = pd.to_numeric(logs["MIN"], errors="coerce").fillna(0.0)
    logs = logs[logs["MIN"].gt(0)].copy()
    logs["PDK"] = logs.apply(
        lambda row: pdk_from_boxscore_row(row, team_won=str(row.get("WL", "")).upper() == "W"),
        axis=1,
    )
    totals = logs.groupby("PLAYER_ID").agg(
        rookie_games=("GAME_ID", "nunique"), rookie_minutes=("MIN", "sum"), rookie_pdk=("PDK", "sum")
    )
    by_id = by_id.set_index("PERSON_ID").join(totals, how="left").reset_index()
    by_id["nba_pdk_per_min"] = by_id["rookie_pdk"] / by_id["rookie_minutes"]
    return by_id[["PLAYER_NAME", "nba_pdk_per_min", "rookie_games", "rookie_minutes"]].rename(
        columns={"PLAYER_NAME": "player_name", "rookie_games": "nba_rookie_games", "rookie_minutes": "nba_rookie_minutes"}
    )


def build_dataset(from_draft_year: int, current_draft_year: int, output: Path, cache_dir: Path) -> pd.DataFrame:
    all_rows: list[pd.DataFrame] = []
    with httpx.Client(timeout=40.0, follow_redirects=True, headers={"User-Agent": "DunkestRookiePrior/1.0"}) as client:
        college_by_year: dict[int, pd.DataFrame] = {}
        for college_year in range(from_draft_year, current_draft_year + 1):
            player_stats = _fetch_torvik_players(college_year, cache_dir, client)
            team_stats = _fetch_torvik_teams(college_year, cache_dir, client)
            college_by_year[college_year] = _team_context(player_stats, team_stats)
            print(f"College {college_year}: {len(player_stats):,} righe NCAA caricate")

    for draft_year in range(from_draft_year, current_draft_year + 1):
        draft = _fetch_draft(draft_year, cache_dir)
        # Torvik year is the calendar year in which the NCAA season ends:
        # the 2025-26 college season feeds the 2026 NBA draft class.
        college = college_by_year[draft_year]
        rows = _college_rows_for_class(draft, college, draft_year)
        if draft_year < current_draft_year:
            logs = _fetch_nba_rookie_logs(draft_year, cache_dir)
            outcomes = _rookie_outcomes(draft, logs)
            rows = rows.merge(outcomes, on="player_name", how="left", suffixes=("", "_outcome"))
            rows["nba_pdk_per_min"] = rows["nba_pdk_per_min_outcome"]
            rows["nba_rookie_games"] = rows["nba_rookie_games_outcome"]
            rows["nba_rookie_minutes"] = rows["nba_rookie_minutes_outcome"]
            rows = rows.drop(columns=[c for c in rows.columns if c.endswith("_outcome")])
        all_rows.append(rows)
        labelled = int(pd.to_numeric(rows.get("nba_pdk_per_min"), errors="coerce").notna().sum())
        print(f"Draft {draft_year}: {len(rows)} college match, {labelled} esiti rookie NBA")

    combined = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame(columns=OUTPUT_COLUMNS)
    combined = combined.drop_duplicates(["draft_year", "player_name"], keep="last")
    combined["data_retrieved_on"] = date.today().isoformat()
    combined = combined.reindex(columns=OUTPUT_COLUMNS)
    labels = pd.to_numeric(combined["nba_pdk_per_min"], errors="coerce")
    historical = combined[labels.notna()]
    classes = historical["draft_year"].nunique()
    if len(historical) < 40 or classes < 4:
        raise RuntimeError(
            f"Abbinamenti insufficienti ({len(historical)} esiti, {classes} classi); "
            "CSV finale non sovrascritto."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False, float_format="%.6f")
    print(
        f"Salvato {output}: {len(combined)} righe, {len(historical)} esiti NBA "
        f"in {classes} classi; classe corrente {current_draft_year}: "
        f"{int(combined['draft_year'].eq(current_draft_year).sum())} giocatori."
    )
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea i dati reali per il prior rookie NCAA→NBA.")
    parser.add_argument("--from-draft-year", type=int, default=2014)
    parser.add_argument("--current-draft-year", type=int, default=2026)
    parser.add_argument("--output", type=Path, default=Path("data/rookie_college.csv"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/rookie_prior"))
    args = parser.parse_args()
    build_dataset(args.from_draft_year, args.current_draft_year, args.output, args.cache_dir)


if __name__ == "__main__":
    main()
