#!/usr/bin/env python3
"""Audit integrity and temporal evidence for archived pre-match prediction snapshots.

Read-only against existing runs. Writes new, versioned audit outputs only.
A run timestamp before a fixture date is evidence of a pre-game freeze, but is
not a substitute for a source-level retrieval timestamp.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data" / "predictions"
OUT = ROOT / "reports" / "audit"
STEM = "dunkest_pre_match_snapshot_authenticity_v1"
JSON_PATH = OUT / f"{STEM}.json"
MD_PATH = OUT / f"{STEM}.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def main() -> int:
    if JSON_PATH.exists() or MD_PATH.exists():
        raise SystemExit(f"Refusing to overwrite versioned output: {JSON_PATH} / {MD_PATH}")
    OUT.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []

    for manifest_path in sorted(RUNS.glob("*/manifest.json")):
        run_dir = manifest_path.parent
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        snapshot = manifest.get("pre_match_snapshot") or {}
        files = snapshot.get("files") or []
        # Only count runs that actually archive a snapshot bundle; old prediction
        # runs without one are not evidence of a pre-match capture.
        if not files:
            continue
        hash_checks = []
        source_capture_times = []
        for entry in files:
            rel = str(entry.get("path") or "")
            path = run_dir / "pre_match_snapshot" / rel
            exists = path.is_file()
            actual_hash = sha256(path) if exists else None
            expected_hash = entry.get("sha256")
            hash_checks.append({
                "path": rel,
                "exists": exists,
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
                "hash_matches": bool(exists and expected_hash and actual_hash == expected_hash),
            })
            if exists and rel.endswith(".meta.json"):
                try:
                    meta = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    meta = {}
                captured = parse_dt(meta.get("fetched_at") or meta.get("retrieved_at") or meta.get("captured_at"))
                if captured:
                    source_capture_times.append({"file": rel, "timestamp_utc": captured.isoformat()})

        mapping_paths = [
            run_dir / "pre_match_snapshot" / str(entry.get("path") or "")
            for entry in files
            if str(entry.get("path") or "").startswith("dunkest_fixture_mapping_")
        ]
        mapping_rows = 0
        first_game_date = None
        last_game_date = None
        fixture_ids: list[str] = []
        mapping_retrieval_times: list[str] = []
        for mapping_path in mapping_paths:
            if not mapping_path.is_file():
                continue
            try:
                mapping = pd.read_parquet(mapping_path)
            except Exception:
                continue
            mapping_rows += len(mapping)
            if "game_datetime_utc" in mapping and len(mapping):
                dates = pd.to_datetime(mapping["game_datetime_utc"], utc=True, errors="coerce").dropna()
                if len(dates):
                    first = dates.min().date().isoformat()
                    last = dates.max().date().isoformat()
                    first_game_date = first if first_game_date is None else min(first_game_date, first)
                    last_game_date = last if last_game_date is None else max(last_game_date, last)
            if "nba_game_id" in mapping:
                fixture_ids.extend(str(x) for x in mapping["nba_game_id"].dropna().unique())
            if "source_retrieved_at_utc" in mapping:
                dates = pd.to_datetime(mapping["source_retrieved_at_utc"], utc=True, errors="coerce").dropna()
                mapping_retrieval_times.extend(x.isoformat() for x in dates.unique())

        run_time = parse_dt(manifest.get("timestamp"))
        run_day = run_time.date() if run_time else None
        first_day = date.fromisoformat(first_game_date) if first_game_date else None
        all_hashes_valid = bool(hash_checks) and all(x["hash_matches"] for x in hash_checks)
        before_fixture_day = bool(run_day and first_day and run_day < first_day)
        source_times_before_fixture = []
        if first_day:
            source_times_before_fixture = [
                x for x in source_capture_times
                if parse_dt(x["timestamp_utc"]) and parse_dt(x["timestamp_utc"]).date() < first_day
            ]
        season = str((manifest.get("configuration") or {}).get("season") or manifest.get("season") or "")
        runs.append({
            "run_id": manifest.get("run_id") or run_dir.name,
            "season": season,
            "target_gameweek": manifest.get("target_gameweek") or (manifest.get("configuration") or {}).get("target_gameweek"),
            "run_timestamp_utc": run_time.isoformat() if run_time else manifest.get("timestamp"),
            "first_fixture_date_utc": first_game_date,
            "last_fixture_date_utc": last_game_date,
            "run_before_first_fixture_date": before_fixture_day,
            "snapshot_file_count": len(hash_checks),
            "hash_checks": hash_checks,
            "all_snapshot_hashes_valid": all_hashes_valid,
            "mapping_rows": mapping_rows,
            "unique_fixture_ids": len(set(fixture_ids)),
            "mapping_source_retrieval_timestamps": sorted(set(mapping_retrieval_times)),
            "source_capture_timestamps_in_bundle": source_capture_times,
            "source_capture_times_before_fixture_day": source_times_before_fixture,
            "classification": (
                "hash_valid_and_run_precedes_fixture_day"
                if all_hashes_valid and before_fixture_day
                else "incomplete_or_temporal_evidence_needs_review"
            ),
        })

    current_season = [r for r in runs if r["season"] == "2026-27"]
    prior_season = [r for r in runs if r["season"] and r["season"] != "2026-27"]
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_count": len(runs),
        "runs_with_valid_snapshot_hashes": sum(r["all_snapshot_hashes_valid"] for r in runs),
        "runs_before_first_fixture_date_with_valid_hashes": sum(
            r["all_snapshot_hashes_valid"] and r["run_before_first_fixture_date"] for r in runs
        ),
        "runs_with_source_capture_timestamp_in_bundle": sum(bool(r["source_capture_timestamps_in_bundle"]) for r in runs),
        "current_2026_27_run_count": len(current_season),
        "non_2026_27_run_count": len(prior_season),
        "runs": runs,
        "conclusion": {
            "historical_pre_match_snapshots": (
                "No non-2026/27 season run-level snapshots were found in data/predictions; "
                "historical weekly-round tables are outcomes, not authenticated pre-game market captures."
                if not prior_season else
                "Non-2026/27 run-level snapshots exist and require their per-run classifications to be reviewed."
            ),
            "temporal_limit": (
                "Run timestamps and frozen file hashes establish what was saved in a run and that the run predates "
                "the mapped fixture date. They do not alone prove the exact retrieval time of each source; that "
                "requires source-side metadata copied into the bundle."
            ),
            "future_capture": (
                "New prediction runs now copy any adjacent *.meta.json source metadata files into pre_match_snapshot "
                "and hash them in manifest.json."
            ),
        },
    }
    JSON_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Pre-match snapshot authenticity audit — V1", "",
        f"Generated UTC: {result['generated_at_utc']}", "",
        "## Summary", "",
        f"- Run manifests scanned: **{result['run_count']}**",
        f"- Runs with every archived snapshot hash valid: **{result['runs_with_valid_snapshot_hashes']}**",
        f"- Hash-valid runs frozen before the first mapped fixture date: **{result['runs_before_first_fixture_date_with_valid_hashes']}**",
        f"- Runs with source retrieval metadata copied into the bundle: **{result['runs_with_source_capture_timestamp_in_bundle']}**",
        f"- 2026/27 runs: **{result['current_2026_27_run_count']}**",
        f"- Other-season runs: **{result['non_2026_27_run_count']}**", "",
        "## Run-level evidence", "",
        "| Run ID | Season | Frozen at (UTC) | First fixture date | Snapshot files | Hashes valid | Before fixture date | Classification |",
        "|---|---|---|---|---:|---|---|---|",
    ]
    for r in runs:
        lines.append(
            f"| {r['run_id']} | {r['season'] or 'unknown'} | {r['run_timestamp_utc'] or 'missing'} | "
            f"{r['first_fixture_date_utc'] or 'missing'} | {r['snapshot_file_count']} | "
            f"{'yes' if r['all_snapshot_hashes_valid'] else 'no'} | "
            f"{'yes' if r['run_before_first_fixture_date'] else 'no/unknown'} | {r['classification']} |"
        )
    lines += [
        "", "## Conclusions and limits", "",
        result["conclusion"]["historical_pre_match_snapshots"], "",
        result["conclusion"]["temporal_limit"], "",
        result["conclusion"]["future_capture"], "",
        "A valid hash proves that archived bytes match the run manifest; it does not prove the source data itself was correct or available at that exact time. Fixture timestamps are compared by UTC calendar date because some schedule records use date-level midnight placeholders.",
        "", "## Reproducibility", "",
        "    PYTHONPATH=src ./.venv/bin/python scripts/audit_pre_match_snapshot_authenticity_v1.py",
        "",
    ]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "json": str(JSON_PATH.relative_to(ROOT)),
        "markdown": str(MD_PATH.relative_to(ROOT)),
        "runs": len(runs),
        "hash_valid": result["runs_with_valid_snapshot_hashes"],
        "pre_fixture_day": result["runs_before_first_fixture_date_with_valid_hashes"],
        "with_source_capture_times": result["runs_with_source_capture_timestamp_in_bundle"],
        "current_season_runs": len(current_season),
        "other_season_runs": len(prior_season),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
