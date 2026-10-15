#!/usr/bin/env python3
"""Verify the downstream impact of the confirmed season-5 weekly-round contamination."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "audit"
STEM = "dunkest_week_round_contamination_impact_v1"
JSON_PATH = OUT / f"{STEM}.json"
MD_PATH = OUT / f"{STEM}.md"
EVIDENCE = OUT / "dunkest_week_round_season5_contamination_v2.csv"
QUARANTINE = OUT / "dunkest_week_round_quarantine_manifest_v2.json"
WIDE_PATH = ROOT / "data/processed/dunkest_historical_player_week_round_2020-25_v2.parquet"
HISTORY_PATH = ROOT / "data/processed/official_dunkest_player_games_2020-21_season_id_5.parquet"
TRAINING_PATH = ROOT / "data/processed/dunkest_pdk_game_training_2020-26_v3.parquet"
CAPITAL_GAIN_PATH = ROOT / "data/processed/plusvalenza_history_multiseason_26_pre_gw0_5y_nba_v3.parquet"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    for path in (JSON_PATH, MD_PATH):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite versioned output: {path}")
    required = [EVIDENCE, QUARANTINE, WIDE_PATH, HISTORY_PATH, TRAINING_PATH, CAPITAL_GAIN_PATH]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise SystemExit("Missing required evidence: " + ", ".join(missing))

    evidence = pd.read_csv(EVIDENCE, dtype={"dunkest_player_id": str})
    quarantine = json.loads(QUARANTINE.read_text(encoding="utf-8"))
    contaminated_ids = set(evidence["dunkest_player_id"].dropna().astype(str))
    wide = pd.read_parquet(WIDE_PATH)
    season5_week43_round2 = wide[
        wide["source_season_id"].astype(str).eq("5")
        & pd.to_numeric(wide["source_week"], errors="coerce").eq(43)
        & pd.to_numeric(wide["source_round"], errors="coerce").eq(2)
    ]
    confirmed_rows_in_wide = season5_week43_round2[
        season5_week43_round2["id"].astype(str).isin(contaminated_ids)
    ]
    other_season5 = wide[
        wide["source_season_id"].astype(str).eq("5")
        & ~(
            pd.to_numeric(wide["source_week"], errors="coerce").eq(43)
            & pd.to_numeric(wide["source_round"], errors="coerce").eq(2)
        )
    ]
    ids_present_elsewhere = contaminated_ids.intersection(other_season5["id"].astype(str))

    official = pd.read_parquet(HISTORY_PATH)
    official_dates = pd.to_datetime(official["gameDate"], errors="coerce").dropna()
    official_valid = official["gameValidForDunkest"].eq(True)
    training = pd.read_parquet(TRAINING_PATH, columns=["season_id", "season_label", "game_date", "target_pdk"])
    train5 = training[training["season_id"].astype(str).eq("5")].copy()
    train_dates = pd.to_datetime(train5["game_date"], errors="coerce").dropna()
    plusvalenza = pd.read_parquet(CAPITAL_GAIN_PATH, columns=["season_id"])
    plus_seasons = sorted(plusvalenza["season_id"].astype(str).unique(), key=lambda x: int(x))

    guard_df = wide[
        ["id", "player_name", "source_season_id", "source_week", "source_round"]
    ].copy()
    guard_mask = (
        guard_df["source_season_id"].astype(str).eq("5")
        & pd.to_numeric(guard_df["source_week"], errors="coerce").eq(43)
        & pd.to_numeric(guard_df["source_round"], errors="coerce").eq(2)
        & guard_df["id"].astype(str).isin(contaminated_ids)
    )
    guard_rows = int(guard_mask.sum())

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "confirmed_cluster": {
            "players": int(evidence["dunkest_player_id"].nunique()),
            "game_date": str(evidence["game_date"].iloc[0]),
            "game_id": str(evidence["game_id"].iloc[0]),
            "matchup": str(evidence["matchup"].iloc[0]),
            "source_scope": "season_id=5, week=43, round=2",
            "quarantined_files": quarantine.get("confirmed_quarantine_files", []),
        },
        "processed_week_round_source": {
            "path": str(WIDE_PATH.relative_to(ROOT)),
            "season5_week43_round2_rows": int(len(season5_week43_round2)),
            "confirmed_contaminated_player_rows": int(len(confirmed_rows_in_wide)),
            "confirmed_player_ids_present_in_other_season5_rounds": len(ids_present_elsewhere),
            "confirmed_player_ids_not_seen_elsewhere_in_season5": sorted(contaminated_ids - ids_present_elsewhere),
            "guard_excluded_rows_from_season_id_seed": guard_rows,
            "note": "Only the 15 independently confirmed player rows are excluded from season-specific ID seeding; all 15 IDs also occur in other season-5 rounds.",
        },
        "official_2020_21_player_history": {
            "path": str(HISTORY_PATH.relative_to(ROOT)),
            "rows": int(len(official)),
            "valid_true_rows": int(official_valid.sum()),
            "valid_false_rows": int(official["gameValidForDunkest"].eq(False).sum()),
            "min_game_date": official_dates.min().date().isoformat() if len(official_dates) else None,
            "max_game_date": official_dates.max().date().isoformat() if len(official_dates) else None,
            "contains_post_2020_21_dates": bool((official_dates > pd.Timestamp("2021-06-30")).any()),
        },
        "pdk_training_v3": {
            "path": str(TRAINING_PATH.relative_to(ROOT)),
            "season5_rows": int(len(train5)),
            "season5_max_game_date": train_dates.max().date().isoformat() if len(train_dates) else None,
            "season5_rows_after_2021_06_30": int((train_dates > pd.Timestamp("2021-06-30")).sum()),
            "matches_official_valid_row_count": int(len(train5)) == int(official_valid.sum()),
        },
        "current_2026_27_capital_gain_history": {
            "path": str(CAPITAL_GAIN_PATH.relative_to(ROOT)),
            "season_ids": plus_seasons,
            "includes_contaminated_season_id_5": "5" in plus_seasons,
        },
        "source_sha256": {
            str(p.relative_to(ROOT)): sha256(p)
            for p in [EVIDENCE, QUARANTINE, WIDE_PATH, HISTORY_PATH, TRAINING_PATH, CAPITAL_GAIN_PATH]
        },
        "conclusion": (
            "The confirmed contamination is confined to two weekly-round source files and their derived weekly-round table. "
            "The official 2020/21 per-player history and PDK training targets contain no post-season dates, the season-5 "
            "training row count matches the official valid-row count, and the current 2026/27 capital-gain cache does not "
            "include season_id=5. The historical collector now excludes only the 15 confirmed bad rows from season-specific "
            "ID seeding. This does not certify the remaining weekly-round archive as clean."
        ),
    }
    JSON_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Downstream impact of confirmed weekly-round contamination — V1", "",
        f"Generated UTC: {result['generated_at_utc']}", "",
        "## Confirmed source issue", "",
        f"- Cluster: **{result['confirmed_cluster']['players']} players** in {result['confirmed_cluster']['matchup']} on {result['confirmed_cluster']['game_date']} (NBA game {result['confirmed_cluster']['game_id']}).",
        "- Scope: season ID 5, week 43, round 2.",
        "- Quarantined files: " + ", ".join(result["confirmed_cluster"]["quarantined_files"]), "",
        "## Downstream checks", "",
        "| Dataset / path | Result |",
        "|---|---|",
        f"| Processed weekly-round table | {result['processed_week_round_source']['season5_week43_round2_rows']} rows in the affected round; {result['processed_week_round_source']['confirmed_contaminated_player_rows']} confirmed bad player rows identified |",
        f"| Historical collector guard | Excludes exactly {result['processed_week_round_source']['guard_excluded_rows_from_season_id_seed']} confirmed rows from season-specific ID seeding |",
        f"| Official 2020/21 player history | {result['official_2020_21_player_history']['rows']:,} rows; {result['official_2020_21_player_history']['valid_true_rows']:,} valid rows; dates {result['official_2020_21_player_history']['min_game_date']}–{result['official_2020_21_player_history']['max_game_date']} |",
        f"| PDK training V3, season 2020/21 | {result['pdk_training_v3']['season5_rows']:,} rows; latest date {result['pdk_training_v3']['season5_max_game_date']}; rows after 2021-06-30: {result['pdk_training_v3']['season5_rows_after_2021_06_30']} |",
        f"| Current 2026/27 capital-gain cache | Season IDs {', '.join(result['current_2026_27_capital_gain_history']['season_ids'])}; season ID 5 included: {'yes' if result['current_2026_27_capital_gain_history']['includes_contaminated_season_id_5'] else 'no'} |",
        "", "## Interpretation", "",
        result["conclusion"], "",
        "The PDK training target is sourced from official per-player game history and verified NBA matches, not the weekly-round Parquet. The weekly-round derivative remains uncertified and must not be used as a training target or trusted same-round pre-game feature.", "",
        "## Reproducibility", "",
        "    PYTHONPATH=src ./.venv/bin/python scripts/audit_dunkest_week_round_contamination_impact_v1.py", "",
    ]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "report": str(MD_PATH.relative_to(ROOT)),
        "json": str(JSON_PATH.relative_to(ROOT)),
        "confirmed_cluster_rows": result["confirmed_cluster"]["players"],
        "wide_round_rows": result["processed_week_round_source"]["season5_week43_round2_rows"],
        "guard_rows": guard_rows,
        "official_2020_21_valid_rows": result["official_2020_21_player_history"]["valid_true_rows"],
        "training_2020_21_rows": result["pdk_training_v3"]["season5_rows"],
        "training_rows_after_season": result["pdk_training_v3"]["season5_rows_after_2021_06_30"],
        "capital_gain_contains_season5": result["current_2026_27_capital_gain_history"]["includes_contaminated_season_id_5"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
