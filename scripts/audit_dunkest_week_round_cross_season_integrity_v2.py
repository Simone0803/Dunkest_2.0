#!/usr/bin/env python3
"""Read-only audit for weekly-round rows that exactly match NBA boxscores in another season.

Uses player/team/minutes plus a compact boxscore signature. A cross-season row by
itself is only a candidate; a multi-player match to one different NBA game is
stronger evidence of source-scope contamination. Outputs are versioned and never
overwrite prior reports or source data.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data/raw/dunkest_history_v2"
NBA_DIR = ROOT / "data/raw/nba_historical_logs_2018-25_v1"
REPORT_DIR = ROOT / "reports/audit"
OUT_JSON = REPORT_DIR / "dunkest_week_round_cross_season_integrity_v2.json"
OUT_MD = REPORT_DIR / "dunkest_week_round_cross_season_integrity_v2.md"
OUT_CSV = REPORT_DIR / "dunkest_week_round_cross_season_integrity_v2.csv"
EXPECTED_SEASONS = {"5": "2020-21", "7": "2021-22", "9": "2022-23", "13": "2023-24", "19": "2024-25"}
STAT_KEYS = [("pts", "PTS"), ("reb", "REB"), ("ast", "AST"), ("stl", "STL"), ("blk", "BLK"), ("tov", "TOV"), ("plus_minus", "PLUS_MINUS")]


def main() -> None:
    for path in (OUT_JSON, OUT_MD, OUT_CSV):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing versioned output: {path}")
    table_paths = sorted(DATA_DIR.glob("season_*_week_*_round_*_avg.parquet"))
    nba_paths = sorted(NBA_DIR.glob("nba_player_game_logs_*.parquet"))
    if not table_paths or not nba_paths:
        raise SystemExit("Missing weekly-round tables or NBA historical logs.")

    tables = []
    for path in table_paths:
        frame = pd.read_parquet(path)
        frame["source_file"] = path.name
        frame["table_season_id"] = path.stem.split("_")[1]
        tables.append(frame)
    table = pd.concat(tables, ignore_index=True, sort=False).reset_index(drop=True)
    table["_row_id"] = range(len(table))
    table["k_name"] = table["player_name"].astype(str).str.casefold().str.strip()
    table["k_team"] = table["team_code"].astype(str).str.upper().str.strip()
    
    nba_frames = []
    for path in nba_paths:
        frame = pd.read_parquet(path)
        frame["nba_season_label"] = path.stem.replace("nba_player_game_logs_", "")
        nba_frames.append(frame)
    nba = pd.concat(nba_frames, ignore_index=True, sort=False)
    nba["k_name"] = nba["PLAYER_NAME"].astype(str).str.casefold().str.strip()
    nba["k_team"] = nba["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    keys = ["k_name", "k_team"]
    for table_col, nba_col in STAT_KEYS:
        key = f"k_{table_col}"
        table[key] = pd.to_numeric(table[table_col], errors="coerce").fillna(-999).astype(float)
        nba[key] = pd.to_numeric(nba[nba_col], errors="coerce").fillna(-999).astype(float)
        keys.append(key)

    lookup = nba[keys + ["nba_season_label", "GAME_DATE", "GAME_ID", "MATCHUP"]].drop_duplicates()
    matched = table[["_row_id", "source_file", "table_season_id", "player_name", "team_code", "pdk", "pts", "min", "plus_minus"] + keys].merge(lookup, on=keys, how="left")
    matched = matched.drop_duplicates(["_row_id", "nba_season_label", "GAME_DATE", "GAME_ID", "MATCHUP"])
    summary = matched.groupby("_row_id", sort=False).agg(
        candidate_seasons=("nba_season_label", lambda s: tuple(sorted(set(s.dropna().astype(str))))),
        candidate_games=("GAME_ID", lambda s: tuple(sorted(set(s.dropna().astype(str))))),
        candidate_dates=("GAME_DATE", lambda s: tuple(sorted(set(pd.to_datetime(s, errors="coerce").dropna().dt.strftime("%Y-%m-%d"))))),
        candidate_matchups=("MATCHUP", lambda s: tuple(sorted(set(s.dropna().astype(str))))),
    ).reset_index()
    rows = table.merge(summary, on="_row_id", how="left")
    rows["expected_nba_season"] = rows["table_season_id"].map(EXPECTED_SEASONS)
    rows["candidate_season_count"] = rows["candidate_seasons"].map(lambda x: len(x) if isinstance(x, tuple) else 0)
    rows["match_class"] = "no_exact_signature_match"
    rows.loc[rows["candidate_season_count"] > 1, "match_class"] = "ambiguous_multiple_seasons"
    unique = rows["candidate_season_count"].eq(1)
    rows.loc[unique & rows.apply(lambda r: r["candidate_seasons"][0] == r["expected_nba_season"] if r["candidate_season_count"] == 1 else False, axis=1), "match_class"] = "unique_expected_season_match"
    rows.loc[unique & rows.apply(lambda r: r["candidate_seasons"][0] != r["expected_nba_season"] if r["candidate_season_count"] == 1 else False, axis=1), "match_class"] = "unique_cross_season_candidate"

    cross = rows[rows["match_class"].eq("unique_cross_season_candidate")].copy()
    cross["candidate_nba_season"] = cross["candidate_seasons"].map(lambda x: x[0])
    cross["candidate_game_id"] = cross["candidate_games"].map(lambda x: x[0] if len(x) == 1 else "")
    cross["candidate_game_date"] = cross["candidate_dates"].map(lambda x: x[0] if len(x) == 1 else "")
    cross["candidate_matchup"] = cross["candidate_matchups"].map(lambda x: x[0] if len(x) == 1 else "")
    cluster = cross.groupby(["table_season_id", "source_file", "expected_nba_season", "candidate_nba_season", "candidate_game_id", "candidate_game_date", "candidate_matchup"], dropna=False).agg(
        matched_player_rows=("player_name", "size"),
        player_names=("player_name", lambda s: sorted(set(s.astype(str)))),
    ).reset_index().sort_values("matched_player_rows", ascending=False)
    cluster["evidence_level"] = cluster["matched_player_rows"].map(lambda n: "multi_player_game_cluster" if n >= 5 else "isolated_candidate")

    per_season = []
    for sid, expected in EXPECTED_SEASONS.items():
        g = rows[rows["table_season_id"].astype(str).eq(sid)]
        per_season.append({
            "table_season_id": sid,
            "expected_nba_season": expected,
            "files": int(g["source_file"].nunique()),
            "rows": int(len(g)),
            "unique_expected_season_matches": int(g["match_class"].eq("unique_expected_season_match").sum()),
            "unique_cross_season_candidates": int(g["match_class"].eq("unique_cross_season_candidate").sum()),
            "ambiguous_multiple_seasons": int(g["match_class"].eq("ambiguous_multiple_seasons").sum()),
            "no_exact_signature_match": int(g["match_class"].eq("no_exact_signature_match").sum()),
        })
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Exact player name + team + PTS/REB/AST/STL/BLK/TOV/PLUS_MINUS signature (minutes excluded to avoid integer rounding differences) against NBA historical boxscores. A unique different-season match is a candidate; a cluster of >=5 players matching one different-season NBA game is strong evidence of source-scope contamination.",
        "table_files": len(table_paths),
        "table_rows": len(table),
        "nba_log_files": len(nba_paths),
        "match_class_counts": {str(k): int(v) for k, v in rows["match_class"].value_counts().items()},
        "per_season": per_season,
        "cross_season_candidate_rows": int(len(cross)),
        "cross_season_clusters": cluster.to_dict("records"),
        "confirmed_multi_player_clusters": cluster[cluster["matched_player_rows"].ge(5)].to_dict("records"),
        "limitations": [
            "No exact signature match does not prove a bad row: the Dunkest table may have differing precision, missing values, or source corrections.",
            "An isolated cross-season match can be coincidental; only clustered matches to the same NBA game are treated as strong evidence.",
            "This audit does not modify source files, labels, model artifacts, configuration, temporal splits, or backtests.",
        ],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    cross_out = cross[["table_season_id", "source_file", "player_name", "team_code", "pdk", "pts", "min", "plus_minus", "expected_nba_season", "candidate_nba_season", "candidate_game_id", "candidate_game_date", "candidate_matchup"]].copy()
    cross_out.to_csv(OUT_CSV, index=False)

    lines = [
        "# Dunkest weekly-round cross-season integrity audit (v2)", "",
        f"Generated UTC: {report['generated_utc']}", "",
        "## Method", "",
        report["method"], "",
        "## Summary", "",
        f"- Weekly-round `avg` Parquets inspected: **{len(table_paths):,}** ({len(table):,} rows).",
        f"- Unique cross-season candidate rows: **{len(cross):,}**.",
        f"- Multi-player clusters (at least 5 rows matching one NBA game in a different season): **{int(cluster['matched_player_rows'].ge(5).sum())}**.", "",
        "| Table season ID | Expected NBA season | Rows | Exact expected-season matches | Cross-season candidates | Ambiguous seasons | No exact match |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for s in per_season:
        lines.append(f"| {s['table_season_id']} | {s['expected_nba_season']} | {s['rows']:,} | {s['unique_expected_season_matches']:,} | {s['unique_cross_season_candidates']:,} | {s['ambiguous_multiple_seasons']:,} | {s['no_exact_signature_match']:,} |")
    lines += ["", "## Strongest cross-season clusters", "", "| Table season | Source file | Expected season | Matched NBA season | NBA date | Matchup | Player rows | Evidence |", "|---:|---|---|---|---|---|---:|---|"]
    for r in cluster.head(20).to_dict("records"):
        lines.append(f"| {r['table_season_id']} | `{r['source_file']}` | {r['expected_nba_season']} | {r['candidate_nba_season']} | {r['candidate_game_date']} | {r['candidate_matchup']} | {r['matched_player_rows']} | {r['evidence_level']} |")
    lines += ["", "## Interpretation", "",
        "A multi-player match to a single NBA game in a different season is stronger evidence than a lone score coincidence. The report preserves isolated candidates separately and does not automatically remove any row.",
        "No exact match is not proof of corruption because of precision differences, missing values, or source corrections. Review candidate rows in the CSV before any filtering or rebuild.",
        "", "Source Parquets and manifests were read only. No training labels, targets, models, production settings, temporal splits, or backtests were modified.",
        "", f"JSON details: `{OUT_JSON.relative_to(ROOT)}`", f"Candidate CSV: `{OUT_CSV.relative_to(ROOT)}`", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"JSON: {OUT_JSON}")
    print(f"Markdown: {OUT_MD}")
    print(f"CSV: {OUT_CSV}")
    print("Rows", len(table), "cross-season candidates", len(cross), "clusters >=5", int(cluster["matched_player_rows"].ge(5).sum()))
    print("Top clusters:")
    print(cluster.head(15)[["table_season_id", "source_file", "candidate_nba_season", "candidate_game_date", "candidate_matchup", "matched_player_rows"]].to_string(index=False))

if __name__ == "__main__":
    main()
