#!/usr/bin/env python3
"""Audit which season/gameweeks are genuinely replayable from immutable archives.

This script is read-only. It never generates predictions, mutates caches, or
promotes proxy-derived data into certified outcomes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dunkest.config import Settings
from dunkest.data.dunkest.fixtures import (
    check_backtest_readiness,
    load_post_match_results_archive,
    load_pre_match_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data", help="Root data directory")
    parser.add_argument("--output", default="reports/audit/dunkest_multiseason_archive_readiness_20261015_v1.json")
    args = parser.parse_args()
    data_root = Path(args.data_dir).resolve()
    archive_root = data_root / "archive"
    seasons = sorted(path.name for path in archive_root.iterdir() if path.is_dir()) if archive_root.is_dir() else []
    report = {
        "audit": "multi-season-immutable-archive-readiness",
        "data_root": str(data_root),
        "read_only": True,
        "season_count": len(seasons),
        "seasons": [],
        "certification_rule": (
            "A gameweek is replayable only if check_backtest_readiness passes all required gates, "
            "including hash-verified PRE_MATCH inputs and hash-verified POST_MATCH player and coach outcomes. "
            "No retrospective reconstruction is treated as a pre-lock snapshot."
        ),
    }
    total_ready = 0
    for season_id in seasons:
        season_settings = Settings(data_dir=str(data_root), season_id=season_id)
        season_dir = archive_root / season_id
        gameweeks = sorted(
            int(path.name[2:]) for path in season_dir.glob("gw*")
            if path.is_dir() and path.name[2:].isdigit()
        )
        entries = []
        for gameweek in gameweeks:
            pre = load_pre_match_snapshot(season_settings, gameweek, season_id=season_id)
            post = load_post_match_results_archive(season_settings, gameweek, season_id=season_id)
            readiness = check_backtest_readiness(season_settings, gameweek, season_id=season_id)
            ready = bool(readiness["backtest_ready"] and pre is not None and post is not None)
            total_ready += int(ready)
            failed = [name for name, item in readiness["checks"].items() if not item["pass"]]
            entries.append({
                "gameweek": gameweek,
                "replay_ready": ready,
                "prematch_archive": str(pre["path"].relative_to(data_root)) if pre else None,
                "postmatch_archive": str(post["path"].relative_to(data_root)) if post else None,
                "failed_gates": failed,
                "gate_reasons": {name: item["reason"] for name, item in readiness["checks"].items() if not item["pass"]},
            })
        report["seasons"].append({
            "season_id": season_id,
            "archived_gameweeks": len(entries),
            "replay_ready_gameweeks": sum(entry["replay_ready"] for entry in entries),
            "gameweeks": entries,
        })
    report["total_replay_ready_gameweeks"] = total_ready
    report["multi_season_validation_possible"] = len([s for s in report["seasons"] if s["replay_ready_gameweeks"] > 0]) >= 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "seasons_found": len(seasons),
        "total_replay_ready_gameweeks": total_ready,
        "multi_season_validation_possible": report["multi_season_validation_possible"],
        "per_season": [{
            "season_id": season["season_id"],
            "archived_gameweeks": season["archived_gameweeks"],
            "replay_ready_gameweeks": season["replay_ready_gameweeks"],
        } for season in report["seasons"]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
