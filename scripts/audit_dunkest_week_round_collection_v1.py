#!/usr/bin/env python3
"""Read-only integrity audit for the versioned Dunkest weekly-round archive.

Writes a new, versioned JSON and Markdown report; never modifies source Parquets
or the collection manifest. Refuses to overwrite either report.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data/raw/dunkest_history_v2"
REPORT_DIR = ROOT / "reports/audit"
JSON_OUT = REPORT_DIR / "dunkest_week_round_collection_audit_v1.json"
MD_OUT = REPORT_DIR / "dunkest_week_round_collection_audit_v1.md"
EXPECTED_SEASONS = ("5", "7", "9", "13", "19")
REQUIRED_META = (
    "source_season_id", "source_week", "source_round",
    "source_stats_type", "source_granularity",
)


def main() -> None:
    if JSON_OUT.exists() or MD_OUT.exists():
        raise SystemExit("Refusing to overwrite an existing versioned audit output.")
    manifest_path = DATA_DIR / "collection_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing collection manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = sorted(DATA_DIR.glob("season_*.parquet"))
    if not paths:
        raise SystemExit(f"No season Parquets found in {DATA_DIR}")

    schema_counts: Counter[tuple[str, ...]] = Counter()
    files_by_season: Counter[str] = Counter()
    rows_by_season: Counter[str] = Counter()
    weeks_by_season: dict[str, set[int]] = defaultdict(set)
    task_types: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    player_sets: dict[tuple[str, int, str, str], set[str]] = {}
    issues: list[dict[str, object]] = []
    total_rows = 0
    pdk_nulls = 0
    id_nulls = 0
    duplicate_player_ids = 0
    duplicate_files = 0
    rows_by_type: Counter[str] = Counter()
    round_row_counts: dict[tuple[str, int, str, str], int] = {}

    for path in paths:
        parts = path.stem.split("_")
        try:
            if len(parts) != 7 or parts[0] != "season" or parts[2] != "week" or parts[4] != "round":
                raise ValueError("unexpected filename format")
            season, week, round_id, stats_type = parts[1], int(parts[3]), parts[5], parts[6]
            if stats_type not in {"avg", "tot"}:
                raise ValueError(f"unexpected stats type {stats_type!r}")
            df = pd.read_parquet(path)
        except Exception as exc:
            issues.append({"file": path.name, "issue": "read_or_filename_error", "detail": repr(exc)})
            continue

        total_rows += len(df)
        files_by_season[season] += 1
        rows_by_season[season] += len(df)
        weeks_by_season[season].add(week)
        rows_by_type[stats_type] += len(df)
        schema_counts[tuple(df.columns)] += 1
        task_types[(season, week, round_id)].add(stats_type)
        round_row_counts[(season, week, round_id, stats_type)] = len(df)

        missing_cols = [c for c in ("id", "pdk", *REQUIRED_META) if c not in df.columns]
        if missing_cols:
            issues.append({"file": path.name, "issue": "missing_columns", "detail": missing_cols})
            continue
        for col, expected in (
            ("source_season_id", season), ("source_week", week),
            ("source_round", round_id), ("source_stats_type", stats_type),
            ("source_granularity", "dunkest_week_round_table"),
        ):
            actual = df[col].astype(str)
            if actual.nunique(dropna=False) != 1 or actual.iloc[0] != str(expected):
                issues.append({"file": path.name, "issue": "metadata_mismatch", "detail": {"column": col, "expected": str(expected), "observed": actual.drop_duplicates().head(5).tolist()}})
        if df.empty:
            issues.append({"file": path.name, "issue": "empty_file"})
        id_nulls += int(df["id"].isna().sum())
        pdk_nulls += int(df["pdk"].isna().sum())
        if df["id"].duplicated().any():
            ndup = int(df["id"].duplicated().sum())
            duplicate_player_ids += ndup
            duplicate_files += 1
            issues.append({"file": path.name, "issue": "duplicate_player_ids", "detail": ndup})
        player_sets[(season, week, round_id, stats_type)] = set(df["id"].dropna().astype(str))

    unpaired = []
    for key, types in sorted(task_types.items()):
        if types != {"avg", "tot"}:
            unpaired.append({"season_id": key[0], "week": key[1], "round_id": key[2], "present": sorted(types), "missing": sorted({"avg", "tot"} - types)})
            continue
        season, week, round_id = key
        avg_ids = player_sets.get((season, week, round_id, "avg"), set())
        tot_ids = player_sets.get((season, week, round_id, "tot"), set())
        if avg_ids != tot_ids:
            issues.append({"task": f"{season}:{week}:{round_id}", "issue": "avg_tot_player_id_mismatch", "avg_only": sorted(avg_ids - tot_ids)[:20], "tot_only": sorted(tot_ids - avg_ids)[:20], "avg_only_count": len(avg_ids - tot_ids), "tot_only_count": len(tot_ids - avg_ids)})

    completed = set(manifest.get("completed", []))
    expected_manifest_keys = {
        f"{season}:{week}:{round_id}:{stats_type}"
        for (season, week, round_id), types in task_types.items()
        for stats_type in types
    }
    missing_manifest = sorted(expected_manifest_keys - completed)
    completed_without_file = []
    for key in completed:
        try:
            season, week, round_id, stats_type = key.split(":", 3)
            expected_file = DATA_DIR / f"season_{season}_week_{int(week)}_round_{round_id}_{stats_type}.parquet"
            if not expected_file.exists():
                completed_without_file.append(key)
        except Exception:
            completed_without_file.append(key)

    season_summary = []
    for season in EXPECTED_SEASONS:
        weeks = sorted(weeks_by_season.get(season, set()))
        gaps = [w for w in range(weeks[0], weeks[-1] + 1) if w not in set(weeks)] if weeks else []
        season_summary.append({
            "season_id": season,
            "files": files_by_season[season],
            "rows": rows_by_season[season],
            "weeks_with_data": len(weeks),
            "min_week": min(weeks) if weeks else None,
            "max_week": max(weeks) if weeks else None,
            "week_gaps_inside_observed_range": gaps,
            "rounds": sum(1 for s, _, _ in task_types if s == season),
            "avg_tot_complete_rounds": sum(1 for (s, _, _), types in task_types.items() if s == season and types == {"avg", "tot"}),
        })

    audit = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(DATA_DIR),
        "manifest_path": str(manifest_path),
        "files_found": len(paths),
        "manifest_completed_count": len(completed),
        "manifest_error_count": len(manifest.get("errors", [])),
        "completed_tasks_missing_file": completed_without_file,
        "parquet_tasks_missing_from_manifest": missing_manifest,
        "rows_total": total_rows,
        "rows_by_stats_type": dict(rows_by_type),
        "files_by_season": dict(files_by_season),
        "rows_by_season": dict(rows_by_season),
        "schema_variants": [{"columns": list(schema), "file_count": count} for schema, count in schema_counts.items()],
        "empty_files": sum(1 for issue in issues if issue.get("issue") == "empty_file"),
        "duplicate_player_id_rows": duplicate_player_ids,
        "files_with_duplicate_player_ids": duplicate_files,
        "null_player_ids": id_nulls,
        "null_pdk_values": pdk_nulls,
        "unpaired_avg_tot_rounds": unpaired,
        "integrity_issues": issues,
        "season_summary": season_summary,
        "coverage_limitations": [
            "This audit checks internal consistency of saved weekly-round tables, not whether the API exposed every historical round.",
            "Stats season IDs 1 and 3 are absent from this weekly-round archive and are handled by the separate player-game history collection.",
            "No original Parquet or manifest was modified.",
        ],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Dunkest weekly-round archive integrity audit (v1)", "",
        f"Generated UTC: {audit['generated_utc']}", "",
        "## Summary", "",
        f"- Parquet files: **{len(paths):,}**; manifest completed entries: **{len(completed):,}**.",
        f"- Rows: **{total_rows:,}**; schema variants: **{len(schema_counts)}**.",
        f"- Manifest errors: **{len(manifest.get('errors', []))}**; tasks without files: **{len(completed_without_file)}**; files missing from manifest: **{len(missing_manifest)}**.",
        f"- Empty files: **{audit['empty_files']}**; duplicate player-ID rows: **{duplicate_player_ids}**; null IDs: **{id_nulls}**; null PDK: **{pdk_nulls}**.",
        f"- Unpaired avg/tot rounds: **{len(unpaired)}**; integrity issues: **{len(issues)}**.", "",
        "## Per-season coverage observed", "",
        "| Season ID | Files | Rows | Weeks with data | Week range | Rounds | Paired avg/tot | Gaps inside observed range |",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for s in season_summary:
        week_range = f"{s['min_week']}–{s['max_week']}" if s['min_week'] is not None else "—"
        lines.append(f"| {s['season_id']} | {s['files']} | {s['rows']:,} | {s['weeks_with_data']} | {week_range} | {s['rounds']} | {s['avg_tot_complete_rounds']} | {', '.join(map(str, s['week_gaps_inside_observed_range'])) or 'None'} |")
    lines += ["", "## Findings", ""]
    if not issues and not unpaired and not missing_manifest and not completed_without_file and not manifest.get("errors"):
        lines.append("No internal consistency errors were detected in the saved collection.")
    else:
        lines.append("Issues were detected; inspect the JSON report for file/task-level details.")
    lines += [
        "", "## Interpretation and limits", "",
        "This is an integrity audit, not proof of complete historical API coverage. It validates file readability, task metadata, manifest/file correspondence, player-ID uniqueness within each table, and matching player-ID sets between avg and tot tables.",
        "The weekly-round endpoint archive includes stats season IDs 5, 7, 9, 13 and 19. IDs 1 and 3 (2018/19 and 2019/20) are handled separately through the per-player game-history endpoint; their `gameValidForDunkest` flags remain unaltered and must not be interpreted as official eligible targets without independent verification.",
        "", "Source files were read only. No raw data, production configuration, targets, temporal splits, models, or backtests were modified.", "",
        f"JSON details: `{JSON_OUT.relative_to(ROOT)}`", "",
    ]
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"JSON report: {JSON_OUT}")
    print(f"Markdown report: {MD_OUT}")
    print(f"Files={len(paths)} rows={total_rows} schema_variants={len(schema_counts)}")
    print(f"Unpaired rounds={len(unpaired)} integrity_issues={len(issues)} manifest_errors={len(manifest.get('errors', []))}")
    print("Season coverage:")
    for s in season_summary:
        print(f"  {s['season_id']}: files={s['files']} rows={s['rows']} weeks={s['min_week']}..{s['max_week']} rounds={s['rounds']} gaps={s['week_gaps_inside_observed_range']}")


if __name__ == "__main__":
    main()
