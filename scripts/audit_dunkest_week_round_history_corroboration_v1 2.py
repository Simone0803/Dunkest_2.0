#!/usr/bin/env python3
"""Cross-check isolated weekly-round cross-season candidates against official player history.
Read-only; does not remove or relabel source rows.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_CSV = ROOT / "reports/audit/dunkest_week_round_cross_season_integrity_v2.csv"
HISTORY_PATH = ROOT / "data/processed/official_dunkest_player_games_2018-25_v1.parquet"
REPORT_DIR = ROOT / "reports/audit"
OUT_JSON = REPORT_DIR / "dunkest_week_round_history_corroboration_v1.json"
OUT_MD = REPORT_DIR / "dunkest_week_round_history_corroboration_v1.md"
OUT_CSV = REPORT_DIR / "dunkest_week_round_history_corroboration_v1.csv"
SEASON_ID = {"2018-19":"1", "2019-20":"3", "2020-21":"5", "2021-22":"7", "2022-23":"9", "2023-24":"13", "2024-25":"19"}
CONFIRMED_SOURCE = "season_5_week_43_round_2_avg.parquet"
CONFIRMED_GAME = "0022100292"


def half_up_1dp(value: object) -> float:
    try:
        return float(Decimal(str(float(value))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, ArithmeticError):
        return float("nan")


def main() -> None:
    for path in (OUT_JSON, OUT_MD, OUT_CSV):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing output: {path}")
    if not CANDIDATE_CSV.exists() or not HISTORY_PATH.exists():
        raise SystemExit("Missing candidate scan or official history source.")
    candidates = pd.read_csv(CANDIDATE_CSV, dtype={"table_season_id": str, "candidate_game_id": str})
    history = pd.read_parquet(HISTORY_PATH).copy()
    history["season_id"] = history["season_id"].astype(str)
    history["date_norm"] = pd.to_datetime(history["gameDate"], errors="coerce").dt.strftime("%Y-%m-%d")
    history["name_norm"] = history["dunkest_player_name"].astype(str).str.casefold().str.strip()
    records = []
    for _, row in candidates.iterrows():
        season_label = str(row.get("candidate_nba_season", ""))
        history_sid = SEASON_ID.get(season_label)
        date = str(row.get("candidate_game_date", ""))
        if date in {"", "nan", "NaT"}:
            date = ""
        name = str(row.get("player_name", "")).casefold().strip()
        matched = history.iloc[0:0]
        if history_sid and date:
            matched = history[(history["season_id"].eq(history_sid)) & history["date_norm"].eq(date) & history["name_norm"].eq(name)]
        official_pdks = pd.to_numeric(matched["pdk"], errors="coerce").dropna().tolist()
        table_pdk = pd.to_numeric(pd.Series([row.get("pdk")]), errors="coerce").iloc[0]
        pdk_match = any(half_up_1dp(table_pdk) == half_up_1dp(v) for v in official_pdks)
        source_file = str(row.get("source_file", ""))
        game_id = str(row.get("candidate_game_id", ""))
        if game_id.endswith(".0"):
            game_id = game_id[:-2]
        game_id = game_id.zfill(10) if game_id.isdigit() else game_id
        main_cluster = source_file == CONFIRMED_SOURCE and game_id == CONFIRMED_GAME and date == "2021-11-27"
        if main_cluster:
            status = "confirmed_multi_player_cross_season_cluster"
        elif len(matched) and pdk_match:
            status = "corroborated_isolated_cross_season_candidate"
        elif len(matched):
            status = "history_match_but_pdk_differs"
        else:
            status = "no_same_date_official_history_match_or_date_unavailable"
        records.append({
            "source_file_avg": source_file,
            "source_file_tot": source_file.replace("_avg.parquet", "_tot.parquet"),
            "table_season_id": str(row.get("table_season_id", "")),
            "expected_nba_season": str(row.get("expected_nba_season", "")),
            "candidate_nba_season": season_label,
            "candidate_game_date": date,
            "candidate_game_id": game_id,
            "candidate_matchup": str(row.get("candidate_matchup", "")),
            "player_name": str(row.get("player_name", "")),
            "team_code": str(row.get("team_code", "")),
            "table_pdk": None if pd.isna(table_pdk) else float(table_pdk),
            "official_history_season_id": history_sid or "",
            "official_history_rows_same_player_date": int(len(matched)),
            "official_history_pdk_values": ";".join(map(str, official_pdks)),
            "official_history_valid_flags": ";".join(sorted(set(matched["gameValidForDunkest"].astype(str)))),
            "pdk_match_at_one_decimal_half_up": bool(pdk_match),
            "status": status,
        })
    result = pd.DataFrame(records)
    counts = {str(k): int(v) for k, v in result["status"].value_counts().items()}
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_rows_reviewed": int(len(result)),
        "status_counts": counts,
        "corroborated_isolated_candidates": result[result["status"].eq("corroborated_isolated_cross_season_candidate")][["source_file_avg", "player_name", "candidate_nba_season", "candidate_game_date", "candidate_game_id", "table_pdk", "official_history_pdk_values", "official_history_valid_flags"]].to_dict("records"),
        "confirmed_cluster_rows": int(result["status"].eq("confirmed_multi_player_cross_season_cluster").sum()),
        "interpretation": "A same-player/date official-history match plus PDK agreement at one-decimal table precision corroborates a cross-season candidate, but isolated rows are still tracked separately from the confirmed multi-player cluster. PDK mismatches and missing history rows are unresolved, not automatically labelled errors.",
        "safeguards": ["Read-only analysis", "No source rows changed", "No automatic filtering", "No model/config/target/split/backtest changes"],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    result.to_csv(OUT_CSV, index=False)
    lines = [
        "# Weekly-round cross-season candidate corroboration (v1)", "",
        f"Generated UTC: {report['generated_utc']}", "",
        "## Results", "",
        f"Candidate rows checked: **{len(result)}**.",
        f"Confirmed 15-player cluster rows: **{counts.get('confirmed_multi_player_cross_season_cluster', 0)}**.",
        f"Isolated rows with same-date official history and PDK agreement at 1 decimal: **{counts.get('corroborated_isolated_cross_season_candidate', 0)}**.",
        f"Same-date history exists but PDK differs: **{counts.get('history_match_but_pdk_differs', 0)}**.",
        f"No same-date history match or date unavailable: **{counts.get('no_same_date_official_history_match_or_date_unavailable', 0)}**.", "",
        "## Corroborated isolated candidates", "",
        "These rows warrant targeted review but are not grouped into a multi-player cluster, so this report does not automatically quarantine their files.", "",
        "| File | Player | Table season | Candidate season | Date | Table PDK | Official PDK | Valid flag |",
        "|---|---|---:|---|---|---:|---:|---|",
    ]
    for r in report["corroborated_isolated_candidates"]:
        lines.append(f"| `{r['source_file_avg']}` | {r['player_name']} | {r['source_file_avg'].split('_')[1]} | {r['candidate_nba_season']} | {r['candidate_game_date']} | {r['table_pdk']} | {r['official_history_pdk_values']} | {r['official_history_valid_flags']} |")
    lines += ["", "## Interpretation", "", report["interpretation"], "", "Source data was read only. No source Parquet, training target, validity flag, model, production configuration, temporal split or backtest was changed.", "", f"CSV: `{OUT_CSV.relative_to(ROOT)}`", f"JSON: `{OUT_JSON.relative_to(ROOT)}`", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("JSON:", OUT_JSON)
    print("Markdown:", OUT_MD)
    print("CSV:", OUT_CSV)
    print("Status counts:", counts)
    print("Corroborated isolated rows:")
    print(result[result.status.eq("corroborated_isolated_cross_season_candidate")][["source_file_avg", "player_name", "candidate_nba_season", "candidate_game_date", "table_pdk", "official_history_pdk_values"]].to_string(index=False))

if __name__ == "__main__":
    main()
