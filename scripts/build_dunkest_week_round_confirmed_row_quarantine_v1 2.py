#!/usr/bin/env python3
"""Build a row-level quarantine register for corroborated cross-season weekly-round records.

This is an audit register only: it never edits raw or processed Parquets.
"""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "audit"
EVIDENCE_IN = OUT / "dunkest_week_round_boxscore_signature_corroboration_v1.csv"
WIDE_PATH = ROOT / "data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet"
CSV_OUT = OUT / "dunkest_week_round_confirmed_contamination_rows_v1.csv"
JSON_OUT = OUT / "dunkest_week_round_confirmed_contamination_rows_v1.json"
MD_OUT = OUT / "dunkest_week_round_confirmed_contamination_rows_v1.md"

def main() -> int:
    for path in (CSV_OUT, JSON_OUT, MD_OUT):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite versioned output: {path}")
    source = pd.read_csv(EVIDENCE_IN)
    wide = pd.read_parquet(WIDE_PATH)
    candidates = source[
        source["cluster_status"].eq("confirmed_multi_player_cluster")
        | (
            source["pdk_matches_at_one_decimal_half_up"].astype(str).str.lower().eq("true")
            & source["official_history_valid_flags"].astype(str).str.lower().eq("true")
        )
    ].copy()
    rows = []
    for _, item in candidates.iterrows():
        match = re.fullmatch(r"season_(\d+)_week_(\d+)_round_(\d+)_avg\.parquet", str(item["source_file_avg"]))
        if not match:
            raise ValueError(f"Unrecognized weekly-round filename: {item['source_file_avg']}")
        season, week, round_ = map(int, match.groups())
        subset = wide[
            wide["source_season_id"].astype(str).eq(str(season))
            & pd.to_numeric(wide["source_week"], errors="coerce").eq(week)
            & pd.to_numeric(wide["source_round"], errors="coerce").eq(round_)
            & wide["player_name"].astype(str).str.casefold().eq(str(item["player_name"]).casefold())
            & wide["team_code"].astype(str).str.upper().eq(str(item["team_code"]).upper())
        ]
        if len(subset) != 1:
            raise ValueError(f"Expected one processed row for {item['player_name']} / {item['source_file_avg']}, found {len(subset)}")
        row = subset.iloc[0]
        is_cluster = str(item["cluster_status"]) == "confirmed_multi_player_cluster"
        rows.append({
            "dunkest_player_id": str(row["id"]), "player_name": str(row["player_name"]),
            "team_code": str(row["team_code"]), "source_season_id": str(season),
            "source_week": week, "source_round": round_,
            "source_file_avg": str(item["source_file_avg"]), "source_file_tot": str(item["source_file_tot"]),
            "nba_game_date": str(item["nba_game_date"]), "nba_game_id": str(item["nba_game_id"]),
            "nba_matchup": str(item["nba_matchup"]),
            "official_history_pdk_values": str(item["official_history_pdk_values"]),
            "official_history_valid_flags": str(item["official_history_valid_flags"]),
            "pdk_matches_at_one_decimal_half_up": str(item["pdk_matches_at_one_decimal_half_up"]),
            "evidence_class": "confirmed_multi_player_cluster" if is_cluster else "isolated_exact_boxscore_and_official_pdk_match",
            "action": "exclude_exact_player_season_week_round_row_from_downstream_derivatives",
            "raw_source_mutated": False,
        })
    result_df = pd.DataFrame(rows).sort_values(
        ["source_season_id", "source_week", "source_round", "dunkest_player_id"],
        key=lambda s: pd.to_numeric(s, errors="coerce") if s.name in {"source_season_id", "source_week", "source_round", "dunkest_player_id"} else s,
    )
    if result_df.duplicated(["source_season_id", "source_week", "source_round", "dunkest_player_id"]).any():
        raise ValueError("Duplicate row-level quarantine key found")
    result_df.to_csv(CSV_OUT, index=False)
    cluster_n = int(result_df["evidence_class"].eq("confirmed_multi_player_cluster").sum())
    isolated_n = int(result_df["evidence_class"].eq("isolated_exact_boxscore_and_official_pdk_match").sum())
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_corroboration_csv": str(EVIDENCE_IN.relative_to(ROOT)),
        "source_processed_table": str(WIDE_PATH.relative_to(ROOT)),
        "rows": len(result_df), "confirmed_cluster_rows": cluster_n,
        "isolated_exact_signature_plus_official_pdk_rows": isolated_n,
        "by_season_id": {str(k): int(v) for k, v in result_df.groupby("source_season_id").size().items()},
        "records": result_df.to_dict("records"),
        "policy": [
            "Require an exact 15-field boxscore signature from a different NBA season and either membership in the confirmed multi-player cluster or a valid official-history PDK match at one-decimal precision.",
            "Do not quarantine isolated exact signatures when official PDK evidence disagrees or is invalid.",
            "Use exact season/week/round/player ID keys; do not remove all rows for a player.",
            "Raw source files and processed Parquet files are not edited by this register.",
        ],
        "sha256": {
            str(EVIDENCE_IN.relative_to(ROOT)): hashlib.sha256(EVIDENCE_IN.read_bytes()).hexdigest(),
            str(WIDE_PATH.relative_to(ROOT)): hashlib.sha256(WIDE_PATH.read_bytes()).hexdigest(),
        },
    }
    JSON_OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Confirmed row-level weekly-round contamination register — V1", "",
        f"Generated UTC: {result['generated_at_utc']}", "",
        f"- Total exact rows registered: **{len(result_df)}**",
        f"- Rows in confirmed multi-player cluster: **{cluster_n}**",
        f"- Isolated exact boxscore + official PDK matches: **{isolated_n}**", "",
        "## Registered rows by season ID", "",
        "| Season ID | Rows |", "|---:|---:|",
    ]
    for season, count in result["by_season_id"].items():
        lines.append(f"| {season} | {count} |")
    lines += ["", "## Policy", "", *[f"- {x}" for x in result["policy"]],
              "", "## Files", "", f"- CSV: {CSV_OUT.relative_to(ROOT)}",
              f"- JSON: {JSON_OUT.relative_to(ROOT)}", "",
              "## Reproducibility", "",
              "    PYTHONPATH=src ./.venv/bin/python scripts/build_dunkest_week_round_confirmed_row_quarantine_v1.py", ""]
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"csv": str(CSV_OUT.relative_to(ROOT)), "report": str(MD_OUT.relative_to(ROOT)),
        "rows": len(result_df), "confirmed_cluster": cluster_n, "isolated_exact_plus_official_pdk": isolated_n,
        "by_season": result["by_season_id"]}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
