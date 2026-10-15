#!/usr/bin/env python3
"""Inventory historical Dunkest weekly stats and genuine pre-match market snapshots.

This is an audit only: it does not modify production data or model code.
Versioned outputs are deliberately not overwritten.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "reports" / "audit"
VERSION = "v1"
JSON_PATH = OUT / f"historical_dunkest_market_snapshot_inventory_{VERSION}.json"
MD_PATH = OUT / f"historical_dunkest_market_snapshot_inventory_{VERSION}.md"
PATTERN = re.compile(r"season_(\d+)_week_(\d+)_round_(\d+)_(avg|tot)\.parquet$")


def schema_info(path: Path) -> dict:
    pf = pq.ParquetFile(path)
    columns = pf.schema.names
    return {"rows": pf.metadata.num_rows, "columns": columns}


def main() -> int:
    if JSON_PATH.exists() or MD_PATH.exists():
        raise SystemExit(f"Refusing to overwrite existing versioned output: {JSON_PATH} / {MD_PATH}")
    OUT.mkdir(parents=True, exist_ok=True)

    weekly: dict[str, dict] = {}
    season_week_round: dict[str, set[tuple[int, int]]] = defaultdict(set)
    rows_by_season: Counter[str] = Counter()
    for family in ("dunkest_history", "dunkest_history_v2"):
        folder = DATA / "raw" / family
        files = sorted(folder.glob("season_*_week_*_round_*_*.parquet")) if folder.exists() else []
        matches = []
        total_rows = 0
        for path in files:
            match = PATTERN.fullmatch(path.name)
            if not match:
                continue
            season, week, rnd, stat_type = match.groups()
            info = schema_info(path)
            total_rows += info["rows"]
            matches.append({"path": str(path.relative_to(ROOT)), "season_id": season,
                            "week": int(week), "round": int(rnd), "stats_type": stat_type,
                            "rows": info["rows"], "columns": len(info["columns"])})
            season_week_round[season].add((int(week), int(rnd)))
            rows_by_season[season] += info["rows"]
        per_season = {}
        for sid in sorted({m["season_id"] for m in matches}, key=int):
            items = [m for m in matches if m["season_id"] == sid]
            wk = [m["week"] for m in items]
            rounds = sorted({m["round"] for m in items})
            pairs = {(m["week"], m["round"]) for m in items}
            per_season[sid] = {"files": len(items), "distinct_week_rounds": len(pairs),
                               "week_min": min(wk), "week_max": max(wk), "rounds_seen": rounds,
                               "avg_files": sum(m["stats_type"] == "avg" for m in items),
                               "tot_files": sum(m["stats_type"] == "tot" for m in items),
                               "rows": sum(m["rows"] for m in items)}
        weekly[family] = {"files": len(matches), "rows_across_files": total_rows,
                          "season_ids": per_season, "examples": matches[:2]}

    # Archived prediction runs contain genuinely pre-match captures, but so far
    # they are contemporary captures rather than a multi-season historical archive.
    pred_root = DATA / "predictions"
    runs = []
    for snapshot_dir in sorted(pred_root.glob("*/pre_match_snapshot")):
        run_dir = snapshot_dir.parent
        manifest_path = run_dir / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        files = []
        for p in sorted(snapshot_dir.iterdir()):
            if p.is_file():
                item = {"name": p.name, "bytes": p.stat().st_size}
                if p.suffix == ".parquet":
                    try:
                        info = schema_info(p)
                        item.update(rows=info["rows"], columns=info["columns"])
                    except Exception as exc:
                        item["schema_error"] = str(exc)
                files.append(item)
        runs.append({"run_id": run_dir.name, "manifest": manifest, "files": files})

    # Explicitly distinguish archived market inputs from historical outcome tables.
    historical_tables = []
    for p in sorted((DATA / "processed").glob("*")):
        if not p.is_file() or p.suffix != ".parquet":
            continue
        low = p.name.lower()
        if any(token in low for token in ("plusvalenza_history", "dunkest_historical_player_week_round", "dunkest_historical_stats", "daily_historical_pdk")):
            info = schema_info(p)
            historical_tables.append({"path": str(p.relative_to(ROOT)), "rows": info["rows"],
                                      "columns": info["columns"]})

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Determine whether local historical data contains point-in-time pre-game Dunkest market snapshots suitable for leakage-safe roster-adjustment backtests.",
        "weekly_round_archives": weekly,
        "distinct_season_ids_in_weekly_archives": sorted(season_week_round, key=int),
        "historical_processed_tables": historical_tables,
        "archived_pre_match_snapshot_runs": len(runs),
        "pre_match_runs": runs,
        "interpretation": {
            "weekly_round_tables": "Contain player credits (cr) and fantasy results (pdk) together, but do not contain a capture timestamp or explicit as-of/pre-game marker. Treat same-round cr as unsafe for pre-game features until source semantics are independently verified; using the prior completed round is safer but is only a lagged proxy.",
            "pre_match_snapshots": "Contain explicit current-market captures (player credits, coach market, injuries, lineup availability, fixture mapping) under prediction run directories. These are point-in-time snapshots for the 2026/27 opener period, not historical captures spanning prior seasons.",
            "missing_historical_features": "No confirmed multi-season timestamped pre-game injury, availability, coach-market, or player-credit snapshots were found in the inventory. Weekly results can support lagged form features, not reconstruct exact pre-game roster state on their own."
        }
    }
    JSON_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Historical Dunkest market/snapshot inventory — V1", "",
        f"Generated (UTC): {result['generated_at_utc']}", "",
        "## Conclusion", "",
        "The repository contains extensive historical Dunkest player-week/round statistics, including both `cr` and `pdk`, but those tables do not carry a capture timestamp or a verified pre-game as-of marker. They must not be treated as exact pre-game market snapshots without additional source validation.", "",
        "The `data/predictions/*/pre_match_snapshot/` directories are the only clearly point-in-time bundles found. They contain credits, coaches, injuries, availability and fixture mappings, but cover the current 2026/27 opener capture period rather than earlier seasons. Therefore the current roster adjustment cannot yet be validated historically against the exact market/availability state available before each past game.", "",
        "## Historical weekly-round archives", "",
        "| Folder | Files | Rows summed across files | Season IDs |", "|---|---:|---:|---|"
    ]
    for family, info in weekly.items():
        season_bits = "; ".join(f"{sid}: {v['files']} files, weeks {v['week_min']}–{v['week_max']} ({v['distinct_week_rounds']} week/rounds)" for sid, v in info["season_ids"].items())
        lines.append(f"| `{family}` | {info['files']} | {info['rows_across_files']:,} | {season_bits} |")
    lines += ["", "The `avg` and `tot` files are alternative representations of the same weekly-round result table, not independent pre-game snapshots.", "",
              "## Processed historical tables inspected", "",
              "| Dataset | Rows | Key fields relevant to this audit |", "|---|---:|---|"]
    for item in historical_tables:
        cols = item["columns"]
        relevant = [c for c in cols if c.lower() in {"cr", "pdk", "plus", "min", "starter", "gameweek", "season_id", "source_week", "source_round", "game_date", "api_date", "timestamp", "date"}]
        lines.append(f"| `{Path(item['path']).name}` | {item['rows']:,} | {', '.join(relevant) or 'no explicit temporal/market fields'} |")
    lines += ["", "## Archived point-in-time snapshot bundles", "", f"Found **{len(runs)}** run-level `pre_match_snapshot` bundles.", ""]
    if runs:
        lines += ["| Run ID | Files captured |", "|---|---|"]
        for run in runs:
            names = ", ".join(f"{f['name']} ({f.get('rows', '?')} rows)" for f in run["files"])
            lines.append(f"| `{run['run_id']}` | {names} |")
    lines += ["", "## Consequences for model validation", "",
              "1. Keep the current production roster adjustment unchanged; the previous PDK aggregate proxy failed to improve walk-forward probability metrics.",
              "2. Use official historical PDK and NBA logs for leakage-safe player-form/score validation; use prior-round `cr` only as a lagged price proxy if needed.",
              "3. Do not claim historical injury/coach/availability validation from current snapshots: the exact historical states are not archived here.",
              "4. Begin prospective immutable snapshot capture every run, retaining retrieval timestamps, raw payload hashes, fixture IDs and the precise pre-game cutoff. This will create a defensible 2026/27+ evaluation set.", "",
              "## Reproducibility", "", "```bash", "PYTHONPATH=\"$PWD/src\" ./.venv/bin/python scripts/audit_historical_dunkest_market_snapshots_v1.py", "```", ""]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(JSON_PATH.relative_to(ROOT)), "markdown": str(MD_PATH.relative_to(ROOT)),
                      "weekly_archive_files": {k: v["files"] for k, v in weekly.items()},
                      "weekly_seasons": result["distinct_season_ids_in_weekly_archives"],
                      "pre_match_snapshot_runs": len(runs),
                      "processed_tables": len(historical_tables)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
