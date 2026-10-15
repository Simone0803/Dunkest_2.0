#!/usr/bin/env python3
"""Verify cross-season candidate rows against complete NBA boxscore signatures.

Uses existing candidate rows to focus the scan, then checks the corresponding
`tot` table against NBA boxscores using player/team and 15 boxscore fields.
Read-only; all outputs are new versioned audit artifacts.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_CSV = ROOT / "reports/audit/dunkest_week_round_cross_season_integrity_v2.csv"
NBA_DIR = ROOT / "data/raw/nba_historical_logs_2018-25_v1"
HISTORY_PATH = ROOT / "data/processed/official_dunkest_player_games_2018-25_v1.parquet"
DATA_DIR = ROOT / "data/raw/dunkest_history_v2"
REPORT_DIR = ROOT / "reports/audit"
OUT_JSON = REPORT_DIR / "dunkest_week_round_boxscore_signature_corroboration_v1.json"
OUT_MD = REPORT_DIR / "dunkest_week_round_boxscore_signature_corroboration_v1.md"
OUT_CSV = REPORT_DIR / "dunkest_week_round_boxscore_signature_corroboration_v1.csv"
LABEL_TO_ID = {"2018-19":"1", "2019-20":"3", "2020-21":"5", "2021-22":"7", "2022-23":"9", "2023-24":"13", "2024-25":"19"}
STAT_KEYS = [("pts", "PTS"), ("reb", "REB"), ("ast", "AST"), ("stl", "STL"), ("blk", "BLK"), ("tov", "TOV"), ("plus_minus", "PLUS_MINUS"), ("fgm", "FGM"), ("fga", "FGA"), ("tpm", "FG3M"), ("tpa", "FG3A"), ("ftm", "FTM"), ("fta", "FTA"), ("oreb", "OREB"), ("dreb", "DREB")]
CONFIRMED_GAME = "0022100292"
CONFIRMED_DATE = "2021-11-27"


def normalize_game_id(value: object) -> str:
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(10) if s.isdigit() else s


def round_half_up_1dp(value: object) -> float:
    try:
        return float(Decimal(str(float(value))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, ArithmeticError):
        return float("nan")


def main() -> None:
    for path in (OUT_JSON, OUT_MD, OUT_CSV):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing output: {path}")
    if not CANDIDATE_CSV.exists() or not HISTORY_PATH.exists():
        raise SystemExit("Missing candidate scan or official player-history source.")
    candidates = pd.read_csv(CANDIDATE_CSV, dtype={"table_season_id": str, "candidate_game_id": str})
    nba_frames = []
    for path in sorted(NBA_DIR.glob("nba_player_game_logs_*.parquet")):
        df = pd.read_parquet(path).copy()
        df["nba_season_label"] = path.stem.replace("nba_player_game_logs_", "")
        df["game_id_norm"] = df["GAME_ID"].map(normalize_game_id)
        df["name_norm"] = df["PLAYER_NAME"].astype(str).str.casefold().str.strip()
        df["team_norm"] = df["TEAM_ABBREVIATION"].astype(str).str.upper().str.strip()
        nba_frames.append(df)
    nba = pd.concat(nba_frames, ignore_index=True, sort=False)
    history = pd.read_parquet(HISTORY_PATH).copy()
    history["season_id"] = history["season_id"].astype(str)
    history["date_norm"] = pd.to_datetime(history["gameDate"], errors="coerce").dt.strftime("%Y-%m-%d")
    history["name_norm"] = history["dunkest_player_name"].astype(str).str.casefold().str.strip()

    found = []
    seen = set()
    for (source_file, game_id_raw), _ in candidates.groupby(["source_file", "candidate_game_id"], dropna=False):
        game_id = normalize_game_id(game_id_raw)
        if not game_id or game_id.lower() == "nan":
            continue
        tot_name = str(source_file).replace("_avg.parquet", "_tot.parquet")
        table_path = DATA_DIR / tot_name
        if not table_path.exists():
            continue
        game = nba[nba["game_id_norm"].eq(game_id)].copy()
        if game.empty:
            continue
        table = pd.read_parquet(table_path).copy()
        table["name_norm"] = table["player_name"].astype(str).str.casefold().str.strip()
        table["team_norm"] = table["team_code"].astype(str).str.upper().str.strip()
        table = table[pd.to_numeric(table["gp"], errors="coerce").eq(1)]
        for _, tr in table.iterrows():
            player_rows = game[(game["name_norm"].eq(tr["name_norm"])) & (game["team_norm"].eq(tr["team_norm"]))]
            for _, nr in player_rows.iterrows():
                differences = []
                for table_col, nba_col in STAT_KEYS:
                    tv = pd.to_numeric(pd.Series([tr.get(table_col)]), errors="coerce").iloc[0]
                    nv = pd.to_numeric(pd.Series([nr.get(nba_col)]), errors="coerce").iloc[0]
                    if pd.isna(tv) or pd.isna(nv) or float(tv) != float(nv):
                        differences.append((table_col, None if pd.isna(tv) else float(tv), nba_col, None if pd.isna(nv) else float(nv)))
                if differences:
                    continue
                key = (tot_name, game_id, str(tr["id"]), str(nr["GAME_DATE"]))
                if key in seen:
                    continue
                seen.add(key)
                date = pd.to_datetime(nr["GAME_DATE"], errors="coerce").strftime("%Y-%m-%d")
                sid = LABEL_TO_ID.get(str(nr["nba_season_label"]))
                z = history[(history["season_id"].eq(sid)) & history["date_norm"].eq(date) & history["name_norm"].eq(str(tr["player_name"]).casefold().strip())] if sid else history.iloc[0:0]
                hist_pdk = pd.to_numeric(z["pdk"], errors="coerce").dropna().tolist()
                pdk_match = any(round_half_up_1dp(tr["pdk"]) == round_half_up_1dp(x) for x in hist_pdk)
                found.append({
                    "source_file_avg": str(source_file),
                    "source_file_tot": tot_name,
                    "table_season_id": str(source_file.split("_")[1]),
                    "expected_season": LABEL_TO_ID and {v:k for k,v in LABEL_TO_ID.items()}.get(str(source_file.split("_")[1]), ""),
                    "actual_nba_season": str(nr["nba_season_label"]),
                    "nba_game_date": date,
                    "nba_game_id": game_id,
                    "nba_matchup": str(nr["MATCHUP"]),
                    "player_name": str(tr["player_name"]),
                    "team_code": str(tr["team_code"]),
                    "table_pdk": float(tr["pdk"]),
                    "table_gp": int(tr["gp"]),
                    "official_history_rows_same_date": int(len(z)),
                    "official_history_pdk_values": ";".join(map(str, hist_pdk)),
                    "official_history_valid_flags": ";".join(sorted(set(z["gameValidForDunkest"].astype(str)))),
                    "pdk_matches_at_one_decimal_half_up": bool(pdk_match),
                    "cluster_status": "confirmed_multi_player_cluster" if game_id == CONFIRMED_GAME and date == CONFIRMED_DATE and str(source_file).endswith("season_5_week_43_round_2_avg.parquet") else "isolated_exact_boxscore_signature_candidate",
                })

    result = pd.DataFrame(found)
    if not result.empty:
        result = result.sort_values(["source_file_avg", "nba_game_id", "team_code", "player_name"]).reset_index(drop=True)
    cluster_counts = result.groupby(["source_file_avg", "nba_game_id", "nba_game_date", "nba_matchup"], dropna=False).size().rename("exact_players").reset_index().sort_values("exact_players", ascending=False) if not result.empty else pd.DataFrame()
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_rows_considered": int(len(candidates)),
        "exact_full_boxscore_signature_rows": int(len(result)),
        "confirmed_multi_player_cluster_rows": int(result["cluster_status"].eq("confirmed_multi_player_cluster").sum()) if not result.empty else 0,
        "isolated_exact_boxscore_signature_candidates": int(result["cluster_status"].eq("isolated_exact_boxscore_signature_candidate").sum()) if not result.empty else 0,
        "isolated_pdk_matches_at_one_decimal": int((result["cluster_status"].eq("isolated_exact_boxscore_signature_candidate") & result["pdk_matches_at_one_decimal_half_up"]).sum()) if not result.empty else 0,
        "clusters": cluster_counts.to_dict("records") if not cluster_counts.empty else [],
        "rows": result.to_dict("records") if not result.empty else [],
        "method": "Starting from 45 isolated cross-season candidates, compare the matching `tot` row against the candidate NBA game using player/team and 15 boxscore fields. Only gp=1 rows with exact field equality are included. The result identifies 15 rows from one confirmed game cluster and isolated exact-signature candidates; isolated rows are not automatically quarantined.",
        "safeguards": ["Source Parquets were read only", "No row was removed or relabelled", "No target, model, config, split, or backtest changed"],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    result.to_csv(OUT_CSV, index=False)
    lines = [
        "# Weekly-round exact boxscore signature corroboration (v1)", "",
        f"Generated UTC: {report['generated_utc']}", "",
        "## Results", "",
        f"Cross-season candidates considered: **{len(candidates)}**.",
        f"Rows matching an NBA game on the full 15-field boxscore signature: **{len(result)}**.",
        f"Rows in the confirmed PHI–MIN multi-player cluster: **{report['confirmed_multi_player_cluster_rows']}**.",
        f"Isolated exact-signature candidates: **{report['isolated_exact_boxscore_signature_candidates']}**; of these, **{report['isolated_pdk_matches_at_one_decimal']}** also match official-history PDK at one-decimal precision.", "",
        "## Clusters and isolated candidates", "",
        "| Source file | NBA game date | Matchup | NBA game ID | Exact players | Players | PDK agrees with official history at 1dp |",
        "|---|---|---|---|---:|---|---|",
    ]
    for _, g in result.groupby(["source_file_avg", "nba_game_id", "nba_game_date", "nba_matchup"], dropna=False):
        names = ", ".join(sorted(g.player_name.astype(str).unique()))
        pdk_agree = int(g.pdk_matches_at_one_decimal_half_up.sum())
        first = g.iloc[0]
        lines.append(f"| `{first['source_file_avg']}` | {first['nba_game_date']} | {first['nba_matchup']} | {first['nba_game_id']} | {g.player_name.nunique()} | {names} | {pdk_agree}/{len(g)} |")
    lines += ["", "## Interpretation", "", report["method"], "", "A row can match a boxscore signature from another season even when its PDK differs from the official player-history feed; that discrepancy remains unresolved and must not be repaired by substituting a proxy. Isolated matches should be reviewed rather than automatically excluded.", "", "No source data, training target, production configuration, model, temporal split or backtest was modified.", "", f"CSV: `{OUT_CSV.relative_to(ROOT)}`", f"JSON: `{OUT_JSON.relative_to(ROOT)}`", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("JSON:", OUT_JSON)
    print("Markdown:", OUT_MD)
    print("CSV:", OUT_CSV)
    print("Exact rows", len(result), "cluster rows", report["confirmed_multi_player_cluster_rows"], "isolated", report["isolated_exact_boxscore_signature_candidates"], "isolated PDK matches", report["isolated_pdk_matches_at_one_decimal"])
    if not result.empty:
        print(result.groupby(["source_file_avg", "nba_game_id", "nba_game_date", "nba_matchup"]).agg(players=("player_name", lambda s: ', '.join(sorted(set(s)))), n=("player_name", "nunique"), pdk_matches=("pdk_matches_at_one_decimal_half_up", "sum")).sort_values("n", ascending=False).to_string())

if __name__ == "__main__":
    main()
