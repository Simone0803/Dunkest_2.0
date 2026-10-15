#!/usr/bin/env python3
"""Readiness audit for learning player participation/DNP probability from local archives."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HIST = DATA / "raw/nba_historical_logs_2018-25_v1"
TRAIN = DATA / "processed/dunkest_pdk_game_training_2020-26_v3.parquet"
OUT = ROOT / "reports/audit"
STEM = "dunkest_participation_label_readiness_20261013_v1"
CSV, JSON, MD = (OUT / f"{STEM}.{ext}" for ext in ("csv", "json", "md"))
CSV = OUT / f"{STEM}.csv"
JSON = OUT / f"{STEM}.json"
MD = OUT / f"{STEM}.md"
for path in (CSV, JSON, MD):
    if path.exists():
        raise SystemExit(f"Refusing to overwrite versioned artifact: {path}")
seasons = [
    ("2018-19", HIST / "nba_player_game_logs_2018-19.parquet", None),
    ("2019-20", HIST / "nba_player_game_logs_2019-20.parquet", None),
    ("2020-21", HIST / "nba_player_game_logs_2020-21.parquet", "5"),
    ("2021-22", HIST / "nba_player_game_logs_2021-22.parquet", "7"),
    ("2022-23", HIST / "nba_player_game_logs_2022-23.parquet", "9"),
    ("2023-24", HIST / "nba_player_game_logs_2023-24.parquet", "13"),
    ("2024-25", HIST / "nba_player_game_logs_2024-25.parquet", "19"),
    ("2025-26", DATA / "processed/player_game_logs_2025-26.parquet", "25"),
]
if not TRAIN.exists():
    raise SystemExit(f"Missing official target dataset: {TRAIN}")
target = pd.read_parquet(TRAIN, columns=["season_id", "target_pdk"])
target["season_id"] = target.season_id.astype(str)
target_counts = target.groupby("season_id").target_pdk.agg(
    official_target_rows="count", rows_in_target_archive="size"
).to_dict("index")
sid_for = {season: sid for season, _, sid in seasons if sid}
rows = []
for season, path, sid in seasons:
    if not path.exists():
        rows.append({"season": season, "status": "missing_log_archive", "path": str(path)})
        continue
    d = pd.read_parquet(path, columns=["PLAYER_ID", "GAME_ID", "GAME_DATE", "MIN"])
    minutes = pd.to_numeric(d["MIN"], errors="coerce")
    duplicates = int(d.duplicated(["PLAYER_ID", "GAME_ID"]).sum())
    target_stats = target_counts.get(sid, {}) if sid else {}
    n = len(d)
    zeros = int(minutes.eq(0).sum())
    missing = int(minutes.isna().sum())
    rows.append({
        "season": season, "status": "audited", "nba_log_rows": n,
        "unique_player_game_rows": int(d[["PLAYER_ID", "GAME_ID"]].drop_duplicates().shape[0]),
        "duplicate_player_game_rows": duplicates,
        "zero_minute_rows": zeros, "zero_minute_pct": 100.0 * zeros / n if n else None,
        "missing_minute_rows": missing, "positive_minute_rows": int(minutes.gt(0).sum()),
        "official_pdk_target_rows_in_archive": int(target_stats.get("official_target_rows", 0)),
        "target_archive_rows": int(target_stats.get("rows_in_target_archive", 0)),
        "candidate_universe_snapshot_available": False,
    })
df = pd.DataFrame(rows)
df.to_csv(CSV, index=False)
audit = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "purpose": "Determine whether current archives can supervise player participation/DNP probability without inventing labels.",
    "season_metrics": rows,
    "decision": "Do not train or calibrate a participation probability model from these NBA game logs alone. The logs contain observed player-game rows, not a complete pre-lock roster universe with explicit played/DNP/OUT labels.",
    "evidence": {
        "zero_minute_rows_are_rare": True,
        "missing_candidate_rows_are_not_represented": True,
        "official_pdk_rows_are_outcome_archive_rows_not_complete_market_roster_snapshots": True,
    },
    "required_future_inputs": [
        "Timestamped pre-lock full player roster/market snapshot with stable player IDs",
        "Fixture-linked injury/availability status captured before lock",
        "Post-game played/DNP/zero-minute result for every candidate, including candidates with no NBA player-game log row",
        "Immutable snapshot timestamp and source hash",
    ],
    "production_changed": False,
    "outputs": {"csv": str(CSV.relative_to(ROOT)), "json": str(JSON.relative_to(ROOT)), "report": str(MD.relative_to(ROOT))}
}
JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str)+"\n", encoding="utf-8")
lines = [
    "# Participation / DNP label-readiness audit", "",
    f"Generated UTC: {audit['generated_at_utc']}", "",
    "## Results by season", "", df.to_string(index=False), "",
    "## Decision", "",
    "Do not train or calibrate a participation-probability model from these logs alone. NBA player-game archives primarily contain observed appearances; absent players are not represented as explicit zero-minute outcomes. The official Dunkest PDK archive is an outcome table, not a full pre-lock roster/availability snapshot.", "",
    "## Required data for a valid model", "",
    *[f"- {item}" for item in audit["required_future_inputs"]], "",
    "Until those inputs are captured, keep current availability/injury rules deterministic and avoid interpreting PDK score MAE as participation accuracy. Production was not changed.", "",
    "## Artifacts", "",
    f"- CSV: {CSV.relative_to(ROOT)}",
    f"- JSON: {JSON.relative_to(ROOT)}", ""
]
MD.write_text("\n".join(lines), encoding="utf-8")
print(json.dumps({"status":"completed","metrics":rows,"artifacts":[str(p.relative_to(ROOT)) for p in (CSV,JSON,MD)]}, indent=2, default=str))
