#!/usr/bin/env python3
"""Inventory historical pre-lock snapshot archives without loading model predictions.

Read-only audit of data/processed. Deliberately excludes the 2025/26 holdout
(season ID 25) and frozen 2026/27 prospective run (ID 26).
"""
from __future__ import annotations
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "reports" / "audit"
HISTORICAL_SEASONS = ("1", "3", "5", "7", "9", "13", "19")
FAMILIES = {
    "fixture_mapping": "dunkest_fixture_mapping_{sid}_*.parquet",
    "player_market": "player_credits_{sid}_gw*.parquet",
    "injury_snapshot": "injuries_{sid}_gw*.parquet",
    "coach_market": "coach_market_{sid}_gw*.parquet",
    "player_week_outcomes": "dunkest_players_{sid}_gw*.parquet",
    "coach_outcomes": "dunkest_coach_results_{sid}_gw*.parquet",
}
LEGACY_FILES = ("dunkest_players_gw1.parquet", "dunkest_players_gw35.parquet", "coaches_gw1.parquet", "coaches_gw35.parquet", "opening_market_gw1.parquet", "injuries.parquet")
def metadata_for(path: Path) -> dict:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if not meta_path.exists():
        return {"meta_exists": False, "fetched_at": "", "source": "", "rows_meta": ""}
    try: data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {"meta_exists": True, "fetched_at": "INVALID_META", "source": "", "rows_meta": ""}
    return {"meta_exists": True, "fetched_at": data.get("fetched_at", ""), "source": data.get("source", ""), "rows_meta": data.get("rows", "")}
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for sid in HISTORICAL_SEASONS:
        for family, pattern in FAMILIES.items():
            matches = sorted(PROCESSED.glob(pattern.format(sid=sid)))
            if not matches:
                rows.append({"season_id": sid, "family": family, "file": "", "present": False, "meta_exists": False, "fetched_at": "", "source": "", "rows_meta": ""})
            for path in matches:
                rows.append({"season_id": sid, "family": family, "file": path.name, "present": True, **metadata_for(path)})
    for name in LEGACY_FILES:
        path = PROCESSED / name
        if not path.exists():
            rows.append({"season_id": "legacy/unknown", "family": "legacy_candidate", "file": name, "present": False, "meta_exists": False, "fetched_at": "", "source": "", "rows_meta": ""})
        else:
            rows.append({"season_id": "legacy/unknown", "family": "legacy_candidate", "file": name, "present": True, **metadata_for(path)})
    csv_path = OUT / "dunkest_prelock_archive_inventory_20261013_v1.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["season_id", "family", "file", "present", "meta_exists", "fetched_at", "source", "rows_meta"])
        writer.writeheader(); writer.writerows(rows)
    historical = [row for row in rows if row["season_id"] in HISTORICAL_SEASONS]
    family_lines = []
    for family in FAMILIES:
        family_rows = [row for row in historical if row["family"] == family]
        present = [row for row in family_rows if row["present"]]
        family_lines.append(f"| {family} | {len(present)} | {len(family_rows) - len(present)} |")
    legacy_lines = [f"| {r['file']} | {'yes' if r['present'] else 'no'} | {r['fetched_at'] or 'unknown'} | {r['source'] or 'unknown'} |" for r in rows if r["family"] == "legacy_candidate"]
    report = ["# Historical pre-lock archive inventory (read-only)", "", "Date: 2026-10-13", "", "## Scope and exclusions", "", "This audit inventories filenames and sidecar metadata under data/processed; it does not read prediction outputs, score models, alter labels, or modify production code.", "It deliberately excludes season ID 25 (2025/26 holdout) and season ID 26 (frozen 2026/27 prospective GW1) from the historical-season scan.", "Season IDs scanned: " + ", ".join(HISTORICAL_SEASONS) + ".", "", "## Season-specific archives found", "", "| Snapshot family | Files present | Season IDs with no matching file |", "|---|---:|---:|", *family_lines, "", "## Legacy/season-ambiguous candidates", "", "| File | Present | Sidecar fetched_at | Sidecar source |", "|---|---|---|---|", *legacy_lines, "", "## Interpretation", "", "A current or historical outcome table is not evidence of a pre-lock market snapshot. Sidecar fetched_at records when this pipeline fetched/wrote a file, not necessarily the source's original publication time or the Dunkest lock cutoff.", "A legacy filename without a season ID, round-linked fixture identity, and cutoff evidence cannot be promoted to a valid historical pre-lock roster/CR/injury/coach archive.", "Missing snapshot files are classified as missing; this report does not infer that a player was unavailable, had zero points, or was not in the market.", "", "## Recommended next step", "", "Treat historical lineup-level backtests as blocked until a round-by-round archive manifest can establish roster universe, player CR/role/team, availability report, coach CR/opponent, fixture identity, and each artifact's availability at the actual prediction cutoff. Do not use post-lock/current data to fill historical gaps.", "", f"Machine-readable inventory: {csv_path.relative_to(ROOT)}.", "", "No model training, hyperparameter tuning, production changes, holdout evaluation, commit, or push was performed.", ""]
    report_path = OUT / "dunkest_prelock_archive_inventory_20261013_v1.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"wrote {report_path.relative_to(ROOT)}")
    print(f"wrote {csv_path.relative_to(ROOT)}")
    print("historical snapshot-family presence:")
    for line in family_lines: print(line)
if __name__ == "__main__": main()
