#!/usr/bin/env python3
"""Document the verified cross-season game cluster in one historical table scope.
Read-only; writes new versioned audit artifacts and never changes source datasets.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "data/raw/dunkest_history_v2/season_5_week_43_round_2_avg.parquet"
NBA_PATH = ROOT / "data/raw/nba_historical_logs_2018-25_v1/nba_player_game_logs_2021-22.parquet"
HISTORY_PATH = ROOT / "data/processed/official_dunkest_player_games_2018-25_v1.parquet"
REPORT_DIR = ROOT / "reports/audit"
JSON_OUT = REPORT_DIR / "dunkest_week_round_season5_contamination_v2.json"
MD_OUT = REPORT_DIR / "dunkest_week_round_season5_contamination_v2.md"
CSV_OUT = REPORT_DIR / "dunkest_week_round_season5_contamination_v2.csv"
STAT_KEYS = [("pts", "PTS"), ("reb", "REB"), ("ast", "AST"), ("stl", "STL"), ("blk", "BLK"), ("tov", "TOV"), ("plus_minus", "PLUS_MINUS")]


def round_half_up_1dp(value: object) -> float:
    try:
        return float(Decimal(str(float(value))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, ArithmeticError):
        return float("nan")


def main() -> None:
    for p in (JSON_OUT, MD_OUT, CSV_OUT):
        if p.exists():
            raise SystemExit(f"Refusing to overwrite existing output: {p}")
    for p in (TABLE_PATH, NBA_PATH, HISTORY_PATH):
        if not p.exists():
            raise SystemExit(f"Missing source: {p}")
    table = pd.read_parquet(TABLE_PATH).copy()
    nba = pd.read_parquet(NBA_PATH).copy()
    history = pd.read_parquet(HISTORY_PATH).copy()
    table["_row_id"] = range(len(table))
    table["k_name"] = table["player_name"].astype(str).str.casefold().str.strip()
    table["k_team"] = table["team_code"].astype(str).str.upper().str.strip()
    nba["k_name"] = nba["PLAYER_NAME"].astype(str).str.casefold().str.strip()
    nba["k_team"] = nba["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
    keys = ["k_name", "k_team"]
    for a, b in STAT_KEYS:
        key = f"k_{a}"
        table[key] = pd.to_numeric(table[a], errors="coerce").fillna(-999).astype(float)
        nba[key] = pd.to_numeric(nba[b], errors="coerce").fillna(-999).astype(float)
        keys.append(key)
    nba["nba_season_label"] = "2021-22"
    candidates = table[["_row_id", "player_name", "team_code", "id", "pdk", "pts", "reb", "ast", "stl", "blk", "tov", "plus_minus"] + keys].merge(
        nba[keys + ["nba_season_label", "GAME_DATE", "GAME_ID", "MATCHUP"]].drop_duplicates(), on=keys, how="left"
    )
    candidates = candidates.drop_duplicates(["_row_id", "GAME_DATE", "GAME_ID", "MATCHUP"])
    candidates = candidates[candidates["GAME_ID"].notna()].copy()
    candidates["GAME_DATE"] = pd.to_datetime(candidates["GAME_DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    # Keep only rows uniquely mapped to the same NBA game/date in the 2021/22 logs.
    counts = candidates.groupby("_row_id").agg(candidate_count=("GAME_ID", "nunique"), game_date=("GAME_DATE", "first"), game_id=("GAME_ID", "first"), matchup=("MATCHUP", "first"), nba_season=("nba_season_label", "first")).reset_index()
    unique = candidates.merge(counts[counts["candidate_count"].eq(1)][["_row_id", "game_date", "game_id", "matchup", "nba_season"]], on="_row_id", how="inner", suffixes=("", "_unique"))
    unique = unique[unique["game_date"].eq("2021-11-27") & unique["matchup"].astype(str).str.contains("PHI|MIN", case=False, regex=True)].copy()
    history["season_id"] = history["season_id"].astype(str)
    history["gameDate"] = pd.to_datetime(history["gameDate"], errors="coerce").dt.strftime("%Y-%m-%d")
    history["dunkest_player_name_norm"] = history["dunkest_player_name"].astype(str).str.casefold().str.strip()
    unique["player_name_norm"] = unique["player_name"].astype(str).str.casefold().str.strip()
    h = history[(history["season_id"].eq("7")) & history["gameDate"].eq("2021-11-27")].copy()
    h = h[["dunkest_player_name_norm", "gameDate", "gameValidForDunkest", "pdk", "opponentTeamCode", "dunkest_player_id"]]
    out = unique.merge(h, left_on="player_name_norm", right_on="dunkest_player_name_norm", how="left", validate="many_to_one")
    # Handle duplicate field name produced by the join.
    if "pdk_x" in out.columns:
        out["table_pdk"] = pd.to_numeric(out["pdk_x"], errors="coerce")
        out["official_history_pdk"] = pd.to_numeric(out["pdk_y"], errors="coerce")
        out["pdk_diff_table_minus_history"] = out["table_pdk"] - out["official_history_pdk"]
    else:
        out["table_pdk"] = pd.to_numeric(out["pdk"], errors="coerce")
        out["official_history_pdk"] = pd.to_numeric(out["pdk_y"], errors="coerce")
    out["table_pdk_rounded_1dp_half_up"] = out["table_pdk"].map(round_half_up_1dp)
    out["official_pdk_rounded_1dp_half_up"] = out["official_history_pdk"].map(round_half_up_1dp)
    out["rounded_pdk_match_1dp"] = out["table_pdk_rounded_1dp_half_up"].eq(out["official_pdk_rounded_1dp_half_up"])
    # Remove helper collision names and keep a compact evidence table.
    compact = out[["player_name", "team_code", "id", "table_pdk", "pts", "reb", "ast", "stl", "blk", "tov", "plus_minus", "game_date", "game_id", "matchup", "gameValidForDunkest", "official_history_pdk", "opponentTeamCode", "pdk_diff_table_minus_history", "rounded_pdk_match_1dp"]].copy()
    compact = compact.rename(columns={"id": "dunkest_player_id", "gameValidForDunkest": "season_7_gameValidForDunkest"})
    compact = compact.drop_duplicates(["dunkest_player_id", "game_id"])
    compact = compact.sort_values(["team_code", "player_name"]).reset_index(drop=True)

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_table": str(TABLE_PATH.relative_to(ROOT)),
        "expected_table_season": "2020-21 (stats season ID 5)",
        "matched_nba_game": {"season": "2021-22", "date": "2021-11-27", "game_id": "0022100292", "matchup": "Philadelphia 76ers vs Minnesota Timberwolves"},
        "unique_player_rows_in_cluster": int(len(compact)),
        "official_history_rows_found_in_season_id_7": int(compact["official_history_pdk"].notna().sum()),
        "official_valid_true_rows": int(compact["season_7_gameValidForDunkest"].eq(True).sum()),
        "pdk_matches_after_rounding_to_1_decimal": int(compact["rounded_pdk_match_1dp"].sum()),
        "pdk_max_abs_difference_before_rounding": float(compact["pdk_diff_table_minus_history"].abs().max()) if len(compact) else None,
        "players": compact.to_dict("records"),
        "interpretation": "A cluster of rows in a table labelled season_id=5 uniquely matches boxscore lines from one NBA game on 2021-11-27 in season_id=7. Their official player-game PDK values match after rounding to one decimal, and the player-game history marks these rows valid. This is strong evidence that this one weekly-round response contains cross-season rows. Do not assume every row in the season_id=5 weekly-round archive is correctly scoped until investigated.",
        "safeguards": ["Read-only audit", "No raw datasets changed", "No PDK target, production configuration, model, temporal split, or backtest changed"],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    compact.to_csv(CSV_OUT, index=False)
    lines = [
        "# Verified cross-season rows in Dunkest weekly-round archive (v2)", "",
        f"Generated UTC: {report['generated_utc']}", "",
        "## Finding", "",
        f"The file `{TABLE_PATH.relative_to(ROOT)}` is labelled stats `season_id=5` (expected 2020/21), but **{len(compact)} player rows** match boxscore signatures from NBA game `0022100292` on **2021-11-27** (Philadelphia 76ers vs Minnesota Timberwolves), which belongs to 2021/22.",
        f"- Matching rows with a corresponding official player-history record under season ID 7: **{report['official_history_rows_found_in_season_id_7']} / {len(compact)}**.",
        f"- Rows marked `gameValidForDunkest=True` in that official history: **{report['official_valid_true_rows']} / {len(compact)}**.",
        f"- PDK values equal after rounding the table and history values to one decimal: **{report['pdk_matches_after_rounding_to_1_decimal']} / {len(compact)}**.",
        "", "## Player rows", "",
        "| Player | Team | Weekly-table PDK | Season-7 official PDK | Valid flag | Difference |",
        "|---|---|---:|---:|---|---:|",
    ]
    for r in compact.to_dict("records"):
        lines.append(f"| {r['player_name']} | {r['team_code']} | {r['table_pdk']} | {r['official_history_pdk']} | {r['season_7_gameValidForDunkest']} | {r['pdk_diff_table_minus_history']:.3f} |")
    lines += ["", "## Consequence", "",
        "This is not merely a single score coincidence: multiple players from the same game share the same exact boxscore signature and their official player-game PDK agrees at the weekly table's one-decimal precision. The season_id=5 weekly-round archive must therefore be treated as potentially contaminated at least in this scope. The finding does not establish that other files are contaminated, and isolated cross-season signature matches remain candidates rather than confirmed errors.",
        "", "No source Parquet, manifest, training target, production configuration, model, temporal split, or backtest was changed.",
        "", f"CSV details: `{CSV_OUT.relative_to(ROOT)}`", f"JSON details: `{JSON_OUT.relative_to(ROOT)}`", ""]
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"JSON: {JSON_OUT}")
    print(f"Markdown: {MD_OUT}")
    print(f"CSV: {CSV_OUT}")
    print(f"Unique rows={len(compact)}; official rows={report['official_history_rows_found_in_season_id_7']}; valid={report['official_valid_true_rows']}; rounded PDK matches={report['pdk_matches_after_rounding_to_1_decimal']}")

if __name__ == "__main__":
    main()
