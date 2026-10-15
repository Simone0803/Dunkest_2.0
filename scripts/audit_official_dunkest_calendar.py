#!/usr/bin/env python3
"""Fetch and audit the official active Dunkest matchday without changing production data."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from dunkest.config import Settings
from dunkest.data.dunkest.fixtures import (
    build_gameweek_mapping_from_official_calendar,
    fetch_official_dunkest_gameweek_calendar,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gameweek", type=int, default=1)
    parser.add_argument("--schedule", type=Path, help="Existing NBA schedule parquet; no live NBA fetch is performed.")
    parser.add_argument("--output-stem", type=Path, help="Unique output stem under reports/audit; existing files are never overwritten.")
    args = parser.parse_args()
    settings = Settings()
    schedule_path = args.schedule or settings.data_path / "processed" / f"future_regular_schedule_{settings.season}_v2.parquet"
    if not schedule_path.is_file():
        schedule_path = settings.data_path / "processed" / f"future_regular_schedule_{settings.season}.parquet"
    if not schedule_path.is_file():
        raise FileNotFoundError(f"No existing NBA schedule cache found: {schedule_path}; refusing to fetch or write production cache.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = args.output_stem or Path("reports/audit") / f"dunkest_official_calendar_bridge_gw{args.gameweek}_{stamp}"
    stem.parent.mkdir(parents=True, exist_ok=True)
    targets = [stem.with_suffix(".md"), stem.with_suffix(".json"), stem.with_name(stem.name + "_rows.csv")]
    if any(path.exists() for path in targets):
        raise FileExistsError("Audit output already exists; choose a new --output-stem to preserve immutability.")

    official, metadata = fetch_official_dunkest_gameweek_calendar(args.gameweek)
    schedule = pd.read_parquet(schedule_path)
    mapping = build_gameweek_mapping_from_official_calendar(
        settings, schedule, official, gameweek=args.gameweek
    )
    csv_path = targets[2]
    mapping.to_csv(csv_path, index=False)
    summary = {
        **metadata,
        "nba_schedule_source": str(schedule_path),
        "nba_schedule_rows": int(len(schedule)),
        "mapped_rows": int(len(mapping)),
        "mapped_nba_game_ids": int(mapping["nba_game_id"].nunique()),
        "turn_counts": {str(int(k)): int(v) for k, v in mapping.groupby("dunkest_turn").size().items()},
        "eligible_sides": int(mapping["home_team_eligible"].eq(True).sum() + mapping["away_team_eligible"].eq(True).sum()),
        "unknown_sides": int(mapping["home_team_eligible"].isna().sum() + mapping["away_team_eligible"].isna().sum()),
        "mapping_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "audit_only": True,
        "production_mapping_written": False,
        "frozen_market_artifacts_touched": False,
    }
    targets[1].write_text(json.dumps(summary, indent=2, default=str) + "\n")
    targets[0].write_text(
        f"# Official Dunkest API calendar bridge audit — GW{args.gameweek}\n\n"
        f"- Official API endpoint: `{metadata['matchday_url']}`\n"
        f"- Schedule ID / matchday ID: `{metadata['schedule_id']}` / `{metadata['matchday_id']}`\n"
        f"- Official matches: **{len(official)}**\n"
        f"- Unique NBA GAME_ID links: **{mapping['nba_game_id'].nunique()} / {len(official)}**\n"
        f"- Turns: `{summary['turn_counts']}`\n"
        f"- Eligible team sides: **{summary['eligible_sides']}**; unknown sides: **{summary['unknown_sides']}**\n"
        f"- Raw payload SHA-256: `{metadata['raw_payload_sha256']}`\n"
        f"- Mapping CSV SHA-256: `{summary['mapping_sha256']}`\n\n"
        "The official API supplies Giornata, Turno and per-team `is_valid`. The NBA schedule supplies only NBA GAME_ID identity.\n\n"
        "This is an audit-only artifact. No production mapping, market snapshot, model, target or prediction was written.\n"
    )
    print(json.dumps(summary, indent=2, default=str))
    print("Wrote audit-only artifacts:", *map(str, targets), sep="\n- ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
